"""Phase 3 + Phase 7 request workflow tests (PLAN.md). Run: python3 app/test_requests.py"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
_db_file.close()
os.environ["AIT_DEMO_DB"] = _db_file.name

from fastapi.testclient import TestClient  # noqa: E402

from app import certify_client, db  # noqa: E402
from app.fixtures import list_students  # noqa: E402
from app.main import app  # noqa: E402
from app import requests as req_workflow  # noqa: E402

# Tests run with no Certify stack available — default to "never issued" so the
# reissue gate in create_request() doesn't make a real HTTP call. Individual
# tests override this to exercise the gate itself.
certify_client.list_credentials = lambda registration_no: []

db.reset_db()
client = TestClient(app)

STUDENT_A = list_students()[0]  # dual-degree: Masters + PhD
STUDENT_B = list_students()[1]  # single-degree
DEGREE_A1 = STUDENT_A["degrees"][0]["degreeId"]
DEGREE_A2 = STUDENT_A["degrees"][1]["degreeId"]
DEGREE_B1 = STUDENT_B["degrees"][0]["degreeId"]


def _login_student(c: TestClient, student_id: str) -> None:
    c.post("/student/login", data={"persona_id": student_id}, follow_redirects=True)


def test_approve_sets_status_and_claim_panel() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    row = req_workflow.approve_request(sid, DEGREE_A1)
    assert row["status"] == "approved"
    assert row["decided_at"] is not None
    panel = req_workflow.claim_panel_for_student(sid, DEGREE_A1)
    assert panel is not None
    assert panel["keycloak_username"] == STUDENT_A["degrees"][0]["keycloakId"]
    assert panel["keycloak_password"] == "inji"


def test_reject_no_claim_panel() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    row = req_workflow.reject_request(sid, DEGREE_A1)
    assert row["status"] == "rejected"
    assert row["decided_at"] is not None
    assert req_workflow.claim_panel_for_student(sid, DEGREE_A1) is None


def test_rejected_student_can_resubmit() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.reject_request(sid, DEGREE_A1)
    row = req_workflow.create_request(sid, DEGREE_A1)
    assert row["status"] == "pending"
    assert row["decided_at"] is None
    # Resubmitting starts a new history row rather than reusing the rejected one.
    conn = db.connect()
    count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE student_id = ? AND degree_id = ?", (sid, DEGREE_A1)
    ).fetchone()[0]
    conn.close()
    assert count == 2


def test_duplicate_request_not_created() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    try:
        req_workflow.create_request(sid, DEGREE_A1)
        raised = False
    except req_workflow.RequestWorkflowError:
        raised = True
    assert raised
    conn = db.connect()
    count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE student_id = ? AND degree_id = ?", (sid, DEGREE_A1)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_double_approve_idempotent() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    first = req_workflow.approve_request(sid, DEGREE_A1)
    try:
        req_workflow.approve_request(sid, DEGREE_A1)
        raised = False
    except req_workflow.RequestWorkflowError:
        raised = True
    assert raised
    second = req_workflow.get_request(sid, DEGREE_A1)
    assert second["status"] == "approved"
    assert second["decided_at"] == first["decided_at"]


def test_two_degrees_have_independent_state() -> None:
    """A dual-degree student can hold an approved Masters VC and a pending PhD
    request at the same time — requests are scoped per (student, degree)."""
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)
    req_workflow.create_request(sid, DEGREE_A2)

    masters = req_workflow.get_request(sid, DEGREE_A1)
    phd = req_workflow.get_request(sid, DEGREE_A2)
    assert masters["status"] == "approved"
    assert phd["status"] == "pending"
    assert req_workflow.claim_panel_for_student(sid, DEGREE_A1) is not None
    assert req_workflow.claim_panel_for_student(sid, DEGREE_A2) is None


def test_rejected_student_page_has_no_credentials() -> None:
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.reject_request(sid, DEGREE_A1)
    _login_student(c, sid)
    html = c.get("/student").text
    assert "Claim your" not in html
    assert "keycloak_username" not in html.lower()
    assert req_workflow.claim_panel_for_student(sid, DEGREE_A1) is None


def test_student_b_never_sees_student_a_claim() -> None:
    db.reset_db()
    c_a = TestClient(app)
    c_b = TestClient(app)
    req_workflow.create_request(STUDENT_A["id"], DEGREE_A1)
    req_workflow.approve_request(STUDENT_A["id"], DEGREE_A1)
    _login_student(c_b, STUDENT_B["id"])
    html_b = c_b.get("/student").text
    assert STUDENT_A["id"] not in html_b or "Claim your" not in html_b
    assert req_workflow.claim_panel_for_student(STUDENT_B["id"], DEGREE_B1) is None
    _login_student(c_a, STUDENT_A["id"])
    html_a = c_a.get("/student").text
    assert "Claim your" in html_a
    assert STUDENT_A["degrees"][0]["keycloakId"] in html_a


def test_pending_to_approved_via_http() -> None:
    db.reset_db()
    c_student = TestClient(app)
    c_reg = TestClient(app)
    sid = STUDENT_A["id"]
    _login_student(c_student, sid)
    c_student.post("/student/request", data={"degree_id": DEGREE_A1}, follow_redirects=True)
    before = c_student.get("/student").text
    assert "Claim your" not in before
    c_reg.post("/registrar/login", data={"persona_id": "registrar-001"}, follow_redirects=True)
    c_reg.post(f"/registrar/requests/{sid}/{DEGREE_A1}/approve", follow_redirects=True)
    after = c_student.get("/student").text
    assert "Claim your" in after
    assert "http://localhost:4004" in after


def test_reissue_blocked_while_active_vc_exists() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)

    original = certify_client.list_credentials
    certify_client.list_credentials = lambda registration_no: [{"credentialId": "x", "revoked": False}]
    try:
        raised = False
        try:
            req_workflow.create_request(sid, DEGREE_A1)
        except req_workflow.RequestWorkflowError:
            raised = True
        assert raised
    finally:
        certify_client.list_credentials = original


def test_reissue_allowed_once_revoked() -> None:
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)

    original = certify_client.list_credentials
    # Was issued once, that VC is now revoked -> a fresh request is allowed.
    certify_client.list_credentials = lambda registration_no: [{"credentialId": "x", "revoked": True}]
    try:
        row = req_workflow.create_request(sid, DEGREE_A1)
        assert row["status"] == "pending"
    finally:
        certify_client.list_credentials = original


def test_reissue_blocked_while_approval_awaiting_claim() -> None:
    """An approved request whose VC was never actually claimed (transcripts
    empty) must not be re-issuable — that's the same 'approved, no active VC'
    shape as a revoke, but nothing was ever revoked here."""
    db.reset_db()
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)

    raised = False
    try:
        req_workflow.create_request(sid, DEGREE_A1)  # default mock: list_credentials -> []
    except req_workflow.RequestWorkflowError:
        raised = True
    assert raised
    conn = db.connect()
    count = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE student_id = ? AND degree_id = ?", (sid, DEGREE_A1)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_revoked_student_can_request_new_one() -> None:
    """Approved request whose VC was since revoked must offer a re-request
    control on the student page, not just show 'Approved' forever."""
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)

    original = certify_client.list_credentials
    certify_client.list_credentials = lambda registration_no: [
        {"credentialId": "x", "issueDate": "2999-01-01", "revoked": True, "revocable": True}
    ]
    try:
        _login_student(c, sid)
        html = c.get("/student").text
        assert "revoked" in html.lower()
        assert "Request a new transcript VC" in html
        # Revoked-and-unclaimed needs a fresh approval, not wallet access — no
        # Keycloak credentials should be dangled here.
        assert "Keycloak username" not in html
    finally:
        certify_client.list_credentials = original


def test_active_vc_still_shows_wallet_access() -> None:
    """A student with an already-claimed, active VC must still be able to
    reopen Inji Web (new device, cleared browser data, etc.) — the claim
    panel should switch to 'Access' framing, not disappear."""
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)

    original = certify_client.list_credentials
    certify_client.list_credentials = lambda registration_no: [
        {"credentialId": "x", "issueDate": "2026-01-01", "revoked": False}
    ]
    try:
        _login_student(c, sid)
        html = c.get("/student").text
        assert "Access your Masters credential" in html
        assert "Claim your Masters credential" not in html
        assert "Keycloak username" in html
        assert "Already claimed" in html
    finally:
        certify_client.list_credentials = original


def test_student_sees_full_request_history() -> None:
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.reject_request(sid, DEGREE_A1)
    req_workflow.create_request(sid, DEGREE_A1)

    history = req_workflow.list_request_history(sid, DEGREE_A1)
    assert len(history) == 2
    assert history[0]["status"] == "pending"
    assert history[1]["status"] == "rejected"

    _login_student(c, sid)
    html = c.get("/student").text
    assert "Request history (2)" in html


def test_multi_degree_student_gets_jump_nav_and_login_warning() -> None:
    """Dual-degree student (STUDENT_A) can claim both degrees independently —
    the portal must make the choice explicit (jump nav) and warn that each
    degree needs its own Inji Web login, since we deliberately kept per-degree
    Keycloak identities rather than a single multi-credential wallet session."""
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)
    req_workflow.create_request(sid, DEGREE_A2)
    req_workflow.approve_request(sid, DEGREE_A2)

    _login_student(c, sid)
    html = c.get("/student").text
    assert "Jump to:" in html
    assert f"#degree-{DEGREE_A1}" in html
    assert f"#degree-{DEGREE_A2}" in html
    assert "Claim your Masters credential" in html
    assert "Claim your PhD credential" in html
    assert "own Keycloak login" in html


def test_registrar_reissue_button_hidden_while_awaiting_claim() -> None:
    """Reproduces the reported bug: clicking 'Issue new transcript' twice
    before the student claims it must not create two approved rows, and the
    button must be hidden (not just disabled) once approved-and-unclaimed."""
    db.reset_db()
    c_reg = TestClient(app)
    sid = STUDENT_A["id"]
    c_reg.post("/registrar/login", data={"persona_id": "registrar-001"}, follow_redirects=True)
    c_reg.post(f"/registrar/students/{sid}/{DEGREE_A1}/reissue", follow_redirects=True)

    html = c_reg.get("/registrar").text
    assert "nothing appears here until the student actually claims it" in html

    c_reg.post(f"/registrar/students/{sid}/{DEGREE_A1}/reissue", follow_redirects=True)
    history = req_workflow.list_request_history(sid, DEGREE_A1)
    assert len(history) == 1


def test_reissue_after_revoke_shows_awaiting_and_hides_button() -> None:
    """Reported bug: with every VC revoked, 'Issue without request' seemed to do
    nothing (the button stayed, no feedback) and each click added another approval."""
    original = certify_client.list_credentials
    try:
        db.reset_db()
        c_reg = TestClient(app)
        sid = STUDENT_A["id"]
        c_reg.post("/registrar/login", data={"persona_id": "registrar-001"}, follow_redirects=True)
        certify_client.list_credentials = lambda registration_no: [
            {"credentialId": "x", "issueDate": "2000-01-01T00:00:00", "revoked": True, "revocable": True}
        ]
        c_reg.post(f"/registrar/students/{sid}/{DEGREE_A1}/reissue", follow_redirects=True)
        html = c_reg.get("/registrar").text
        assert "New transcript approved" in html
        c_reg.post(f"/registrar/students/{sid}/{DEGREE_A1}/reissue", follow_redirects=True)
        assert len(req_workflow.list_request_history(sid, DEGREE_A1)) == 1
        # Once the student claims (a VC issued after the approval), it's no longer awaiting.
        certify_client.list_credentials = lambda registration_no: [
            {"credentialId": "y", "issueDate": "2999-01-01T00:00:00", "revoked": False, "revocable": True}
        ]
        assert "New transcript approved" not in c_reg.get("/registrar").text
    finally:
        certify_client.list_credentials = original


def test_student_awaiting_claim_after_revoke_has_no_request_button_and_sees_refusal() -> None:
    """Reported bug: re-issued (approved, unclaimed) after all VCs were revoked,
    the student page still offered 'request a new one' and the click did nothing."""
    db.reset_db()
    c = TestClient(app)
    sid = STUDENT_A["id"]
    req_workflow.create_request(sid, DEGREE_A1)
    req_workflow.approve_request(sid, DEGREE_A1)
    original = certify_client.list_credentials
    certify_client.list_credentials = lambda registration_no: [
        {"credentialId": "x", "issueDate": "2000-01-01T00:00:00", "revoked": True, "revocable": True}
    ]
    try:
        _login_student(c, sid)
        html = c.get("/student").text
        assert "Keycloak username" in html
        assert "Request a new transcript VC" not in html
        r = c.post("/student/request", data={"degree_id": DEGREE_A1}, follow_redirects=True)
        assert "still awaiting the student" in r.text
    finally:
        certify_client.list_credentials = original


def main() -> None:
    test_approve_sets_status_and_claim_panel()
    test_reject_no_claim_panel()
    test_rejected_student_can_resubmit()
    test_duplicate_request_not_created()
    test_double_approve_idempotent()
    test_two_degrees_have_independent_state()
    test_rejected_student_page_has_no_credentials()
    test_student_b_never_sees_student_a_claim()
    test_pending_to_approved_via_http()
    test_reissue_blocked_while_active_vc_exists()
    test_reissue_allowed_once_revoked()
    test_reissue_blocked_while_approval_awaiting_claim()
    test_revoked_student_can_request_new_one()
    test_active_vc_still_shows_wallet_access()
    test_student_sees_full_request_history()
    test_multi_degree_student_gets_jump_nav_and_login_warning()
    test_registrar_reissue_button_hidden_while_awaiting_claim()
    test_reissue_after_revoke_shows_awaiting_and_hides_button()
    test_student_awaiting_claim_after_revoke_has_no_request_button_and_sees_refusal()
    print("app/test_requests.py: all tests passed")


if __name__ == "__main__":
    main()
