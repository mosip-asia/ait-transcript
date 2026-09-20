"""Request / approval workflow logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app import certify_client, db, fixtures

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

INJI_WEB_URL = "http://localhost:4004"
INJI_VERIFY_URL = "http://localhost:4007"
KEYCLOAK_DEMO_PASSWORD = "inji"
# Keycloak's browser flow has the Cookie/SSO step disabled (see vc-stack/config/
# keycloak-realm.json's "browser-no-sso" flow), so switching to a *different* degree's
# identity in the same tab needs an explicit sign-out first — otherwise Keycloak refuses
# with "already authenticated as different user" rather than silently mismatching.
KEYCLOAK_LOGOUT_URL = (
    "http://localhost:9080/realms/inji/protocol/openid-connect/logout"
    "?client_id=wallet-demo&post_logout_redirect_uri=" + INJI_WEB_URL + "/redirect"
)

# ponytail: fixed TTL guard, not a retry/cancel flow — if Certify's status-list
# batch job never confirms a revoke (misconfig, outage), the button just
# unsticks itself after this long instead of staying "Revoking…" forever.
REVOKE_PENDING_TTL_SECONDS = 300


class RequestWorkflowError(Exception):
    """Invalid or duplicate workflow transition."""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_request_history(student_id: str, degree_id: str) -> list[dict[str, Any]]:
    """All requests ever made for this (student, degree), newest first."""
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT student_id, degree_id, status, created_at, decided_at FROM requests
            WHERE student_id = ? AND degree_id = ? ORDER BY created_at DESC, id DESC
            """,
            (student_id, degree_id),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def get_request(student_id: str, degree_id: str) -> dict[str, Any] | None:
    history = list_request_history(student_id, degree_id)
    return history[0] if history else None


def list_requests_for_student(student_id: str) -> dict[str, dict[str, Any]]:
    """Latest request per degree_id for this student."""
    student = fixtures.get_student(student_id)
    if student is None:
        return {}
    return {
        degree["degreeId"]: get_request(student_id, degree["degreeId"])
        for degree in fixtures.list_degrees(student)
    }


def create_request(student_id: str, degree_id: str) -> dict[str, Any]:
    existing = get_request(student_id, degree_id)
    if existing is not None and existing["status"] == STATUS_PENDING:
        raise RequestWorkflowError("request already pending")

    student = fixtures.get_student(student_id)
    degree = fixtures.get_degree(student, degree_id) if student is not None else None
    if degree is not None:
        transcripts = certify_client.list_credentials(degree["registrationNo"])
        if any(not t["revoked"] for t in transcripts):
            raise RequestWorkflowError("student already holds an active transcript VC. Revoke it first")
        if existing is not None and existing["status"] == STATUS_APPROVED and not transcripts:
            raise RequestWorkflowError("an earlier approval is still awaiting the student's claim")

    created_at = _utc_now_iso()
    conn = db.connect()
    try:
        conn.execute(
            "INSERT INTO requests (student_id, degree_id, status, created_at, decided_at) VALUES (?, ?, ?, ?, NULL)",
            (student_id, degree_id, STATUS_PENDING, created_at),
        )
        conn.commit()
    finally:
        conn.close()
    return get_request(student_id, degree_id)  # type: ignore[return-value]


def _decide(student_id: str, degree_id: str, new_status: str) -> dict[str, Any]:
    existing = get_request(student_id, degree_id)
    if existing is None:
        raise RequestWorkflowError("request not found")
    if existing["status"] != STATUS_PENDING:
        raise RequestWorkflowError("request already decided")
    decided_at = _utc_now_iso()
    conn = db.connect()
    try:
        conn.execute(
            "UPDATE requests SET status = ?, decided_at = ? WHERE student_id = ? AND degree_id = ? AND status = ?",
            (new_status, decided_at, student_id, degree_id, STATUS_PENDING),
        )
        conn.commit()
    finally:
        conn.close()
    updated = get_request(student_id, degree_id)
    if updated is None:
        raise RequestWorkflowError("request not found")
    return updated


def approve_request(student_id: str, degree_id: str) -> dict[str, Any]:
    return _decide(student_id, degree_id, STATUS_APPROVED)


def reject_request(student_id: str, degree_id: str) -> dict[str, Any]:
    return _decide(student_id, degree_id, STATUS_REJECTED)


def list_pending() -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT student_id, degree_id, status, created_at, decided_at FROM requests WHERE status = ? ORDER BY created_at",
            (STATUS_PENDING,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def list_decided() -> list[dict[str, Any]]:
    conn = db.connect()
    try:
        rows = conn.execute(
            """
            SELECT student_id, degree_id, status, created_at, decided_at FROM requests
            WHERE status IN (?, ?) ORDER BY decided_at DESC
            """,
            (STATUS_APPROVED, STATUS_REJECTED),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def claim_panel_for_student(student_id: str, degree_id: str) -> dict[str, str] | None:
    """Keycloak claim instructions — only when registrar has approved.

    The Keycloak/Certify identity is per-degree (each degree is its own CSV
    row so a multi-degree student can claim a distinct transcript per degree),
    so the username shown here is the degree's own `keycloakId`, not the
    student's demo-app persona id.
    """
    req = get_request(student_id, degree_id)
    if req is None or req["status"] != STATUS_APPROVED:
        return None
    student = fixtures.get_student(student_id)
    degree = fixtures.get_degree(student, degree_id) if student is not None else None
    if degree is None:
        return None
    return {
        "keycloak_username": degree["keycloakId"],
        "keycloak_password": KEYCLOAK_DEMO_PASSWORD,
        "inji_web_url": INJI_WEB_URL,
        "inji_verify_url": INJI_VERIFY_URL,
        "keycloak_logout_url": KEYCLOAK_LOGOUT_URL,
    }


def mark_revoke_requested(credential_id: str) -> None:
    """Record that a revoke was submitted for this VC, so the registrar UI can
    keep showing it as in-flight across page reloads until Certify's
    status-list batch job actually confirms it (see PLAN.md's revoke-UX fix)."""
    conn = db.connect()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO pending_revocations (credential_id, requested_at) VALUES (?, ?)",
            (credential_id, _utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def clear_revoke_pending(credential_id: str) -> None:
    conn = db.connect()
    try:
        conn.execute("DELETE FROM pending_revocations WHERE credential_id = ?", (credential_id,))
        conn.commit()
    finally:
        conn.close()


def is_revoke_pending(credential_id: str) -> bool:
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT requested_at FROM pending_revocations WHERE credential_id = ?",
            (credential_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return False
    requested_at = datetime.fromisoformat(row["requested_at"])
    age_seconds = (datetime.now(timezone.utc) - requested_at).total_seconds()
    if age_seconds > REVOKE_PENDING_TTL_SECONDS:
        clear_revoke_pending(credential_id)
        return False
    return True
