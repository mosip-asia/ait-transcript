"""Tests for the Gateway's POST /issuances (contracts.md section 2a) with the mock adapter beside it.

Run: python3 gateway/tests/test_issuances.py                     on the host, no Docker: the Gateway and the mock
                                                                 adapter in-process, the issuance store faked; every
                                                                 installation's personas on its CSV (generated for
                                                                 ait, the committed roster for hackathon)
     python3 gateway/tests/test_issuances.py URL CSV FIXTURES    against the running containers (smoke.sh), inside
                                                                 the gateway image: the token and the database URL
                                                                 come from the service's environment, CSV is the
                                                                 adapter's file, FIXTURES the installation's smoke.json
Host mode needs gateway/requirements.txt and portal/requirements.txt.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1]
# The Gateway's modules (the image has them too); data/'s generator in host mode only.
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(GATEWAY_DIR.parent / "data"))

import credential_types as ct  # noqa: E402

INSTALLATIONS = GATEWAY_DIR.parent / "installations"
ROSTER = INSTALLATIONS / "hackathon" / "adapter" / "student_identity_data.csv"
# The host-mode CSV per installation: None is the one generated from data/students.json.
HOST_CSV = {"ait": None, "hackathon": ROSTER}
# The edge cases below run on the AIT installation.
SCOPE = "ait_transcript_vc_ldp"
ELIGIBLE = "ait-2026-0001"


def stringify(claims: dict) -> dict:
    """The plugin's rule (contracts.md 2a): every top-level object or array becomes its JSON text."""
    return {k: json.dumps(v, separators=(",", ":"), ensure_ascii=False) if isinstance(v, (dict, list)) else v
            for k, v in claims.items()}


def escaped(row: dict, names) -> dict:
    """The Gateway's 200 body after stringify, for a CSV row holding the values verbatim: every claim escaped for the
    quoted template, `courses` (JSON text, which the template embeds unquoted) as it is."""
    return {k: row[k] if k == "courses" else ct.escape_vc_quoted_claim(row[k]) for k in names}


def claim_names(ctype: ct.CredentialType) -> list[str]:
    """The claims a type answers: its record model's fields, then the claims it derives."""
    return [*ctype.record.model_fields, *ctype.derived]


def assert_only_failing(checks: list[dict], failing: str | list[str], ctype: ct.CredentialType) -> None:
    """The checks of a 403 body exactly: every check of the type in order, the failing one(s) failed with a reason,
    every other check of the type passed without one."""
    failing = [failing] if isinstance(failing, str) else failing
    names = [check.name for check in ctype.checks]
    assert set(failing) <= set(names), (failing, names)
    assert [c["check"] for c in checks] == names, checks
    assert [c["check"] for c in checks if c["passed"] is False] == [n for n in names if n in failing], checks
    assert [c for c in checks if c["passed"] is not False] == [{"check": n, "passed": True} for n in names if n not in failing], checks
    assert all(isinstance(c.get("reason"), str) and c["reason"] for c in checks if c["passed"] is False), checks


def read_fixtures(path: Path) -> list[dict]:
    """An installation's smoke.json: one entry per credential type, each with the scope, the eligible persona (or a
    list of them), the unknown persona the adapter has no record of, and each refused persona's failing check (one
    name, or a list when several fail together)."""
    return json.loads(path.read_text(encoding="utf-8"))


def eligible_personas(fixture: dict) -> list[str]:
    eligible = fixture["eligible"]
    return [eligible] if isinstance(eligible, str) else eligible


@contextmanager
def mock_adapter(csv_path: Path | None = None):
    """The mock adapter's app in-process on csv_path, else on a CSV generated from data/students.json:
    (client, csv_path, rows)."""
    import generate_csv as gc
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as td:
        if csv_path is None:
            rows = gc.build_rows(gc.load_students()["students"])
            csv_path = Path(td) / "student_identity_data.csv"
            gc.write_csv(rows, csv_path)
        else:
            with open(csv_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
        os.environ["ADAPTER_CSV"] = str(csv_path)
        # Loaded by path: the adapter's module is also called main.
        spec = importlib.util.spec_from_file_location("adapter_main", GATEWAY_DIR.parent / "adapter" / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield TestClient(module.app), csv_path, rows


def check_gateway(post, rows, token: str, csv_path: Path, fixtures: dict) -> None:
    """`post(body, token)` returns (status, body); `rows()` the issuance rows as (sub, type, scope, client_id).
    `fixtures` is one entry of the installation's smoke.json."""
    scope, personas = fixtures["scope"], eligible_personas(fixtures)
    eligible = personas[0]  # the error cases below use the first
    ctype = ct.REGISTRY[scope]
    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_rows = {r["id"]: r for r in csv.DictReader(f)}
    before = len(rows())
    request = {"sub": eligible, "scope": scope, "client_id": "wallet-demo"}

    assert post(request, None)[0] == 401
    assert post(request, "not-the-token")[0] == 401

    assert post({**request, "scope": "openid some_other_scope"}, token) == (400, {"error": "unknown_scope"})
    assert post({"sub": eligible}, token) == (400, {"error": "unknown_scope"})
    assert post({"scope": scope}, token) == (400, {"error": "invalid_access_token"})
    assert post({**request, "sub": fixtures["unknown"]}, token) == (404, {"error": "no_record"})

    for sub, failing in fixtures["refused"].items():
        status, body = post({**request, "sub": sub}, token)
        assert status == 403 and body["error"] == "checklist_failed", (sub, status, body)
        assert body["credentialType"] == ctype.credential_type, body
        assert_only_failing(body["checks"], failing, ctype)
    assert len(rows()) == before, "a refusal wrote an issuance row"

    # The scope is matched inside a space-separated claim; every other claim is ignored.
    for sub in personas:
        status, body = post({**request, "sub": sub, "scope": f"openid {scope}", "accessTokenHash": "x", "iss": "y"}, token)
        assert status == 200, (sub, status, body)
        assert stringify(body) == escaped(csv_rows[sub], claim_names(ctype)), (sub, body)
    assert rows()[before:] == [(sub, ctype.credential_type, scope, "wallet-demo") for sub in personas], rows()


def post_with(client):
    """`post(body, token)` over a TestClient or an httpx.Client with a base URL."""
    def post(body: dict, token: str | None) -> tuple[int, dict]:
        r = client.post("/issuances", json=body, headers={"Authorization": f"Bearer {token}"} if token else {})
        return r.status_code, r.json()
    return post


class FakeStore:
    def __init__(self) -> None:
        self.schema_ready = False
        self.rows: list[tuple] = []

    def ensure_schema(self) -> None:
        self.schema_ready = True

    def record(self, sub: str, credential_type: str, scope: str, client_id: str | None) -> None:
        self.rows.append((sub, credential_type, scope, client_id))


def host_gateway(adapter, store: FakeStore, enabled_scopes: tuple[str, ...] = (SCOPE,)):
    import main
    from fastapi.testclient import TestClient

    settings = main.Settings(enabled_scopes=enabled_scopes, adapter_url="http://adapter:8000",
                             auth_token="test-token", database_url="postgresql://unused")
    return TestClient(main.create_app(settings, adapter=adapter, store=store))


def enabled_scopes(installation: str) -> tuple[str, ...]:
    """GATEWAY_ENABLED_SCOPES from the installation's gateway.env."""
    lines = (INSTALLATIONS / installation / "gateway.env").read_text(encoding="utf-8").splitlines()
    return tuple(next(line for line in lines if line.startswith("GATEWAY_ENABLED_SCOPES=")).split("=", 1)[1].split())


def test_issuances_with_the_mock_adapter_for_every_installation() -> None:
    for installation, csv_path in HOST_CSV.items():
        store = FakeStore()
        fixtures = read_fixtures(INSTALLATIONS / installation / "smoke.json")
        with mock_adapter(csv_path) as (adapter, served_csv, _), \
                host_gateway(adapter, store, enabled_scopes(installation)) as client:
            assert store.schema_ready, "the schema is created on start"
            for fixture in fixtures:
                check_gateway(post_with(client), lambda: store.rows, "test-token", served_csv, fixture)


def test_starts_while_the_adapter_is_down_and_answers_gateway_error() -> None:
    import httpx

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    for handler in (refuse, broken):
        store = FakeStore()
        adapter = httpx.Client(base_url="http://adapter:8000", transport=httpx.MockTransport(handler))
        with host_gateway(adapter, store) as client:
            status, body = post_with(client)({"sub": ELIGIBLE, "scope": SCOPE}, "test-token")
        assert status == 502 and body == {"error": "gateway_error"}, (handler.__name__, status, body)
        assert store.rows == []


def answering(degrees, eligibility, record=None):
    """An adapter that answers 200 with these bodies, by path; a str body is served as it is, not as JSON."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        answer = {"degrees": degrees, "eligibility": eligibility, "transcript": record}[request.url.path.rsplit("/", 1)[1]]
        return httpx.Response(200, text=answer) if isinstance(answer, str) else httpx.Response(200, json=answer)
    return httpx.Client(base_url="http://adapter:8000", transport=httpx.MockTransport(handler))


def test_malformed_adapter_data_is_a_gateway_error_not_a_crash() -> None:
    """An answer that does not parse into the type's model, on any of the three paths, is 502 and writes no row."""
    degrees, good = [{"degreeId": "d1"}], {"holds": [], "conferralStatus": "Conferred", "balance": "0"}
    record = {**dict.fromkeys(ct.REGISTRY[SCOPE].record.model_fields, "x"), "courses": []}
    cases = [(answering(degrees, dict(good, balance="n/a")), "balance is not a number"),
             (answering(degrees, dict(good, balance=0)), "balance served as a number"),
             (answering(degrees, dict(good, conferralStatus="Revoked")), "unknown conferralStatus"),
             (answering(degrees, {"holds": []}), "eligibility lacks fields"),
             (answering(degrees, "not json"), "eligibility is not JSON"),
             (answering([{"id": "d1"}], good), "degree lacks degreeId"),
             (answering({"degreeId": "d1"}, good), "degrees is not a list"),
             (answering(degrees, good, dict(record, faculty={"k": "v"})), "a dict faculty"),
             (answering(degrees, good, dict(record, courses=[{"term": "T1"}])), "a term without courses")]
    for adapter, label in cases:
        store = FakeStore()
        with host_gateway(adapter, store) as client:
            status, body = post_with(client)({"sub": ELIGIBLE, "scope": SCOPE}, "test-token")
        assert (status, body) == (502, {"error": "gateway_error"}), (label, status, body)
        assert store.rows == []


def test_a_check_that_raises_is_a_bug_answered_500_without_a_body() -> None:
    """Not a gateway_error body: the plugin maps an answer without one to gateway_error itself."""
    import dataclasses

    import main
    from fastapi.testclient import TestClient

    broken = dataclasses.replace(ct.REGISTRY[SCOPE], checks=(ct.Check("broken", lambda e: 1 / 0),))
    settings = main.Settings(enabled_scopes=(SCOPE,), adapter_url="http://adapter:8000", auth_token="test-token",
                             database_url="postgresql://unused")
    registry, ct.REGISTRY = ct.REGISTRY, {**ct.REGISTRY, SCOPE: broken}
    try:
        app = main.create_app(settings, adapter=answering([{"degreeId": "d1"}], {"holds": [], "conferralStatus": "Conferred",
                                                                                  "balance": "0"}), store=FakeStore())
    finally:
        ct.REGISTRY = registry
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/issuances", json={"sub": ELIGIBLE, "scope": SCOPE}, headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 500 and "json" not in r.headers["content-type"], (r.status_code, r.headers, r.text)


def test_a_failed_issuance_record_is_a_gateway_error_not_a_200() -> None:
    import psycopg

    class DownStore(FakeStore):
        def record(self, *args) -> None:
            raise psycopg.OperationalError("connection refused")

    with mock_adapter() as (adapter, _, _), host_gateway(adapter, DownStore()) as client:
        status, body = post_with(client)({"sub": ELIGIBLE, "scope": SCOPE}, "test-token")
    assert (status, body) == (502, {"error": "gateway_error"}), (status, body)


def test_a_scope_the_installation_does_not_enable_is_unknown() -> None:
    with mock_adapter() as (adapter, _, _), host_gateway(adapter, FakeStore(), enabled_scopes=()) as client:
        assert post_with(client)({"sub": ELIGIBLE, "scope": SCOPE}, "test-token") == (400, {"error": "unknown_scope"})


def run_live(url: str, csv_path: Path, fixtures: list[dict]) -> None:
    import httpx
    import psycopg

    def rows() -> list[tuple]:
        with psycopg.connect(os.environ["GATEWAY_DATABASE_URL"]) as conn:
            return conn.execute("SELECT sub, credential_type, scope, client_id FROM gateway.issuances ORDER BY id").fetchall()

    with httpx.Client(base_url=url, timeout=10) as client:
        for fixture in fixtures:
            check_gateway(post_with(client), rows, os.environ["GATEWAY_AUTH_TOKEN"], csv_path, fixture)


def run_live_adapter_down(url: str, fixtures: list[dict]) -> None:
    """With the adapter stopped, an issuance request is a Gateway error (502), not a crash."""
    import httpx

    with httpx.Client(base_url=url, timeout=30) as client:
        status, body = post_with(client)({"sub": eligible_personas(fixtures[0])[0], "scope": fixtures[0]["scope"]},
                                         os.environ["GATEWAY_AUTH_TOKEN"])
    assert (status, body.get("error")) == (502, "gateway_error"), (status, body)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "adapter-down":
        run_live_adapter_down(sys.argv[2], read_fixtures(Path(sys.argv[3])))
        print(f"PASS gateway at {sys.argv[2]} answers gateway_error while the adapter is down")
    elif len(sys.argv) == 4:
        run_live(sys.argv[1], Path(sys.argv[2]), read_fixtures(Path(sys.argv[3])))
        print(f"PASS gateway at {sys.argv[1]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
