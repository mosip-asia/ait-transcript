"""TEMPORARY SIS bridge (ticket 08 of the issuer reshape; ticket 11 deletes sis-bridge/ and vc-stack/sis-bridge/).

Serves the Adapter contract's record paths (adapter/openapi.yaml) in front of the SIS Adapter's current route,
`GET /api/v1/credentials/transcript/{student_id}`, until the SIS Adapter serves `/records` itself. Every mapping rule
is in sis_mapping.py. Its one setting is the SIS base URL (SIS_BASE_URL).

- `GET /records?sub&scope`: `[{ recordId: sub }]` when the SIS answers 200 for `sub`, a 404 when it answers 404.
- `GET /records/{recordId}?scope`: the SIS's answer mapped to the transcript record, a 404 when the SIS answers 404.
- No eligibility path: the Gateway keeps reading the CSV mock's (wayfinder ticket 09).
- Anything else (no answer, another status, a body that is not the known transcript) is a 502, which the contract makes
  the plugin refuse with `adapter_error`; it is never a 404 ("no such student") and never an empty record.

`scope` is required, as the contract says, and ignored: the SIS holds one kind of record. The bridge logs nothing, and
its image runs uvicorn without an access log, so a `sub` stays out of the logs as the contract asks.
"""

from __future__ import annotations

import os
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException

from sis_mapping import to_record

SIS_ROUTE = "/api/v1/credentials/transcript/{}"


def create_app(sis_base_url: str) -> FastAPI:
    sis = httpx.Client(base_url=sis_base_url, timeout=5)
    app = FastAPI(title="Temporary SIS bridge")

    def ask(student_id: str) -> httpx.Response:
        """The SIS's 200 for the student; its 404 is ours, and anything else is a 502."""
        try:
            answer = sis.get(SIS_ROUTE.format(quote(student_id, safe="")))
        except httpx.HTTPError:
            raise HTTPException(502, "the SIS Adapter did not answer") from None
        if answer.status_code == 404:
            raise HTTPException(404, "no such student")
        if answer.status_code != 200:
            raise HTTPException(502, f"the SIS Adapter answered {answer.status_code}")
        return answer

    @app.get("/records")
    def records(sub: str, scope: str) -> list[dict]:
        ask(sub)
        return [{"recordId": sub}]

    @app.get("/records/{recordId}")
    def record(recordId: str, scope: str) -> dict:
        answer = ask(recordId)
        try:
            return to_record(answer.json())
        except ValueError:  # a body that is not JSON, or UnexpectedSisAnswer (a ValueError)
            raise HTTPException(502, "the SIS Adapter's answer is not a transcript") from None

    return app


def from_env() -> FastAPI:
    """uvicorn --factory bridge:from_env"""
    return create_app(os.environ["SIS_BASE_URL"])
