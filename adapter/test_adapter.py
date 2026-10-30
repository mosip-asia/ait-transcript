"""Tests for the mock adapter (contracts.md section 2b).

Run: python3 adapter/test_adapter.py                      on the host, no Docker: a temp CSV from the generator,
                                                          then a temp copy of the hackathon roster
     python3 adapter/test_adapter.py URL CSV COPY_URL COPY_CSV
                                                          against the running containers (smoke.sh): the reads at
                                                          URL, the adapter serving CSV (the transcript CSV or a
                                                          roster), and the edit case at COPY_URL, a second adapter
                                                          serving COPY_CSV, a copy, so CSV is never rewritten
Needs fastapi and httpx (portal/requirements.txt).
"""

from __future__ import annotations

import csv
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
import generate_csv as gc  # noqa: E402

ROSTER = Path(__file__).parent.parent / "installations" / "hackathon" / "adapter" / "student_identity_data.csv"


def read_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def set_column(csv_path: Path, sub: str, column: str, value: str) -> None:
    rows = read_rows(csv_path)
    next(r for r in rows if r["id"] == sub)[column] = value
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def check_adapter(get, csv_path: Path) -> None:
    """`get(path)` returns (status, body). Checks every row of csv_path, then an unknown sub."""
    rows = read_rows(csv_path)
    # The transcript CSV carries contract 2b's eligibility attributes; a roster does not.
    if "balance" in rows[0]:
        check_transcript_rows(get, rows)
    else:
        check_roster_rows(get, rows)

    first = rows[0]["id"]
    for path in ("degrees", "transcript", "eligibility"):
        assert get(f"/students/nobody/{path}")[0] == 404, path
    assert get(f"/students/{first}/transcript?degreeId=other")[0] == 404
    assert get(f"/students/{first}/eligibility?degreeId=other")[0] == 404


def check_edit(get, csv_path: Path) -> None:
    """The file is read again on every request: an edited value of csv_path is served at once. Rewrites csv_path
    and puts it back, so csv_path must be a copy, never an installation's file."""
    rows = read_rows(csv_path)
    edited = "balance" if "balance" in rows[0] else "teamId"
    first = rows[0]["id"]
    original = csv_path.read_bytes()
    try:
        before = get(f"/students/{first}/eligibility")[1][edited]
        assert before != "777.00"
        set_column(csv_path, first, edited, "777.00")
        assert get(f"/students/{first}/eligibility")[1][edited] == "777.00"
    finally:
        csv_path.write_bytes(original)
    assert get(f"/students/{first}/eligibility")[1][edited] == before


def check_transcript_rows(get, rows: list[dict]) -> None:
    assert len(rows) >= 7
    for row in rows:
        sub = row["id"]
        status, body = get(f"/students/{sub}/degrees")
        assert status == 200 and len(body) == 1, (sub, status, body)
        assert body[0] == {"degreeId": sub, "level": row["level"], "degreeAwarded": row["degreeAwarded"],
                           "dateGraduation": row["dateGraduation"]}, body

        status, body = get(f"/students/{sub}/transcript?degreeId={sub}")
        assert status == 200, (sub, status)
        assert body["fullName"] == row["fullName"] and body["degreeId"] == sub and body["level"] == row["level"]
        assert body["registrationNo"] == row["registrationNo"] and "balance" not in body and "courseList" not in body
        assert isinstance(body["courses"], list) and body["courses"][0]["term"] and body["courses"][0]["courses"][0]["no"]
        # Every other cell exactly as written, a multiline one included: the adapter neither escapes nor un-escapes.
        verbatim = {k: v for k, v in row.items() if k not in {"id", "courses", "courseList", "holds", "conferralStatus", "balance"}}
        assert body == {"degreeId": sub, **verbatim, "courses": json.loads(row["courses"])}, sub

        status, body = get(f"/students/{sub}/eligibility?degreeId={sub}")
        assert status == 200 and body == {"holds": json.loads(row["holds"]), "conferralStatus": row["conferralStatus"],
                                          "balance": row["balance"]}, (sub, body)
        assert get(f"/students/{sub}/eligibility")[0] == 200  # degreeId is optional: there is one degree per sub


def check_roster_rows(get, rows: list[dict]) -> None:
    """A roster (the hackathon installation): the degree list names the row, and the record and the eligibility
    paths both serve the row's columns."""
    for row in rows:
        sub = row["id"]
        columns = {k: v for k, v in row.items() if k != "id"}
        assert get(f"/students/{sub}/degrees") == (200, [{"degreeId": sub}]), sub
        assert get(f"/students/{sub}/transcript?degreeId={sub}") == (200, {"degreeId": sub, **columns}), sub
        assert get(f"/students/{sub}/eligibility?degreeId={sub}") == (200, columns), sub


def host_get(csv_path: Path):
    """`get(path)` over the adapter's app in-process, serving csv_path."""
    from fastapi.testclient import TestClient

    os.environ["ADAPTER_CSV"] = str(csv_path)
    import main

    client = TestClient(main.app)

    def get(path: str) -> tuple[int, object]:
        r = client.get(path)
        return r.status_code, r.json()

    return get


def test_mock_adapter_on_a_generated_csv() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        get = host_get(csv_path)
        check_adapter(get, csv_path)
        check_edit(get, csv_path)


def test_mock_adapter_on_the_hackathon_roster() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(ROSTER.read_bytes())
        # A quote and a newline in a cell are served as written (no JSON decoding of plain cells).
        set_column(csv_path, "hack-2026-0002", "teamName", 'Chain "Gang"\nof two')
        get = host_get(csv_path)
        check_adapter(get, csv_path)
        check_edit(get, csv_path)
        assert get("/students/hack-2026-0001/transcript")[1]["teamName"] == "Sandbox Pioneers"
        assert get("/students/hack-2026-0002/transcript")[1]["teamName"] == 'Chain "Gang"\nof two'
        # The participant without a team is on the roster, with an empty teamId.
        assert get("/students/hack-2026-0003/eligibility")[1]["teamId"] == ""


def drift(schema: dict, spec: dict, defs: dict, components: dict, where: str) -> list[str]:
    """What a model's input schema `schema` asks of the wire that openapi.yaml's `spec` does not promise: a field the
    model requires and the YAML does not, or another type, enum, pattern or minLength, compared down through arrays
    and objects. `defs` and `components` resolve the `$ref`s of each side."""
    schema = defs[schema["$ref"].rsplit("/", 1)[1]] if "$ref" in schema else schema
    spec = components[spec["$ref"].rsplit("/", 1)[1]] if "$ref" in spec else spec
    found = [f"{where}: {key} {schema.get(key)!r} in the model, {spec.get(key)!r} in openapi.yaml"
             for key in ("type", "enum", "pattern", "minLength") if key in schema and schema[key] != spec.get(key)]
    if found or schema.get("type") not in ("array", "object"):
        return found
    if schema["type"] == "array":
        return drift(schema["items"], spec["items"], defs, components, f"{where}[]")
    for name in schema.get("required", []):
        if name not in spec.get("required", []):
            found.append(f"{where}.{name}: required by the model, not by openapi.yaml")
        else:
            found += drift(schema["properties"][name], spec["properties"][name], defs, components, f"{where}.{name}")
    return found


def test_every_field_a_gateway_model_requires_is_required_in_openapi_yaml() -> None:
    """The Gateway's models of the adapter's answers (gateway/credential_types.py) ask nothing of the wire beyond
    adapter/openapi.yaml: each model's validation-mode schema, the input it accepts, against one of the schemas the
    YAML gives for that path. Fields the YAML requires and no model reads are fine."""
    import yaml
    from pydantic import TypeAdapter

    sys.path.insert(0, str(Path(__file__).parent.parent / "gateway"))
    import credential_types as ct

    spec = yaml.safe_load((Path(__file__).parent / "openapi.yaml").read_text(encoding="utf-8"))
    components = spec["components"]["schemas"]

    def answers(path: str) -> list[dict]:
        schema = spec["paths"][f"/students/{{id}}/{path}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        return schema.get("oneOf", [schema])

    def drifts(model, path: str) -> list[list[str]]:
        schema = TypeAdapter(model).json_schema(mode="validation")
        return [drift(schema, answer, schema.get("$defs", {}), components, f"{path} {model}") for answer in answers(path)]

    checked = [(list[ct.Degree], "degrees")] + [
        pair for t in ct.REGISTRY.values() for pair in ((t.eligibility, "eligibility"), (t.record, "transcript"))]
    for model, path in checked:
        assert [] in drifts(model, path), drifts(model, path)
    # The comparison can fail: a field the YAML does not require, a wire type it does not give, and a minimum length
    # it does not state.
    assert drift({"type": "object", "required": ["x"]}, {"type": "object"}, {}, {}, "m") != []
    assert drift({"type": "string"}, {"$ref": "#/components/schemas/Term"}, {}, components, "m") != []
    assert drift({"type": "string", "minLength": 1}, {"type": "string"}, {}, {}, "m") != []


def run_live(url: str, csv_path: Path, copy_url: str, copy_csv: Path) -> None:
    import time

    import httpx

    def getter(base: str):
        def get(path: str) -> tuple[int, object]:
            r = httpx.get(base + path, timeout=10)
            return r.status_code, r.json()
        return get

    check_adapter(getter(url), csv_path)
    # The second adapter was started just before this run: wait for it to answer.
    for _ in range(30):
        try:
            httpx.get(copy_url + "/docs", timeout=3)
            break
        except httpx.HTTPError:
            time.sleep(1)
    check_edit(getter(copy_url), copy_csv)


if __name__ == "__main__":
    if len(sys.argv) == 5:
        run_live(sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
        print(f"PASS adapter at {sys.argv[1]}, edit case at {sys.argv[3]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
