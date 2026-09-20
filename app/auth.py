"""Signed-cookie sessions for student and registrar portals (separate cookie names)."""

from __future__ import annotations

import os
from typing import Literal

from fastapi import Request, Response
from itsdangerous import BadSignature, URLSafeSerializer

COOKIE_STUDENT = "ait_demo_student"
COOKIE_REGISTRAR = "ait_demo_registrar"
MAX_AGE = 60 * 60 * 24 * 7  # 7 days

_SECRET = os.environ.get("AIT_DEMO_SESSION_SECRET", "ait-transcript-demo-session-secret")
_serializer = URLSafeSerializer(_SECRET, salt="ait-demo-persona")


def _sign_persona_id(persona_id: str) -> str:
    return _serializer.dumps({"id": persona_id})


def _unsign_persona_id(value: str) -> str | None:
    try:
        data = _serializer.loads(value)
    except BadSignature:
        return None
    pid = data.get("id")
    return pid if isinstance(pid, str) else None


def set_student_session(response: Response, student_id: str) -> None:
    response.set_cookie(
        key=COOKIE_STUDENT,
        value=_sign_persona_id(student_id),
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def set_registrar_session(response: Response, registrar_id: str) -> None:
    response.set_cookie(
        key=COOKIE_REGISTRAR,
        value=_sign_persona_id(registrar_id),
        max_age=MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def clear_student_session(response: Response) -> None:
    response.delete_cookie(COOKIE_STUDENT, path="/")


def clear_registrar_session(response: Response) -> None:
    response.delete_cookie(COOKIE_REGISTRAR, path="/")


def get_student_id(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE_STUDENT)
    if not raw:
        return None
    return _unsign_persona_id(raw)


def get_registrar_id(request: Request) -> str | None:
    raw = request.cookies.get(COOKIE_REGISTRAR)
    if not raw:
        return None
    return _unsign_persona_id(raw)


Portal = Literal["student", "registrar"]
