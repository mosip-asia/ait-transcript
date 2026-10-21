"""Plain-assert smoke tests for generate_csv.py (PLAN.md Phase 0 Tests).

Run: python3 data/test_generate_csv.py
"""

from __future__ import annotations

import base64
import csv
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import generate_csv as gc  # noqa: E402


def test_row_count_and_columns() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    degree_count = sum(len(s["degrees"]) for s in data["students"])
    assert len(rows) == degree_count
    assert len(data["students"]) == 5
    assert set(rows[0].keys()) == set(gc.CSV_COLUMNS)


def test_multi_degree_student_gets_distinct_rows() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    dual_degree_student = next(s for s in data["students"] if len(s["degrees"]) > 1)
    degree_ids = {d["keycloakId"] for d in dual_degree_student["degrees"]}
    matching_rows = [r for r in rows if r["id"] in degree_ids]
    assert len(matching_rows) == len(degree_ids)
    assert len({r["registrationNo"] for r in matching_rows}) == len(degree_ids)
    assert len({r["courses"] for r in matching_rows}) == len(degree_ids)


def test_registrars_excluded() -> None:
    data = gc.load_students()
    assert len(data["registrars"]) >= 1
    rows = gc.build_rows(data["students"])
    row_ids = {r["id"] for r in rows}
    registrar_ids = {r["id"] for r in data["registrars"]}
    assert row_ids.isdisjoint(registrar_ids)


def test_generated_csv_roundtrip() -> None:
    data = gc.load_students()
    rows = gc.build_rows(data["students"])
    with tempfile.TemporaryDirectory() as td:
        out_path = Path(td) / "out.csv"
        gc.write_csv(rows, out_path)
        with open(out_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == gc.CSV_COLUMNS
            read_rows = list(reader)
    assert len(read_rows) == len(rows)
    assert any("CS601" in (r["courses"] or "") for r in read_rows)
    assert all("${" not in (r["courses"] or "") for r in read_rows)


def test_columns_carry_no_course_table_html() -> None:
    # Every claim is signed now; the course record travels once, as courses (spec: Context fix).
    assert "courseTableHtml" not in gc.CSV_COLUMNS


AIT = gc.REPO_ROOT / "installations" / "ait"


def seed_value(pattern: str) -> str:
    """One SQL string literal of the ait-transcript credential_config row, found by its shape."""
    return re.search(pattern, (AIT / "certify_seed.sql").read_text(encoding="utf-8"))[1]


def seed_template() -> dict:
    template = base64.b64decode(seed_value(r"'(ewo[A-Za-z0-9+/=]+)'")).decode()
    return json.loads(template.replace("${courses}", "[]"))  # the one unquoted placeholder


def test_certify_configuration_names_the_generated_columns() -> None:
    columns = ",".join(["id", *gc.CLAIM_COLUMNS])  # the adapter columns after them are not claims
    (plugin_config,) = json.loads(seed_value(r"'(\[\{\"mosip\.certify\.mock[^']*)'::JSONB"))
    assert plugin_config["mosip.certify.mock.data-provider.csv.data-columns"] == columns
    assert list(json.loads(seed_value(r"'(\{\"fullName\": \{\"display\"[^']*)'::JSONB"))) == gc.CLAIM_COLUMNS
    assert list(seed_template()["credentialSubject"]) == ["id", *gc.CLAIM_COLUMNS]


def test_template_and_context_column_name_the_same_vdr_url() -> None:
    url = seed_value(r"'([^']*/contexts/transcript/v1\.json[^']*)'").split(",")[0]
    assert url == "http://host.docker.internal:9098/contexts/transcript/v1.json", url
    assert seed_template()["@context"] == ["https://www.w3.org/ns/credentials/v2", url,
                                           "https://w3id.org/security/suites/ed25519-2020/v1"]


def test_context_v1_signs_every_generated_claim() -> None:
    # Claim terms at the top level, untyped strings except courses as a JSON literal (spec: Context fix).
    context = gc.REPO_ROOT / "vc-lab" / "contexts" / "transcript" / "v1.json"
    terms = json.loads(context.read_text(encoding="utf-8"))["@context"]
    assert terms["ait"] == "https://ait.example/transcript#"
    assert terms["AitTranscriptCredential"] == "ait:AitTranscriptCredential"
    for claim in gc.CLAIM_COLUMNS:
        want = {"@id": "ait:courses", "@type": "@json"} if claim == "courses" else f"ait:{claim}"
        assert terms.get(claim) == want, (claim, terms.get(claim))
    assert set(terms) == {"@version", "@protected", "ait", "AitTranscriptCredential", *gc.CLAIM_COLUMNS}


def test_eligibility_columns_follow_the_claims() -> None:
    # The mock adapter's columns come after the claims; Certify maps by header name and ignores them.
    assert gc.CSV_COLUMNS == ["id", *gc.CLAIM_COLUMNS, "level", "holds", "conferralStatus", "balance"]


def test_personas_cover_each_transcript_check() -> None:
    rows = gc.build_rows(gc.load_students()["students"])
    holds = [json.loads(r["holds"]) for r in rows]
    assert any(holds) and not all(holds)  # a hold fails the no-holds check
    assert {"Conferred"} < {r["conferralStatus"] for r in rows}  # and a student that is not conferred
    assert any(float(r["balance"]) > 0 for r in rows) and any(float(r["balance"]) == 0 for r in rows)
    clean = [r for r in rows if not json.loads(r["holds"]) and r["conferralStatus"] == "Conferred" and float(r["balance"]) == 0]
    assert clean  # someone still passes all three


def test_csv_goes_to_the_ait_installation_adapter() -> None:
    # Certify and, later, the mock adapter mount it from there (spec: Directory layout).
    repo_root = Path(__file__).resolve().parent.parent
    assert gc.OUT_CSV.resolve() == repo_root / "installations" / "ait" / "adapter" / "student_identity_data.csv"


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")

