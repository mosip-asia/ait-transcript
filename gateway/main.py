"""The Gateway: `POST /issuances` (contracts.md section 2a), the checklist runner behind Certify's data-provider plugin.

The plugin posts the access-token claims; the Gateway picks the credential type by `scope`, fetches the record and
the eligibility attributes from the data adapter (section 2b), parsing each answer into the type's model, evaluates
the type's checks and answers the claim set (200), the checklist result (403), `no_record` (404) or `unknown_scope`
(400). An answer that does not parse is 502 `gateway_error`; a check that raises is a bug, so a 500. A 200 writes
one issuance row.
Startup touches only the database, never the adapter, so Certify, the adapter and the Gateway start in any order.

Settings come from the environment, which Compose fills from installations/<name>/gateway.env.
Run: uvicorn main:from_env --factory
"""

from __future__ import annotations

import hmac
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeVar
from urllib.parse import quote

import httpx
import psycopg
from fastapi import Body, Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

import credential_types as ct
from store import Store

Answer = TypeVar("Answer")  # what fetch parses an adapter answer into: a model, or a list of one


@dataclass(frozen=True)
class Settings:
    enabled_scopes: tuple[str, ...]
    adapter_url: str
    auth_token: str
    database_url: str

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            enabled_scopes=tuple(os.environ["GATEWAY_ENABLED_SCOPES"].split()),
            adapter_url=os.environ["GATEWAY_ADAPTER_URL"],
            auth_token=os.environ["GATEWAY_AUTH_TOKEN"],
            database_url=os.environ["GATEWAY_DATABASE_URL"],
        )


class Refusal(Exception):
    """Any answer other than 200: a status and the JSON body the plugin reads `error` from."""

    def __init__(self, status: int, error: str, **body) -> None:
        self.status = status
        self.body = {"error": error, **body}


def create_app(settings: Settings, adapter: httpx.Client | None = None, store: Store | None = None) -> FastAPI:
    unknown = set(settings.enabled_scopes) - ct.REGISTRY.keys()
    if unknown:
        raise ValueError(f"no credential type for the enabled scope(s) {sorted(unknown)}")
    enabled = {scope: ct.REGISTRY[scope] for scope in settings.enabled_scopes}
    adapter = adapter or httpx.Client(base_url=settings.adapter_url, timeout=3)
    store = store or Store(settings.database_url)
    expected_auth = f"Bearer {settings.auth_token}".encode()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.ensure_schema()
        yield

    app = FastAPI(title="Gateway", lifespan=lifespan)

    @app.exception_handler(Refusal)
    async def refused(request, exc: Refusal) -> JSONResponse:
        return JSONResponse(exc.body, status_code=exc.status)

    def authenticate(authorization: str = Header("")) -> None:
        if not hmac.compare_digest(authorization.encode(), expected_auth):
            raise HTTPException(401, "missing or wrong bearer token", headers={"WWW-Authenticate": "Bearer"})

    def fetch(path: str, shape: type[Answer], **params: str) -> Answer:
        """The adapter's 200 parsed into `shape`; no answer, another status or malformed data is gateway_error."""
        try:
            r = adapter.get(path, params=params)
        except httpx.HTTPError as exc:
            raise Refusal(502, "gateway_error") from exc
        if r.status_code == 404:
            raise Refusal(404, "no_record")
        if r.status_code != 200:
            raise Refusal(502, "gateway_error")
        try:
            return TypeAdapter(shape).validate_json(r.content)
        except ValidationError as exc:
            raise Refusal(502, "gateway_error") from exc

    @app.post("/issuances", dependencies=[Depends(authenticate)])
    def issuances(claims: dict = Body(...)) -> dict:
        sub, scope = claims.get("sub"), claims.get("scope")
        if not isinstance(sub, str) or not sub:
            raise Refusal(400, "invalid_access_token")
        scopes = scope.split() if isinstance(scope, str) else []
        ctype = next((enabled[s] for s in scopes if s in enabled), None)
        if ctype is None:
            raise Refusal(400, "unknown_scope")

        student = f"/students/{quote(sub, safe='')}"
        degrees = fetch(f"{student}/degrees", list[ct.Degree])
        if not degrees:
            raise Refusal(404, "no_record")
        degree_id = degrees[0].degreeId  # one identity per degree in v0.1: the list has one entry
        checks = ct.evaluate(ctype, fetch(f"{student}/eligibility", ctype.eligibility, degreeId=degree_id))
        if not all(c["passed"] for c in checks):
            raise Refusal(403, "checklist_failed", credentialType=ctype.credential_type, checks=checks)

        body = ct.claims(ctype, fetch(f"{student}/transcript", ctype.record, degreeId=degree_id))
        try:
            store.record(sub, ctype.credential_type, ctype.scope, claims.get("client_id"))
        except psycopg.Error as exc:
            raise Refusal(502, "gateway_error") from exc
        return body

    return app


def from_env() -> FastAPI:
    return create_app(Settings.from_env())
