"""Tests for the mock adapter and the Adapter contract (adapter/openapi.yaml).

Run: python3 adapter/test_adapter.py                      on the host, no Docker: a temp CSV from the generator,
                                                          then a temp copy of the hackathon roster, and the
                                                          contract's own checks
     python3 adapter/test_adapter.py URL CSV COPY_URL COPY_CSV
                                                          against the running containers (smoke.sh): the reads at
                                                          URL, the adapter serving CSV (the transcript CSV or a
                                                          roster), and the edit case at COPY_URL, a second adapter
                                                          serving COPY_CSV, a copy, so CSV is never rewritten
     python3 adapter/test_adapter.py --contract URL SUB SCOPE
                                                          the contract mode, against any Adapter at URL: the list
                                                          for SUB, its first record against SCOPE's record schema
                                                          (no reserved key), and a 404 or an empty
                                                          list for an unknown sub.
                                                          check_contract(get, sub, scope) is the same in-process
     python3 adapter/test_adapter.py --record-claims SCOPE
                                                          the claim names of SCOPE's record schema, one per line
                                                          (issuer-checks.sh compares Certify's metadata with them)
Needs fastapi, httpx and PyYAML (portal/requirements.txt).
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "data"))
import generate_csv as gc  # noqa: E402

ROSTER = Path(__file__).parent.parent / "installations" / "hackathon" / "adapter" / "student_identity_data.csv"
# The scopes each CSV's Installation enables. The mock serves the same row for every one of them.
TRANSCRIPT_SCOPES = ("ait_transcript_vc_ldp",)
ROSTER_SCOPES = ("developer_passport_vc_ldp", "achievement_certificate_vc_ldp")
ELIGIBILITY = ("holds", "conferralStatus", "balance")  # the transcript CSV's eligibility columns


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

    # An unknown sub or recordId is a 404 on every /records path.
    for path in ("/records?sub=nobody&scope=any", "/records/nobody?scope=any", "/records/nobody/eligibility?scope=any"):
        assert get(path)[0] == 404, path


def check_edit(get, csv_path: Path) -> None:
    """The file is read again on every request: an edited value of csv_path is served at once. Rewrites csv_path
    and puts it back, so csv_path must be a copy, never an installation's file."""
    rows = read_rows(csv_path)
    edited = "balance" if "balance" in rows[0] else "teamId"
    first = rows[0]["id"]
    original = csv_path.read_bytes()
    path = f"/records/{first}/eligibility?scope=any"
    try:
        before = get(path)[1][edited]
        assert before != "777.00"
        set_column(csv_path, first, edited, "777.00")
        assert get(path)[1][edited] == "777.00"
    finally:
        csv_path.write_bytes(original)
    assert get(path)[1][edited] == before


def check_transcript_rows(get, rows: list[dict]) -> None:
    assert len(rows) >= 7
    for row in rows:
        sub = row["id"]
        for scope in TRANSCRIPT_SCOPES:
            assert get(f"/records?sub={sub}&scope={scope}") == (200, [{
                "recordId": sub, "level": row["level"], "degreeAwarded": row["degreeAwarded"],
                "dateGraduation": row["dateGraduation"]}]), sub
            # The record: every column but the id and the eligibility columns, the generator's courseList included.
            status, body = get(f"/records/{sub}?scope={scope}")
            assert status == 200 and "id" not in body and not set(ELIGIBILITY) & body.keys(), (sub, status, body)
            assert body["courseList"] == row["courseList"] and "\n" in body["courseList"], sub
            assert isinstance(body["courses"], list) and body["courses"][0]["term"] and body["courses"][0]["courses"][0]["no"]
            # Every other cell exactly as written, a multiline one included: the adapter neither escapes nor un-escapes.
            verbatim = {k: v for k, v in row.items() if k not in {"id", "courses", *ELIGIBILITY}}
            assert body == {**verbatim, "courses": json.loads(row["courses"])}, sub
            assert get(f"/records/{sub}/eligibility?scope={scope}") == (200, {
                "holds": json.loads(row["holds"]), "conferralStatus": row["conferralStatus"],
                "balance": row["balance"]}), sub


def check_roster_rows(get, rows: list[dict]) -> None:
    """A roster (the hackathon installation): the list names the row, and the record and the eligibility paths both
    serve the row's columns."""
    for row in rows:
        sub = row["id"]
        columns = {k: v for k, v in row.items() if k != "id"}
        for scope in ROSTER_SCOPES:  # the roster has no degree columns, so the list names the row only
            assert get(f"/records?sub={sub}&scope={scope}") == (200, [{"recordId": sub}]), (sub, scope)
            assert get(f"/records/{sub}?scope={scope}") == (200, columns), (sub, scope)
            assert get(f"/records/{sub}/eligibility?scope={scope}") == (200, columns), (sub, scope)


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
        scope = ROSTER_SCOPES[0]
        assert get(f"/records/hack-2026-0001?scope={scope}")[1]["teamName"] == "Sandbox Pioneers"
        assert get(f"/records/hack-2026-0002?scope={scope}")[1]["teamName"] == 'Chain "Gang"\nof two'
        # The participant without a team is on the roster, with an empty teamId.
        assert get(f"/records/hack-2026-0003/eligibility?scope={scope}")[1]["teamId"] == ""


OPENAPI = Path(__file__).parent / "openapi.yaml"
PLUGIN = Path(__file__).parent.parent / "plugin/src/main/java/asia/mosip/issuer/plugin/IssuerDataProviderPlugin.java"
# Certify's reserved keys and the plugin's trace keys: no record may carry one (spec, "Shaping the data map").
FORBIDDEN_KEYS = {"id", "_holderId", "_issuer", "validFrom", "validUntil", "credentialStatus", "tokenSub", "tokenClientId"}


def load_contract() -> dict:
    import yaml

    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def resolve(schema: dict, contract: dict) -> dict:
    while "$ref" in schema:
        schema = contract["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


def answer_schemas(contract: dict, path: str) -> list[dict]:
    """The schemas the contract gives for a 200 at `path`, resolved."""
    schema = contract["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return [resolve(s, contract) for s in schema.get("oneOf", [schema])]


def scope_schema(contract: dict, path: str, scope: str) -> dict:
    """The schema the contract names at `path` for the token scope `scope` (space-separated scopes), by `x-scope`."""
    (schema,) = [s for s in answer_schemas(contract, path) if s.get("x-scope") in scope.split()] or [None]
    assert schema is not None, f"openapi.yaml names no schema for scope {scope} at {path}"
    return schema


TYPES = {"string": str, "array": list, "object": dict, "boolean": bool}


def violations(value, schema: dict, contract: dict, where: str) -> list[str]:
    """How `value` breaks `schema`, for the keywords openapi.yaml uses on answers: type, required, properties, items,
    propertyNames, enum, not and minLength. A field the schema does not name is not checked."""
    schema = resolve(schema, contract)
    if "type" in schema and not isinstance(value, TYPES[schema["type"]]):
        return [f"{where}: {value!r} is not a {schema['type']}"]
    found = []
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "not" in schema and not violations(value, schema["not"], contract, where):
        found.append(f"{where}: {value!r} is excluded by openapi.yaml")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        found.append(f"{where}: {value!r} is too short")
    if isinstance(value, list):
        for i, item in enumerate(value):
            found += violations(item, schema.get("items", {}), contract, f"{where}[{i}]")
    if isinstance(value, dict):
        found += [f"{where}.{name}: missing" for name in schema.get("required", []) if name not in value]
        for key, item in value.items():
            if "propertyNames" in schema:
                found += violations(key, schema["propertyNames"], contract, f"{where} key")
            if key in schema.get("properties", {}):
                found += violations(item, schema["properties"][key], contract, f"{where}.{key}")
    return found


def check_contract(get, sub: str, scope: str) -> None:
    """The contract mode: any Adapter, through `get(path)` -> (status, body), against openapi.yaml for one known
    `sub` and one token `scope`. The list is a non-empty list of record summaries; its first entry's record follows
    the scope's record schema, so it holds every claim and no reserved or trace key; an unknown sub is a 404 or an
    empty list."""
    from urllib.parse import quote

    contract = load_contract()
    q = lambda value: quote(value, safe="")  # noqa: E731
    status, entries = get(f"/records?sub={q(sub)}&scope={q(scope)}")
    assert status == 200, f"GET /records for {sub}: {status} {entries!r}"
    (list_schema,) = answer_schemas(contract, "/records")
    problems = violations(entries, list_schema, contract, "list")
    assert entries and not problems, f"GET /records for {sub}: {problems or 'an empty list'}"

    status, record = get(f"/records/{q(entries[0]['recordId'])}?scope={q(scope)}")
    assert status == 200, f"GET /records/{entries[0]['recordId']}: {status} {record!r}"
    problems = violations(record, scope_schema(contract, "/records/{recordId}", scope), contract, "record")
    assert not problems, f"GET /records/{entries[0]['recordId']}: {problems}"

    unknown = "no-such-student-" + os.urandom(4).hex()
    status, unknown_entries = get(f"/records?sub={unknown}&scope={q(scope)}")
    assert status == 404 or (status == 200 and unknown_entries == []), (
        f"GET /records for an unknown sub: {status} {unknown_entries!r}, not a 404 or an empty list")


def template_claims() -> dict[str, set[str]]:
    """Each Installation's Certify templates, by scope: the names they substitute, less the ones Certify sets."""
    import base64

    found = {}
    for seed in (Path(__file__).parent.parent / "installations").glob("*/certify_seed.sql"):
        for row in seed.read_text(encoding="utf-8").split("INSERT INTO certify.credential_config")[1:]:
            (scope,) = re.findall(r"'([a-z_]+_vc_ldp)'", row)
            (template,) = re.findall(r"'(ewo[A-Za-z0-9+/=]+)'", row)
            names = set(re.findall(r"\$\{([^}]+)\}", base64.b64decode(template).decode()))
            found[scope] = {n for n in names if n not in {"_issuer", "_holderId", "validFrom", "validUntil"}
                            and not n.startswith("credentialStatus.")}
    return found


def test_every_record_schema_lists_exactly_the_claims_its_template_substitutes() -> None:
    """GET /records/{recordId} names one record schema per scope, and each lists exactly the claims its Certify
    template substitutes, every one required, a string but `courses`, and no reserved or trace key."""
    contract = load_contract()
    claims = template_claims()
    assert set(claims) == {"ait_transcript_vc_ldp", "developer_passport_vc_ldp", "achievement_certificate_vc_ldp"}
    assert {s.get("x-scope") for s in answer_schemas(contract, "/records/{recordId}")} == set(claims)
    for scope, names in claims.items():
        schema = scope_schema(contract, "/records/{recordId}", scope)
        assert set(schema["required"]) == set(schema["properties"]) == names, (scope, names ^ set(schema["properties"]))
        for name, prop in schema["properties"].items():
            want = "array" if name == "courses" else "string"
            assert resolve(prop, contract).get("type") == want, (scope, name)
        assert set(resolve(schema["propertyNames"], contract)["not"]["enum"]) == FORBIDDEN_KEYS, scope
    assert "courseList" in claims["ait_transcript_vc_ldp"]  # served by the Adapter now, no longer derived


def test_the_contract_mode_passes_against_the_mock() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        get = host_get(csv_path)
        for sub in ("ait-2026-0001", "st123456"):  # st123456: the SIS test student, so issuer-dev can gate it
            check_contract(get, sub, "ait_transcript_vc_ldp")
        check_contract(get, "ait-2026-0001", "openid ait_transcript_vc_ldp")  # the token's scope claim, whole
        assert get("/records/st123456/eligibility?scope=ait_transcript_vc_ldp") == (200, {
            "holds": [], "conferralStatus": "Conferred", "balance": "0.00"})  # eligible: it passes every check
        csv_path.write_bytes(ROSTER.read_bytes())
        for scope in ROSTER_SCOPES:
            check_contract(get, "hack-2026-0001", scope)


def test_the_contract_mode_accepts_an_empty_list_for_an_unknown_sub() -> None:
    """The contract (openapi.yaml, `GET /records`) says an empty list means the same as a 404."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        mock = host_get(csv_path)

        def get(path: str):
            status, body = mock(path)
            return (200, []) if path.startswith("/records?") and status == 404 else (status, body)

        check_contract(get, "ait-2026-0001", "ait_transcript_vc_ldp")


def test_the_contract_mode_fails_an_adapter_that_breaks_the_contract() -> None:
    """Each break, served by an otherwise correct Adapter (the mock), fails the contract mode."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(gc.build_rows(gc.load_students()["students"]), csv_path)
        mock = host_get(csv_path)

        def broken(path_start: str, change):
            def get(path: str):
                status, body = mock(path)
                return change(status, body) if path.startswith(path_start) else (status, body)
            return get

        record = "/records/ait-2026-0001?"
        breaks = {
            "a reserved key": broken(record, lambda s, b: (s, {**b, "id": "ait-2026-0001"})),
            "a trace key": broken(record, lambda s, b: (s, {**b, "tokenSub": "ait-2026-0001"})),
            "a claim missing": broken(record, lambda s, b: (s, {k: v for k, v in b.items() if k != "courseList"})),
            "a number for a string": broken(record, lambda s, b: (s, {**b, "totalCredits": 49.0})),
            "a null claim": broken(record, lambda s, b: (s, {**b, "notes": None})),
            "a course without a grade": broken(record, lambda s, b: (s, {**b, "courses": [
                {"term": "T", "courses": [{"no": "CS601", "title": "A", "credits": "3"}]}]})),
            "a list entry without recordId": broken("/records?sub=ait", lambda s, b: (s, [{"level": "Masters"}])),
            "an empty list for a known sub": broken("/records?sub=ait", lambda s, b: (s, [])),
            "a 200 for an unknown sub": broken("/records?sub=no-such", lambda s, b: (200, [{"recordId": "x"}])),
        }
        for name, get in breaks.items():
            try:
                check_contract(get, "ait-2026-0001", "ait_transcript_vc_ldp")
            except AssertionError:
                continue
            raise AssertionError(f"the contract mode passed an Adapter with {name}")


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
    """The Gateway's eligibility models (gateway/credential_types.py) ask nothing of the wire beyond
    adapter/openapi.yaml: each type's model's validation-mode schema, the input it accepts, against its scope's
    eligibility schema. Fields the YAML requires and no model reads are fine."""
    from pydantic import TypeAdapter

    sys.path.insert(0, str(Path(__file__).parent.parent / "gateway"))
    import credential_types as ct

    spec = load_contract()
    components = spec["components"]["schemas"]
    for t in ct.REGISTRY.values():
        schema = TypeAdapter(t.eligibility).json_schema(mode="validation")
        answer = scope_schema(spec, "/records/{recordId}/eligibility", t.scope)
        assert drift(schema, answer, schema.get("$defs", {}), components, f"{t.scope} eligibility") == []
    # The comparison can fail: a field the YAML does not require, a wire type it does not give, and a minimum length
    # it does not state.
    assert drift({"type": "object", "required": ["x"]}, {"type": "object"}, {}, {}, "m") != []
    assert drift({"type": "string"}, {"$ref": "#/components/schemas/Term"}, {}, components, "m") != []
    assert drift({"type": "string", "minLength": 1}, {"type": "string"}, {}, {}, "m") != []


def java_string_set(source: str, name: str) -> set[str]:
    """The strings of the Java constant `name = Set.of("a", "b", ...)` in `source`."""
    (body,) = re.findall(rf"\b{name}\s*=\s*Set\.of\(([^)]*)\)", source)
    return set(re.findall(r'"([^"]*)"', body))


def test_the_plugin_refuses_exactly_the_keys_openapi_yaml_forbids() -> None:
    """The Data-provider plugin's FORBIDDEN_KEYS are the keys openapi.yaml's RecordKey excludes. The plugin's build
    mounts only plugin/, so its JUnit tests cannot read the contract; this host test holds the two equal."""
    contract = set(load_contract()["components"]["schemas"]["RecordKey"]["not"]["enum"])
    assert java_string_set(PLUGIN.read_text(encoding="utf-8"), "FORBIDDEN_KEYS") == contract
    # The parse reads a set split over lines, as the plugin writes it, so a key the plugin misses fails the test.
    assert java_string_set('FORBIDDEN_KEYS = Set.of("id",\n        "_issuer")', "FORBIDDEN_KEYS") == {"id", "_issuer"}


def getter(base: str):
    """`get(path)` over HTTP at `base`. Only a 200's body is read as JSON (a 404's is not part of the contract)."""
    import httpx

    def get(path: str) -> tuple[int, object]:
        r = httpx.get(base + path, timeout=10)
        return r.status_code, r.json() if r.status_code == 200 else r.text
    return get


def run_live(url: str, csv_path: Path, copy_url: str, copy_csv: Path) -> None:
    import time

    import httpx

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
    if sys.argv[1:2] == ["--contract"] and len(sys.argv) == 5:
        check_contract(getter(sys.argv[2].rstrip("/")), sys.argv[3], sys.argv[4])
        print(f"PASS contract at {sys.argv[2]} for {sys.argv[4]}")
    elif sys.argv[1:2] == ["--record-claims"] and len(sys.argv) == 3:
        print("\n".join(scope_schema(load_contract(), "/records/{recordId}", sys.argv[2])["required"]))
    elif len(sys.argv) == 5:
        run_live(sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
        print(f"PASS adapter at {sys.argv[1]}, edit case at {sys.argv[3]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
