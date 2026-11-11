"""Tests for the Gateway's POST /evaluations, the read-only Checklist evaluation, with the mock adapter beside it.

Run: python3 gateway/tests/test_evaluations.py                         on the host, no Docker: the Gateway and the
                                                                       mock adapter in-process; every installation's
                                                                       personas on its CSV (generated for ait, the
                                                                       committed roster for hackathon)
     python3 gateway/tests/test_evaluations.py URL FIXTURES            against the running containers (issuer-checks.sh),
                                                                       inside the gateway image: the token comes from
                                                                       the service's environment, FIXTURES is the
                                                                       installation's smoke.json
     python3 gateway/tests/test_evaluations.py adapter-down URL FIXTURES   the same, with the adapter stopped: 502
Host mode needs gateway/requirements.txt and portal/requirements.txt.

A persona is the `sub` of its request: the mock adapter's CSV row id, which is the sign-in identity.
test_credential_types.py imports the helpers above the tests.
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
REPO_ROOT = GATEWAY_DIR.parent if (GATEWAY_DIR.parent / "deploy").exists() else GATEWAY_DIR.parent.parent
sys.path.insert(0, str(GATEWAY_DIR))

import credential_types as ct  # noqa: E402

INSTALLATIONS = REPO_ROOT / "deploy"
AIT_ROSTER = INSTALLATIONS / "ait" / "adapter" / "student_identity_data.csv"
ROSTER = INSTALLATIONS / "hackathon" / "adapter" / "student_identity_data.csv"
HOST_CSV = {"ait": AIT_ROSTER, "hackathon": ROSTER}
# The edge cases run on the AIT installation.
SCOPE = "ait_transcript_vc_ldp"
ELIGIBLE = "ait-2026-0001"
ELIGIBILITY_URL = "http://adapter:8000/student/{sub}/eligibility"
TOKEN = "test-token"


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


def enabled_scopes(installation: str) -> tuple[str, ...]:
    """GATEWAY_ENABLED_SCOPES from the installation's gateway.env."""
    lines = (INSTALLATIONS / installation / "gateway.env").read_text(encoding="utf-8").splitlines()
    return tuple(next(line for line in lines if line.startswith("GATEWAY_ENABLED_SCOPES=")).split("=", 1)[1].split())


@contextmanager
def mock_adapter(csv_path: Path | None = None):
    """The mock adapter's app in-process on csv_path, else on the AIT roster CSV:
    (client, csv_path, rows)."""
    from fastapi.testclient import TestClient

    if csv_path is None:
        csv_path = AIT_ROSTER
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    os.environ["ADAPTER_CSV"] = str(csv_path)
    # Loaded by path: the adapter's module is also called main.
    spec = importlib.util.spec_from_file_location("adapter_main", REPO_ROOT / "mock" / "adapter" / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield TestClient(module.app), csv_path, rows


def gateway_app(adapter, enabled_scopes: tuple[str, ...] = (SCOPE,)):
    import main

    settings = main.Settings(enabled_scopes=enabled_scopes, eligibility_url=ELIGIBILITY_URL, auth_token=TOKEN)
    return main.create_app(settings, adapter=adapter)


def host_gateway(adapter, enabled_scopes: tuple[str, ...] = (SCOPE,)):
    from fastapi.testclient import TestClient

    return TestClient(gateway_app(adapter, enabled_scopes))


# --- POST /evaluations ----------------------------------------------------------------------------------------


def evaluation(sub: str, scope: str = SCOPE) -> dict:
    """The request body: the persona is the sub."""
    return {"sub": sub, "scope": scope}


def evaluate_with(client):
    """`evaluate(body, token)` returns (status, body) over a TestClient or an httpx.Client with a base URL; `body` is
    sent as JSON unless it is bytes."""
    def evaluate(body, token: str | None) -> tuple[int, dict]:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if isinstance(body, bytes):
            r = client.post("/evaluations", content=body, headers={**headers, "Content-Type": "application/json"})
        else:
            r = client.post("/evaluations", json=body, headers=headers)
        return r.status_code, r.json()
    return evaluate


def check_personas(evaluate, token: str, fixture: dict) -> None:
    """Every persona of one smoke.json entry: 200 with every check passed for the eligible, 403 checklist_failed with
    exactly the failing checks for the refused, 404 no_record for the unknown."""
    scope = fixture["scope"]
    ctype = ct.REGISTRY[scope]
    every_check_passed = [{"check": check.name, "passed": True} for check in ctype.checks]

    for sub in eligible_personas(fixture):
        # The scope is matched inside a space-separated scope claim.
        answer = evaluate(evaluation(sub, f"openid {scope}"), token)
        assert answer == (200, {"credentialType": ctype.credential_type, "checks": every_check_passed}), (sub, answer)

    for sub, failing in fixture["refused"].items():
        status, body = evaluate(evaluation(sub, scope), token)
        assert status == 403 and body.keys() == {"error", "credentialType", "checks"}, (sub, status, body)
        assert body["error"] == "checklist_failed" and body["credentialType"] == ctype.credential_type, (sub, body)
        assert_only_failing(body["checks"], failing, ctype)

    assert evaluate(evaluation(fixture["unknown"], scope), token) == (404, {"error": "no_record"})


def check_refused_requests(evaluate, token: str, fixture: dict) -> None:
    """The refusals before any adapter call: 401 for a missing or wrong secret (whatever the body), 400
    invalid_request for a body that is not exactly the two non-empty strings, 400 unknown_scope for a scope that
    names no enabled type."""
    request = evaluation(eligible_personas(fixture)[0], fixture["scope"])
    for secret in (None, "not-the-token"):
        assert evaluate(request, secret)[0] == 401, secret
        assert evaluate({}, secret)[0] == 401, secret

    invalid = [*({k: v for k, v in request.items() if k != missing} for missing in request),
               *({**request, k: ""} for k in request),
               {**request, "scope": 1}, {**request, "sub": None},
               {**request, "client_id": "wallet-demo"},  # a token claim is not part of the request
               {**request, "recordId": request["sub"]},  # the contract before 0.5.0
               [request], b"not json"]
    for body in invalid:
        assert evaluate(body, token) == (400, {"error": "invalid_request"}), body

    for scope in ("openid some_other_scope", "openid"):
        assert evaluate({**request, "scope": scope}, token) == (400, {"error": "unknown_scope"}), scope


def test_a_request_that_is_not_authorized_or_not_well_formed_is_refused() -> None:
    with mock_adapter() as (adapter, _, _), host_gateway(adapter) as client:
        for fixture in read_fixtures(INSTALLATIONS / "ait" / "smoke.json"):
            check_refused_requests(evaluate_with(client), TOKEN, fixture)


def test_a_scope_the_installation_does_not_enable_is_unknown() -> None:
    with mock_adapter() as (adapter, _, _), host_gateway(adapter, enabled_scopes=()) as client:
        assert evaluate_with(client)(evaluation(ELIGIBLE), TOKEN) == (400, {"error": "unknown_scope"})


def adapter_answering(handler):
    import httpx

    return httpx.Client(base_url="http://adapter:8000", transport=httpx.MockTransport(handler))


def test_starts_while_the_adapter_is_down_and_answers_gateway_error() -> None:
    """The app starts with no adapter, and an adapter that is down or answers another status than 200 or 404 is a
    502 gateway_error."""
    import httpx

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "no_record"})

    for handler in (refuse, slow, broken, unavailable):
        with host_gateway(adapter_answering(handler)) as client:
            answer = evaluate_with(client)(evaluation(ELIGIBLE), TOKEN)
        assert answer == (502, {"error": "gateway_error"}), (handler.__name__, answer)


def test_starts_from_its_three_settings_and_touches_nothing_external() -> None:
    """The Gateway as Compose starts it, from the environment holding gateway.env's three settings and no database:
    it starts with nothing listening at its eligibility URL and answers 502 gateway_error."""
    import main
    from fastapi.testclient import TestClient

    settings = {"GATEWAY_ENABLED_SCOPES": SCOPE, "GATEWAY_ELIGIBILITY_URL": "http://127.0.0.1:9/student/{sub}/eligibility",
                "GATEWAY_AUTH_TOKEN": TOKEN}
    saved = {k: os.environ.pop(k, None) for k in settings}
    os.environ.update(settings)
    try:
        with TestClient(main.from_env()) as client:
            assert evaluate_with(client)(evaluation(ELIGIBLE), TOKEN) == (502, {"error": "gateway_error"})
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def eligibility_answer(answer):
    """An adapter that answers 200 with `answer` on the eligibility path only (served as it is when a str, else as
    JSON), and records the requests it got."""
    import httpx

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if not request.url.path.endswith("/eligibility"):
            return httpx.Response(404)
        return httpx.Response(200, text=answer) if isinstance(answer, str) else httpx.Response(200, json=answer)
    return adapter_answering(handler), seen


GOOD = {"holds": [], "conferralStatus": "Conferred", "balance": "0"}


def test_it_reads_only_its_eligibility_url_with_sub_as_one_path_segment() -> None:
    adapter, seen = eligibility_answer(GOOD)
    with host_gateway(adapter) as client:
        status, _ = evaluate_with(client)({"sub": "s/1 2", "scope": f"openid {SCOPE}"}, TOKEN)
    assert status == 200
    assert [(r.method, str(r.url)) for r in seen] == [("GET", "http://adapter:8000/student/s%2F1%202/eligibility")], seen


def test_an_eligibility_url_without_sub_or_not_http_stops_startup() -> None:
    import main

    for url in ("", "http://adapter:8000/student/eligibility", "adapter:8000/student/{sub}/eligibility",
                "ftp://adapter/student/{sub}/eligibility", "http:///student/{sub}/eligibility"):
        settings = main.Settings(enabled_scopes=(SCOPE,), eligibility_url=url, auth_token=TOKEN)
        try:
            main.create_app(settings)
        except ValueError as e:
            assert "GATEWAY_ELIGIBILITY_URL" in str(e), (url, e)
            continue
        raise AssertionError(f"the Gateway started with the eligibility URL {url!r}")


def test_malformed_eligibility_is_a_gateway_error_not_a_crash() -> None:
    cases = [(dict(GOOD, balance="n/a"), "balance is not a number"),
             (dict(GOOD, balance=0), "balance served as a number"),
             (dict(GOOD, conferralStatus="Revoked"), "unknown conferralStatus"),
             (dict(GOOD, holds=None), "null holds"),
             ({"holds": []}, "eligibility lacks fields"),
             ([GOOD], "eligibility is a list"),
             ("not json", "eligibility is not JSON")]
    for answer, label in cases:
        with host_gateway(eligibility_answer(answer)[0]) as client:
            result = evaluate_with(client)(evaluation(ELIGIBLE), TOKEN)
        assert result == (502, {"error": "gateway_error"}), (label, result)


def test_a_check_that_raises_is_a_bug_answered_500_without_a_body() -> None:
    """Not a gateway_error body: a caller maps an answer without one to gateway_error itself."""
    import dataclasses

    from fastapi.testclient import TestClient

    broken = dataclasses.replace(ct.REGISTRY[SCOPE], checks=(ct.Check("broken", lambda e: 1 / 0),))
    registry, ct.REGISTRY = ct.REGISTRY, {**ct.REGISTRY, SCOPE: broken}
    try:
        app = gateway_app(eligibility_answer(GOOD)[0])
    finally:
        ct.REGISTRY = registry
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/evaluations", json=evaluation(ELIGIBLE), headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 500 and r.content == b"", (r.status_code, r.headers, r.text)


def test_every_persona_of_every_installation_is_evaluated() -> None:
    for installation, csv_path in HOST_CSV.items():
        with mock_adapter(csv_path) as (adapter, _, _), host_gateway(adapter, enabled_scopes(installation)) as client:
            for fixture in read_fixtures(INSTALLATIONS / installation / "smoke.json"):
                check_personas(evaluate_with(client), TOKEN, fixture)


def run_live(url: str, fixtures: list[dict]) -> None:
    import httpx

    token = os.environ["GATEWAY_AUTH_TOKEN"]
    with httpx.Client(base_url=url, timeout=10) as client:
        for fixture in fixtures:
            check_refused_requests(evaluate_with(client), token, fixture)
            check_personas(evaluate_with(client), token, fixture)


def run_live_adapter_down(url: str, fixtures: list[dict]) -> None:
    """With the adapter stopped, every type's evaluation is a Gateway error (502), not a crash."""
    import httpx

    with httpx.Client(base_url=url, timeout=30) as client:
        for fixture in fixtures:
            answer = evaluate_with(client)(evaluation(eligible_personas(fixture)[0], fixture["scope"]),
                                           os.environ["GATEWAY_AUTH_TOKEN"])
            assert answer == (502, {"error": "gateway_error"}), (fixture["scope"], answer)


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "adapter-down":
        run_live_adapter_down(sys.argv[2], read_fixtures(Path(sys.argv[3])))
        print(f"PASS evaluations at {sys.argv[2]} answer gateway_error while the adapter is down")
    elif len(sys.argv) == 3:
        run_live(sys.argv[1], read_fixtures(Path(sys.argv[2])))
        print(f"PASS evaluations at {sys.argv[1]}")
    else:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"PASS {name}")
