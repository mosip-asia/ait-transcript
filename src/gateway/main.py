"""The Gateway: the Approval gate's checklist runner, behind the shared bearer secret.

`POST /evaluations` is the read-only Checklist evaluation: given `{sub, scope}` it picks the credential type by
`scope`, reads the student's eligibility at GATEWAY_ELIGIBILITY_URL with `{sub}` filled in (adapter/openapi.yaml's
`GET /student/{sub}/eligibility`), parsing it into the type's eligibility model, evaluates every check in order and answers `{credentialType, checks}`: 200 when every
check passes, else 403 with `error: checklist_failed`. It writes nothing.

It answers `unknown_scope` (400), `no_record` (404), and 502 `gateway_error` for an adapter that is unreachable,
answers another status or answers data that does not parse; a check that raises is a bug, so a 500 with no body.
Startup touches nothing external, so Certify, the adapter and the Gateway start in any order; it refuses an
eligibility URL that is not an http(s) URL holding `{sub}`.

Settings come from the environment, which Compose fills from installations/<name>/gateway.env.
Run: uvicorn main:from_env --factory
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import quote, urlsplit

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

import credential_types as ct


@dataclass(frozen=True)
class Settings:
    enabled_scopes: tuple[str, ...]
    eligibility_url: str
    auth_token: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            enabled_scopes=tuple(os.environ["GATEWAY_ENABLED_SCOPES"].split()),
            eligibility_url=os.environ["GATEWAY_ELIGIBILITY_URL"],
            auth_token=os.environ["GATEWAY_AUTH_TOKEN"],
        )


class Refusal(Exception):
    """Any answer other than 200: a status and the JSON body the plugin reads `error` from."""

    def __init__(self, status: int, error: str, **body) -> None:
        self.status = status
        self.body = {"error": error, **body}


class Evaluation(BaseModel):
    """The body of POST /evaluations, and nothing else: `sub` travels in the body to stay out of the access logs."""

    model_config = ConfigDict(extra="forbid")

    sub: Annotated[StrictStr, Field(min_length=1)]
    scope: Annotated[StrictStr, Field(min_length=1)]  # the token's scope claim: space-separated scopes


async def evaluation_body(request: Request) -> Evaluation:
    """The request parsed at the seam: anything but exactly the two non-empty strings is invalid_request."""
    try:
        return Evaluation.model_validate_json(await request.body())
    except ValidationError as exc:
        raise Refusal(400, "invalid_request") from exc


def eligibility_url(template: str) -> str:
    """GATEWAY_ELIGIBILITY_URL, checked: an http(s) URL with a host that holds `{sub}`, else ValueError."""
    parts = urlsplit(template.replace("{sub}", "sub"))
    if "{sub}" not in template or parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError(f"GATEWAY_ELIGIBILITY_URL must be an http(s) URL holding {{sub}}, not {template!r}")
    return template


def create_app(settings: Settings, adapter: httpx.Client | None = None) -> FastAPI:
    url = eligibility_url(settings.eligibility_url)
    unknown = set(settings.enabled_scopes) - ct.REGISTRY.keys()
    if unknown:
        raise ValueError(f"no credential type for the enabled scope(s) {sorted(unknown)}")
    enabled = {scope: ct.REGISTRY[scope] for scope in settings.enabled_scopes}
    adapter = adapter or httpx.Client(timeout=3)
    expected_auth = f"Bearer {settings.auth_token}".encode()

    app = FastAPI(title="Gateway")

    @app.exception_handler(Refusal)
    async def refused(request, exc: Refusal) -> JSONResponse:
        return JSONResponse(exc.body, status_code=exc.status)

    @app.exception_handler(Exception)
    async def bug(request, exc: Exception) -> Response:
        """A check that raised: 500 with no body (Starlette still logs the traceback)."""
        return Response(status_code=500)

    def authenticate(authorization: str = Header("")) -> None:
        if not hmac.compare_digest(authorization.encode(), expected_auth):
            raise HTTPException(401, "missing or wrong bearer token", headers={"WWW-Authenticate": "Bearer"})

    def eligibility(ctype: ct.CredentialType, sub: str) -> BaseModel:
        """The adapter's eligibility for the student, parsed into the type's model; no answer, another status than
        200 or 404, or malformed data is gateway_error."""
        try:
            r = adapter.get(url.replace("{sub}", quote(sub, safe="")))
        except httpx.HTTPError as exc:
            raise Refusal(502, "gateway_error") from exc
        if r.status_code == 404:
            raise Refusal(404, "no_record")
        if r.status_code != 200:
            raise Refusal(502, "gateway_error")
        try:
            return ctype.eligibility.model_validate_json(r.content)
        except ValidationError as exc:
            raise Refusal(502, "gateway_error") from exc

    def credential_type(scope: str) -> ct.CredentialType:
        """The enabled type of the first space-separated scope that names one, else unknown_scope."""
        ctype = next((enabled[s] for s in scope.split() if s in enabled), None)
        if ctype is None:
            raise Refusal(400, "unknown_scope")
        return ctype

    @app.post("/evaluations", dependencies=[Depends(authenticate)])
    def evaluations(request: Evaluation = Depends(evaluation_body)) -> dict:
        ctype = credential_type(request.scope)
        checks = ct.evaluate(ctype, eligibility(ctype, request.sub))
        result = {"credentialType": ctype.credential_type, "checks": checks}
        if not all(c["passed"] for c in checks):
            raise Refusal(403, "checklist_failed", **result)
        return result

    return app


def from_env() -> FastAPI:
    return create_app(Settings.from_env())
