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
                                                          the contract mode, against any Adapter: URL is the
                                                          record URL as CERTIFY_RECORD_URL sets it, `{sub}`
                                                          included; SUB's record against SCOPE's record schema
                                                          (no reserved key), and a 404 for an unknown sub.
                                                          check_contract(get, url, sub, scope) is the same
                                                          in-process
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

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))

AIT_ROSTER = REPO_ROOT / "deploy" / "ait" / "adapter" / "student_identity_data.csv"
ROSTER = REPO_ROOT / "deploy" / "hackathon" / "adapter" / "student_identity_data.csv"
# The scopes the hackathon Installation enables: both read the roster row.
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

    # An unknown sub is a 404 on every path.
    for path in ("/student/nobody/transcript", "/student/nobody/eligibility"):
        assert get(path)[0] == 404, path


def check_edit(get, csv_path: Path) -> None:
    """The file is read again on every request: an edited value of csv_path is served at once. Rewrites csv_path
    and puts it back, so csv_path must be a copy, never an installation's file."""
    rows = read_rows(csv_path)
    edited = "balance" if "balance" in rows[0] else "teamId"
    first = rows[0]["id"]
    original = csv_path.read_bytes()
    path = f"/student/{first}/eligibility"
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
        # The record: every column but the id and the eligibility columns, the generator's courseList included.
        status, body = get(f"/student/{sub}/transcript")
        assert status == 200 and "id" not in body and not set(ELIGIBILITY) & body.keys(), (sub, status, body)
        assert body["courseList"] == row["courseList"] and "\n" in body["courseList"], sub
        assert isinstance(body["courses"], list) and body["courses"][0]["term"] and body["courses"][0]["courses"][0]["no"]
        # Every other cell exactly as written, a multiline one included: the adapter neither escapes nor un-escapes.
        verbatim = {k: v for k, v in row.items() if k not in {"id", "courses", *ELIGIBILITY}}
        assert body == {**verbatim, "courses": json.loads(row["courses"])}, sub
        assert get(f"/student/{sub}/eligibility") == (200, {
            "holds": json.loads(row["holds"]), "conferralStatus": row["conferralStatus"],
            "balance": row["balance"]}), sub


def check_roster_rows(get, rows: list[dict]) -> None:
    """A roster (the hackathon installation): the record and the eligibility paths both serve the row's columns."""
    for row in rows:
        sub = row["id"]
        columns = {k: v for k, v in row.items() if k != "id"}
        assert get(f"/student/{sub}/transcript") == (200, columns), sub
        assert get(f"/student/{sub}/eligibility") == (200, columns), sub


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


def test_mock_adapter_on_the_ait_roster() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(AIT_ROSTER.read_bytes())
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
        assert get("/student/hack-2026-0001/transcript")[1]["teamName"] == "Sandbox Pioneers"
        assert get("/student/hack-2026-0002/transcript")[1]["teamName"] == 'Chain "Gang"\nof two'
        # The participant without a team is on the roster, with an empty teamId.
        assert get("/student/hack-2026-0003/eligibility")[1]["teamId"] == ""


OPENAPI = Path(__file__).parent / "openapi.yaml"
PLUGIN = REPO_ROOT / "src/issuer/src/main/java/asia/mosip/issuer/plugin/IssuerDataProviderPlugin.java"
# Certify's reserved keys and the plugin's trace keys: no record may carry one (spec, "Shaping the data map").
FORBIDDEN_KEYS = {"id", "_holderId", "_issuer", "validFrom", "validUntil", "credentialStatus", "tokenSub", "tokenClientId"}


def load_contract() -> dict:
    import yaml

    return yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))


def resolve(schema: dict, contract: dict) -> dict:
    while "$ref" in schema:
        schema = contract["components"]["schemas"][schema["$ref"].rsplit("/", 1)[1]]
    return schema


ELIGIBILITY_PATH = "/student/{sub}/eligibility"
# The record URL both Installations' Certify reads on the mock, as a path.
TRANSCRIPT_URL = "/student/{sub}/transcript"
CREDENTIAL_SCHEMA = REPO_ROOT / "docs" / "schemas" / "ait-transcript-credential.v2.schema.json"


def answer_schemas(contract: dict, path: str) -> list[dict]:
    """The schemas the contract gives for a 200 at `path`, resolved: one, or each of a oneOf."""
    schema = contract["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    return [resolve(s, contract) for s in schema.get("oneOf", [schema])]


def record_schemas(contract: dict) -> list[dict]:
    """Every record schema: the answers of every path but the eligibility one."""
    return [s for path in contract["paths"] if path != ELIGIBILITY_PATH for s in answer_schemas(contract, path)]


def scope_schema(schemas: list[dict], scope: str) -> dict:
    """The one of `schemas` for the token scope `scope` (space-separated scopes), by `x-scope`."""
    (schema,) = [s for s in schemas if s.get("x-scope") in scope.split()] or [None]
    assert schema is not None, f"openapi.yaml names no schema for scope {scope}"
    return schema


def record_schema(contract: dict, scope: str) -> dict:
    return scope_schema(record_schemas(contract), scope)


def eligibility_schema(contract: dict, scope: str) -> dict:
    return scope_schema(answer_schemas(contract, ELIGIBILITY_PATH), scope)


TYPES = {"string": str, "array": list, "object": dict, "boolean": bool, "number": (int, float)}


def violations(value, schema: dict, contract: dict, where: str) -> list[str]:
    """How `value` breaks `schema`, for the keywords openapi.yaml uses on answers: type (one name or a list of them),
    required, properties, additionalProperties (a schema, or false), items, propertyNames, enum, not, minLength and
    pattern. A pattern must match the whole value: the contract's patterns are anchored, and Python's `$` would also
    match before a final newline, which ECMA-262's (JSON Schema's) does not."""
    schema = resolve(schema, contract)
    types = schema.get("type", [])
    types = [types] if isinstance(types, str) else types
    if types and not any(isinstance(value, TYPES[t]) for t in types):
        return [f"{where}: {value!r} is not a {' or '.join(types)}"]
    found = []
    if "enum" in schema and value not in schema["enum"]:
        found.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "not" in schema and not violations(value, schema["not"], contract, where):
        found.append(f"{where}: {value!r} is excluded by openapi.yaml")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        found.append(f"{where}: {value!r} is too short")
    if isinstance(value, str) and "pattern" in schema and not re.fullmatch(schema["pattern"], value):
        found.append(f"{where}: {value!r} does not match {schema['pattern']}")
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
            elif schema.get("additionalProperties") is False:
                found.append(f"{where}.{key}: a key openapi.yaml does not allow here")
            elif "additionalProperties" in schema:
                found += violations(item, schema["additionalProperties"], contract, f"{where}.{key}")
    return found


def check_contract(get, url: str, sub: str, scope: str) -> None:
    """The contract mode: any Adapter, through `get(url)` -> (status, body), against openapi.yaml for one known
    `sub` and one token `scope`. `url` is the record URL as the plugin is set with it, `{sub}` included, which this
    fills in as the plugin does. The record follows the scope's record schema, so it holds every claim, no reserved or
    trace key, no extra field but a scalar, and a `courses` that is an array; an unknown sub is a 404."""
    from urllib.parse import quote

    contract = load_contract()
    status, record = get(url.replace("{sub}", quote(sub, safe="")))
    assert status == 200, f"the record of {sub}: {status} {record!r}"
    problems = violations(record, record_schema(contract, scope), contract, "record")
    if "courses" in record and not isinstance(record["courses"], list):  # the plugin's unquoted slot, in any scope
        problems.append(f"record.courses: {record['courses']!r} is not an array")
    assert not problems, f"the record of {sub}: {problems}"

    unknown = "no-such-student-" + os.urandom(4).hex()
    status, body = get(url.replace("{sub}", unknown))
    assert status == 404, f"the record of an unknown sub: {status} {body!r}, not a 404"


def template_claims() -> dict[str, set[str]]:
    """Each Installation's Certify templates, by scope: the names they substitute, less the ones Certify sets."""
    import base64

    found = {}
    for seed in (REPO_ROOT / "deploy").glob("*/certify_seed.sql"):
        for row in seed.read_text(encoding="utf-8").split("INSERT INTO certify.credential_config")[1:]:
            (scope,) = re.findall(r"'([a-z_]+_vc_ldp)'", row)
            (template,) = re.findall(r"'(ewo[A-Za-z0-9+/=]+)'", row)
            names = set(re.findall(r"\$\{([^}]+)\}", base64.b64decode(template).decode()))
            found[scope] = {n for n in names if n not in {"_issuer", "_holderId", "validFrom", "validUntil"}
                            and not n.startswith("credentialStatus.")}
    return found


def test_every_record_schema_lists_exactly_the_claims_its_template_substitutes() -> None:
    """The record paths name one record schema per scope, and each lists exactly the claims its Certify template
    substitutes, every one required, a string but `courses`, and no reserved or trace key."""
    contract = load_contract()
    claims = template_claims()
    assert set(claims) == {"ait_transcript_vc_ldp", "developer_passport_vc_ldp", "achievement_certificate_vc_ldp"}
    assert sorted(s.get("x-scope") for s in record_schemas(contract)) == sorted(claims)
    for scope, names in claims.items():
        schema = record_schema(contract, scope)
        assert set(schema["required"]) == set(schema["properties"]) == names, (scope, names ^ set(schema["properties"]))
        for name, prop in schema["properties"].items():
            want = "array" if name == "courses" else "string"
            assert resolve(prop, contract).get("type") == want, (scope, name)
        assert set(resolve(schema["propertyNames"], contract)["not"]["enum"]) == FORBIDDEN_KEYS, scope
    assert "courseList" in claims["ait_transcript_vc_ldp"]  # served by the Adapter now, no longer derived


def test_the_contract_mode_passes_against_the_mock() -> None:
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(AIT_ROSTER.read_bytes())
        get = host_get(csv_path)
        for sub in ("ait-2026-0001", "st123456"):  # st123456: the SIS test student, so issuer-dev can gate it
            check_contract(get, TRANSCRIPT_URL, sub, "ait_transcript_vc_ldp")
        check_contract(get, TRANSCRIPT_URL, "ait-2026-0001", "openid ait_transcript_vc_ldp")  # the scope claim, whole
        assert get("/student/st123456/eligibility") == (200, {
            "holds": [], "conferralStatus": "Conferred", "balance": "0.00"})  # eligible: it passes every check
        csv_path.write_bytes(ROSTER.read_bytes())
        for scope in ROSTER_SCOPES:
            check_contract(get, TRANSCRIPT_URL, "hack-2026-0001", scope)


def test_the_contract_mode_fails_an_adapter_that_breaks_the_contract() -> None:
    """Each break, served by an otherwise correct Adapter (the mock), fails the contract mode."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(AIT_ROSTER.read_bytes())
        mock = host_get(csv_path)

        def broken(path_start: str, change):
            def get(path: str):
                status, body = mock(path)
                return change(status, body) if path.startswith(path_start) else (status, body)
            return get

        record = "/student/ait-2026-0001/"
        term = {"term": "T", "credits": "3", "gpa": "4.00", "cumGpa": "4.00"}
        course = {"no": "CS601", "title": "A", "lec": "3", "lab": "0", "credits": "3", "grade": "A"}
        breaks = {
            "a reserved key": broken(record, lambda s, b: (s, {**b, "id": "ait-2026-0001"})),
            "a trace key": broken(record, lambda s, b: (s, {**b, "tokenSub": "ait-2026-0001"})),
            "a claim missing": broken(record, lambda s, b: (s, {k: v for k, v in b.items() if k != "courseList"})),
            "a number for a string": broken(record, lambda s, b: (s, {**b, "totalCredits": 49.0})),
            "a null claim": broken(record, lambda s, b: (s, {**b, "notes": None})),
            "an extra field that is an array of objects": broken(record, lambda s, b: (s, {
                **b, "advisors": [{"name": "Dr. A"}]})),
            "an extra field that is an object": broken(record, lambda s, b: (s, {**b, "committee": {"chair": "A"}})),
            "courses that is not an array": broken(record, lambda s, b: (s, {**b, "courses": "CS601"})),
            "a course without a grade": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "courses": [{k: v for k, v in course.items() if k != "grade"}]}]})),
            "a course without its lecture hours": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "courses": [{k: v for k, v in course.items() if k != "lec"}]}]})),
            "a term without its GPA": broken(record, lambda s, b: (s, {**b, "courses": [
                {**{k: v for k, v in term.items() if k != "gpa"}, "courses": [course]}]})),
            "a date that is not YYYY-MM-DD": broken(record, lambda s, b: (s, {**b, "dateGraduation": "31/08/2026"})),
            "a year that is not four digits": broken(record, lambda s, b: (s, {**b, "yearAwarded": "'23"})),
            "an empty registration number": broken(record, lambda s, b: (s, {**b, "registrationNo": ""})),
            "credits with a unit": broken(record, lambda s, b: (s, {**b, "totalCredits": "49 credits"})),
            "a GPA with a decimal comma": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "gpa": "3,67", "courses": [course]}]})),
            "empty lab hours": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "courses": [{**course, "lab": ""}]}]})),
            "a date with a trailing newline": broken(record, lambda s, b: (s, {**b, "dateGraduation": "2026-08-31\n"})),
            "a course with a key the credential schema does not name": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "courses": [{**course, "remark": "late"}]}]})),
            "a term with a key the credential schema does not name": broken(record, lambda s, b: (s, {**b, "courses": [
                {**term, "standing": "Good", "courses": [course]}]})),
            "a 200 for an unknown sub": broken("/student/no-such", lambda s, b: (200, b)),
        }
        check_contract(broken(record, lambda s, b: (s, {**b, "courses": [{**term, "courses": [course]}]})),
                       TRANSCRIPT_URL, "ait-2026-0001", "ait_transcript_vc_ldp")  # the term and course above pass
        for name, get in breaks.items():
            try:
                check_contract(get, TRANSCRIPT_URL, "ait-2026-0001", "ait_transcript_vc_ldp")
            except AssertionError:
                continue
            raise AssertionError(f"the contract mode passed an Adapter with {name}")


def test_the_contract_mode_fails_a_courses_that_is_not_an_array_in_any_scope() -> None:
    """The plugin refuses a non-array `courses` whatever the scope, though the roster's record schemas do not name it."""
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        csv_path.write_bytes(ROSTER.read_bytes())
        mock = host_get(csv_path)

        def get(path: str):
            status, body = mock(path)
            return (status, {**body, "courses": "CS601"}) if path.startswith("/student/hack") else (status, body)

        try:
            check_contract(get, TRANSCRIPT_URL, "hack-2026-0001", ROSTER_SCOPES[0])
        except AssertionError:
            return
        raise AssertionError("the contract mode passed a roster record whose courses is a string")


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

    sys.path.insert(0, str(REPO_ROOT / "src" / "gateway"))
    import credential_types as ct

    spec = load_contract()
    components = spec["components"]["schemas"]
    for t in ct.REGISTRY.values():
        schema = TypeAdapter(t.eligibility).json_schema(mode="validation")
        answer = eligibility_schema(spec, t.scope)
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


def test_the_plugin_refuses_exactly_the_structured_fields_openapi_yaml_forbids() -> None:
    """The plugin's `shape` refuses an object or array at the top of a record except the one named by its COURSES
    constant, which must be an array. openapi.yaml must say the same: in every record schema, only that name is
    declared an array, and any other field is a string, number or boolean (`additionalProperties`)."""
    contract = load_contract()
    source = PLUGIN.read_text(encoding="utf-8")
    (courses,) = re.findall(r'\bCOURSES\s*=\s*"([^"]*)"', source)
    for scope in template_claims():
        schema = record_schema(contract, scope)
        arrays = {n for n, p in schema["properties"].items() if resolve(p, contract).get("type") == "array"}
        assert arrays <= {courses}, (scope, arrays)
        extra = resolve(schema["additionalProperties"], contract)
        assert extra["type"] == ["string", "number", "boolean"], (scope, extra)
    # The parse reads the constant as the plugin writes it, so a rename in the plugin fails the test.
    assert re.findall(r'\bCOURSES\s*=\s*"([^"]*)"', 'private static final String COURSES = "terms";') == ["terms"]


def shape_of(schema: dict, resolve_ref, top: bool = True) -> object:
    """A schema's field tree, for comparing two schema languages: an object's required names, each to its own tree,
    an array's item tree, else the type name, the pattern and the minLength (None without one). Below the top, an object's tree also
    says whether it allows other keys: the template picks the top-level claims it names, but `courses` goes into the
    credential verbatim, so a key its terms or courses do not name would be signed."""
    schema = resolve_ref(schema)
    if schema.get("type") == "object":
        tree = {name: shape_of(schema["properties"][name], resolve_ref, False) for name in schema.get("required", [])}
        if not top:
            tree[None] = schema.get("additionalProperties", True)  # None: no field can have that name
        return tree
    if schema.get("type") == "array":
        return [shape_of(schema["items"], resolve_ref, False)]
    return schema.get("type"), schema.get("pattern"), schema.get("minLength")


def test_the_transcript_record_is_the_credential_schemas_subject_less_the_holder() -> None:
    """The two master files agree: openapi.yaml's TranscriptRecord requires exactly the claims, terms and courses that
    docs/schemas/ait-transcript-credential.v2.schema.json requires of the signed credentialSubject, with the same
    types and formats (patterns and minimum lengths), and terms and courses that allow no other key, except the holder's `id`, which
    Certify sets."""
    contract = load_contract()
    credential = json.loads(CREDENTIAL_SCHEMA.read_text(encoding="utf-8"))

    def credential_ref(schema: dict) -> dict:
        while "$ref" in schema:
            schema = credential["$defs"][schema["$ref"].rsplit("/", 1)[1]]
        return schema

    subject = shape_of(credential["$defs"]["transcript"], credential_ref)
    del subject["id"]
    assert shape_of(record_schema(contract, "ait_transcript_vc_ldp"), lambda s: resolve(s, contract)) == subject
    # The comparison sees a nested field: a course field the record lacks fails it.
    narrower = {"type": "object", "required": ["courses"], "properties": {"courses": {"type": "array", "items": {
        "type": "object", "required": ["no"], "properties": {"no": {"type": "string"}}}}}}
    assert shape_of(narrower, lambda s: s) != {"courses": [{"no": "string", "title": "string"}]}
    # It also sees a minimum length one file has and the other lacks.
    assert shape_of({"type": "string", "minLength": 1}, lambda s: s) != shape_of({"type": "string"}, lambda s: s)


def test_the_handovers_privacy_section_names_every_claim_the_ait_ledger_indexes() -> None:
    """Certify logs every value its ledger indexes (LedgerUtils, at INFO), so the list on the handover's "Certify also
    logs it" line (docs/project/issuer-v0.1/sis-adapter-handover.md) is the ait Installation's indexed mappings."""
    properties = (REPO_ROOT / "deploy" / "ait" / "certify-installation.properties").read_text(encoding="utf-8")
    indexed = set(re.findall(r"^mosip\.certify\.indexed-mappings\.(\w+)=", properties, re.M))
    page = (REPO_ROOT / "docs" / "project" / "issuer-v0.1" / "sis-adapter-handover.md").read_text(encoding="utf-8")
    line = next(line for line in page.splitlines() if line.startswith("- **Certify also logs it, and more.**"))
    named = set(re.findall(r"`(\w+)`", line.split(" in plain text: ", 1)[1].split(". ", 1)[0]))
    assert indexed and named == indexed, (named, indexed)


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
        check_contract(getter(""), sys.argv[2], sys.argv[3], sys.argv[4])
        print(f"PASS contract at {sys.argv[2]} for {sys.argv[4]}")
    elif sys.argv[1:2] == ["--record-claims"] and len(sys.argv) == 3:
        print("\n".join(record_schema(load_contract(), sys.argv[2])["required"]))
    elif len(sys.argv) == 5:
        run_live(sys.argv[1], Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
        print(f"PASS adapter at {sys.argv[1]}, edit case at {sys.argv[3]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
