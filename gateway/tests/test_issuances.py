"""Tests for the Gateway's POST /issuances (contracts.md section 2a) with the mock adapter beside it.

Run: python3 gateway/tests/test_issuances.py            on the host, no Docker: the Gateway and the mock adapter
                                                        in-process on a generated CSV, the issuance store faked
     python3 gateway/tests/test_issuances.py URL CSV    against the running containers (smoke.sh), inside the
                                                        gateway image: the token and the database URL come from
                                                        the service's environment, CSV is the adapter's file
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
# Host mode only: the Gateway's modules and data/'s generator (the live run inside the image imports neither).
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(GATEWAY_DIR.parent / "data"))

SCOPE = "ait_transcript_vc_ldp"
ELIGIBLE = "ait-2026-0001"
FAILING = {"ait-2026-0002": "no_holds", "ait-2026-0003": "conferred", "ait-2026-0004": "zero_balance"}
# CSV columns that are not template claims: the identity and the adapter's own columns (data/generate_csv.py).
NOT_CLAIMS = {"id", "level", "holds", "conferralStatus", "balance"}


def stringify(claims: dict) -> dict:
    """The plugin's rule (contracts.md 2a): every top-level object or array becomes its JSON text."""
    return {k: json.dumps(v, separators=(",", ":"), ensure_ascii=False) if isinstance(v, (dict, list)) else v
            for k, v in claims.items()}


def assert_only_failing(checks: list[dict], failing: str) -> None:
    """Every transcript check listed in order; `reason` on the failing one only."""
    assert [c["check"] for c in checks] == ["no_holds", "conferred", "zero_balance"], checks
    for c in checks:
        if c["check"] == failing:
            assert c["passed"] is False and isinstance(c["reason"], str) and c["reason"], c
        else:
            assert c == {"check": c["check"], "passed": True}, c


@contextmanager
def mock_adapter():
    """The mock adapter's app in-process on a CSV generated from data/students.json: (client, csv_path, rows)."""
    import generate_csv as gc
    from fastapi.testclient import TestClient

    rows = gc.build_rows(gc.load_students()["students"])
    with tempfile.TemporaryDirectory() as td:
        csv_path = Path(td) / "student_identity_data.csv"
        gc.write_csv(rows, csv_path)
        os.environ["ADAPTER_CSV"] = str(csv_path)
        # Loaded by path: the adapter's module is also called main.
        spec = importlib.util.spec_from_file_location("adapter_main", GATEWAY_DIR.parent / "adapter" / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield TestClient(module.app), csv_path, rows


def check_gateway(post, rows, token: str, csv_path: Path) -> None:
    """`post(body, token)` returns (status, body); `rows()` the issuance rows as (sub, type, scope, client_id)."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        csv_row = next(r for r in csv.DictReader(f) if r["id"] == ELIGIBLE)
    before = len(rows())
    request = {"sub": ELIGIBLE, "scope": SCOPE, "client_id": "wallet-demo"}

    assert post(request, None)[0] == 401
    assert post(request, "not-the-token")[0] == 401

    assert post({**request, "scope": "openid some_other_scope"}, token) == (400, {"error": "unknown_scope"})
    assert post({"sub": ELIGIBLE}, token) == (400, {"error": "unknown_scope"})
    assert post({"scope": SCOPE}, token) == (400, {"error": "invalid_access_token"})
    assert post({**request, "sub": "nobody"}, token) == (404, {"error": "no_record"})

    for sub, failing in FAILING.items():
        status, body = post({**request, "sub": sub}, token)
        assert status == 403 and body["error"] == "checklist_failed", (sub, status, body)
        assert body["credentialType"] == "AitTranscriptCredential", body
        assert_only_failing(body["checks"], failing)
    assert len(rows()) == before, "a refusal wrote an issuance row"

    # The scope is matched inside a space-separated claim; every other claim is ignored.
    status, body = post({**request, "scope": f"openid {SCOPE}", "accessTokenHash": "x", "iss": "y"}, token)
    assert status == 200, (status, body)
    assert stringify(body) == {k: v for k, v in csv_row.items() if k not in NOT_CLAIMS}, body
    assert rows()[before:] == [(ELIGIBLE, "AitTranscriptCredential", SCOPE, "wallet-demo")], rows()


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


def test_issuances_with_the_mock_adapter() -> None:
    store = FakeStore()
    with mock_adapter() as (adapter, csv_path, _), host_gateway(adapter, store) as client:
        assert store.schema_ready, "the schema is created on start"
        check_gateway(post_with(client), lambda: store.rows, "test-token", csv_path)


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


def run_live(url: str, csv_path: Path) -> None:
    import httpx
    import psycopg

    def rows() -> list[tuple]:
        with psycopg.connect(os.environ["GATEWAY_DATABASE_URL"]) as conn:
            return conn.execute("SELECT sub, credential_type, scope, client_id FROM gateway.issuances ORDER BY id").fetchall()

    with httpx.Client(base_url=url, timeout=10) as client:
        check_gateway(post_with(client), rows, os.environ["GATEWAY_AUTH_TOKEN"], csv_path)


def run_live_adapter_down(url: str) -> None:
    """With the adapter stopped, an issuance request is a Gateway error (502), not a crash."""
    import httpx

    with httpx.Client(base_url=url, timeout=30) as client:
        status, body = post_with(client)({"sub": ELIGIBLE, "scope": SCOPE}, os.environ["GATEWAY_AUTH_TOKEN"])
    assert (status, body.get("error")) == (502, "gateway_error"), (status, body)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "adapter-down":
        run_live_adapter_down(sys.argv[2])
        print(f"PASS gateway at {sys.argv[2]} answers gateway_error while the adapter is down")
    elif len(sys.argv) == 3:
        run_live(sys.argv[1], Path(sys.argv[2]))
        print(f"PASS gateway at {sys.argv[1]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
