"""FastAPI demo app: student request flow + registrar approval."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import auth, certify_client, db, fixtures, requests as req_workflow

BANGKOK = ZoneInfo("Asia/Bangkok")


def _bangkok(value: str | None) -> str:
    """Render a stored/Certify timestamp (always UTC, sometimes naive) in
    Bangkok local time for display — both portals show one timezone."""
    if not value:
        return ""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(BANGKOK).strftime("%Y-%m-%d %H:%M ICT")


TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
TEMPLATES.env.filters["bkk"] = _bangkok

app = FastAPI(title="AIT Transcript VC Demo")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


def _redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=status_code)


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return _redirect("/student/login")


# --- Student portal ---


@app.get("/student/login", response_class=HTMLResponse)
def student_login_get(request: Request) -> HTMLResponse:
    if auth.get_student_id(request):
        return _redirect("/student")
    return TEMPLATES.TemplateResponse(
        request,
        "student_login.html",
        {"students": fixtures.list_students(), "error": None},
    )


@app.post("/student/login", response_model=None)
def student_login_post(
    request: Request,
    persona_id: str = Form(...),
):
    student = fixtures.get_student(persona_id)
    if student is None:
        return TEMPLATES.TemplateResponse(
            request,
            "student_login.html",
            {
                "students": fixtures.list_students(),
                "error": "Unknown student persona. Please choose from the list.",
            },
            status_code=400,
        )
    response = _redirect("/student")
    auth.set_student_session(response, student["id"])
    return response


@app.get("/student", response_model=None)
def student_home(request: Request):
    student_id = auth.get_student_id(request)
    if not student_id:
        return _redirect("/student/login")
    student = fixtures.get_student(student_id)
    if student is None:
        response = _redirect("/student/login")
        auth.clear_student_session(response)
        return response

    certify_error = None
    degree_views = []
    for degree in fixtures.list_degrees(student):
        degree_id = degree["degreeId"]
        transcripts = []
        try:
            transcripts = certify_client.list_credentials(degree["registrationNo"])
        except certify_client.CertifyUnavailableError as exc:
            certify_error = str(exc)
        transcript_request = req_workflow.get_request(student_id, degree_id)
        has_active_vc = any(not t["revoked"] for t in transcripts)
        # Approved, no active VC, and never issued at all — the one state where
        # there's actually something left to claim. Excludes "approved but the
        # VC was since revoked" (that's a re-request, not a claim).
        needs_claim = bool(
            transcript_request
            and transcript_request["status"] == req_workflow.STATUS_APPROVED
            and not has_active_vc
            and not transcripts
        )
        degree_views.append(
            {
                "degree": degree,
                "transcript_request": transcript_request,
                "request_history": req_workflow.list_request_history(student_id, degree_id),
                "claim_panel": req_workflow.claim_panel_for_student(student_id, degree_id),
                "transcripts": transcripts,
                "has_active_vc": has_active_vc,
                "needs_claim": needs_claim,
                # Whether Inji Web login details are shown at all for this degree —
                # to claim for the first time, or to re-access an already-claimed one
                # (new device, cleared browser data, etc.). Excludes the revoked-and-
                # unclaimed state, which needs a fresh approval first, not wallet access.
                "has_wallet_access": needs_claim or has_active_vc,
            }
        )

    return TEMPLATES.TemplateResponse(
        request,
        "student_home.html",
        {
            "student": student,
            "degree_views": degree_views,
            "certify_error": certify_error,
        },
    )


@app.post("/student/logout")
def student_logout() -> RedirectResponse:
    response = _redirect("/student/login")
    auth.clear_student_session(response)
    return response


@app.post("/student/request")
def student_create_request(request: Request, degree_id: str = Form(...)) -> RedirectResponse:
    student_id = auth.get_student_id(request)
    if not student_id:
        return _redirect("/student/login")
    student = fixtures.get_student(student_id)
    if student is not None and fixtures.get_degree(student, degree_id) is not None:
        try:
            req_workflow.create_request(student_id, degree_id)
        except req_workflow.RequestWorkflowError:
            pass
    return _redirect("/student")


# --- Registrar portal ---


@app.get("/registrar/login", response_class=HTMLResponse)
def registrar_login_get(request: Request) -> HTMLResponse:
    if auth.get_registrar_id(request):
        return _redirect("/registrar")
    return TEMPLATES.TemplateResponse(
        request,
        "registrar_login.html",
        {"registrars": fixtures.list_registrars(), "error": None},
    )


@app.post("/registrar/login", response_model=None)
def registrar_login_post(
    request: Request,
    persona_id: str = Form(...),
):
    registrar = fixtures.get_registrar(persona_id)
    if registrar is None:
        return TEMPLATES.TemplateResponse(
            request,
            "registrar_login.html",
            {
                "registrars": fixtures.list_registrars(),
                "error": "Unknown registrar persona.",
            },
            status_code=400,
        )
    response = _redirect("/registrar")
    auth.set_registrar_session(response, registrar["id"])
    return response


@app.get("/registrar", response_model=None)
def registrar_home(request: Request):
    registrar_id = auth.get_registrar_id(request)
    if not registrar_id:
        return _redirect("/registrar/login")
    if fixtures.get_registrar(registrar_id) is None:
        response = _redirect("/registrar/login")
        auth.clear_registrar_session(response)
        return response
    students = fixtures.list_students()
    pending = req_workflow.list_pending()
    decided = req_workflow.list_decided()
    student_by_id = {s["id"]: s for s in students}
    degree_by_id = {
        (s["id"], d["degreeId"]): d for s in students for d in fixtures.list_degrees(s)
    }

    student_degree_rows = [
        {
            "student": s,
            "degree": d,
            "transcripts": [],
            "active_vc": None,
            "request": req_workflow.get_request(s["id"], d["degreeId"]),
        }
        for s in students
        for d in fixtures.list_degrees(s)
    ]
    certify_error = None
    try:
        for row in student_degree_rows:
            vcs = certify_client.list_credentials(row["degree"]["registrationNo"])
            for vc in vcs:
                if vc["revoked"]:
                    req_workflow.clear_revoke_pending(vc["credentialId"])
                    vc["revoke_pending"] = False
                else:
                    vc["revoke_pending"] = req_workflow.is_revoke_pending(vc["credentialId"])
            row["transcripts"] = vcs
            row["active_vc"] = next((v for v in vcs if not v["revoked"]), None)
    except certify_client.CertifyUnavailableError as exc:
        certify_error = str(exc)

    return TEMPLATES.TemplateResponse(
        request,
        "registrar_home.html",
        {
            "student_by_id": student_by_id,
            "degree_by_id": degree_by_id,
            "pending": pending,
            "decided": decided,
            "student_degree_rows": student_degree_rows,
            "certify_error": certify_error,
            "action_error": request.query_params.get("action_error"),
            "notice": request.query_params.get("notice"),
        },
    )


@app.post("/registrar/requests/{student_id}/{degree_id}/approve")
def registrar_approve(request: Request, student_id: str, degree_id: str) -> RedirectResponse:
    if not auth.get_registrar_id(request):
        return _redirect("/registrar/login")
    try:
        req_workflow.approve_request(student_id, degree_id)
    except req_workflow.RequestWorkflowError:
        pass
    return _redirect("/registrar")


@app.post("/registrar/requests/{student_id}/{degree_id}/reject")
def registrar_reject(request: Request, student_id: str, degree_id: str) -> RedirectResponse:
    if not auth.get_registrar_id(request):
        return _redirect("/registrar/login")
    try:
        req_workflow.reject_request(student_id, degree_id)
    except req_workflow.RequestWorkflowError:
        pass
    return _redirect("/registrar")


@app.post("/registrar/students/{student_id}/{degree_id}/transcripts/revoke")
def registrar_revoke_transcript(
    request: Request, student_id: str, degree_id: str, credential_id: str = Form(...)
) -> RedirectResponse:
    if not auth.get_registrar_id(request):
        return _redirect("/registrar/login")
    student = fixtures.get_student(student_id)
    degree = fixtures.get_degree(student, degree_id) if student is not None else None
    if degree is not None:
        try:
            for row in certify_client.list_credentials(degree["registrationNo"]):
                if row["credentialId"] == credential_id:
                    certify_client.revoke_credential(row)
                    req_workflow.mark_revoke_requested(credential_id)
                    notice = "Revoke submitted. Certify batches status-list updates, so it can take up to a minute to show as Revoked below. Refresh to check."
                    return _redirect(f"/registrar?notice={quote(notice)}")
        except certify_client.CertifyUnavailableError as exc:
            return _redirect(f"/registrar?action_error={quote(str(exc))}")
    return _redirect("/registrar")


@app.post("/registrar/students/{student_id}/{degree_id}/reissue")
def registrar_reissue(request: Request, student_id: str, degree_id: str) -> RedirectResponse:
    if not auth.get_registrar_id(request):
        return _redirect("/registrar/login")
    try:
        req_workflow.create_request(student_id, degree_id)
        req_workflow.approve_request(student_id, degree_id)
    except req_workflow.RequestWorkflowError as exc:
        return _redirect(f"/registrar?action_error={quote(str(exc))}")
    return _redirect("/registrar")
