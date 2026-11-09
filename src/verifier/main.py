"""Verifier Web Service for W3C Verifiable Credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.verifier.verify import verify_credential

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(
    title="AIT Credential Verifier",
    description="Custom branded verification service for W3C Verifiable Credentials",
    version="1.0.0",
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "verifier"}


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request) -> HTMLResponse:
    """Render the Verification UI."""
    institution = os.getenv("INSTITUTION_NAME", "Asian Institute of Technology")
    title = f"{institution} Credential Verifier"
    return templates.TemplateResponse(
        "verify.html",
        {
            "request": request,
            "title": title,
            "institution": institution,
        },
    )


@app.post("/api/verify")
async def verify_endpoint(request: Request) -> JSONResponse:
    """Verify a Verifiable Credential payload.

    Accepts raw JSON credential, or wrapped in {"verifiableCredentials": [...]}
    or {"credential": {...}}.
    """
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")

    vc: dict[str, Any] | None = None
    if isinstance(data, dict):
        if "verifiableCredentials" in data and isinstance(data["verifiableCredentials"], list) and data["verifiableCredentials"]:
            vc = data["verifiableCredentials"][0]
        elif "credential" in data and isinstance(data["credential"], dict):
            vc = data["credential"]
        else:
            vc = data
    else:
        raise HTTPException(status_code=400, detail="Expected JSON object")

    verify_service_url = os.getenv("VERIFY_SERVICE_URL")
    result = verify_credential(vc, verify_service_url=verify_service_url)
    return JSONResponse(content=result)


@app.post("/api/verify/file")
async def verify_file(file: UploadFile = File(...)) -> JSONResponse:
    """Verify a credential from an uploaded JSON file."""
    try:
        contents = await file.read()
        data = json.loads(contents.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid file content: {e}")

    vc = data.get("credential", data) if isinstance(data, dict) else None
    if not isinstance(vc, dict):
        raise HTTPException(status_code=400, detail="File did not contain a valid JSON object")

    verify_service_url = os.getenv("VERIFY_SERVICE_URL")
    result = verify_credential(vc, verify_service_url=verify_service_url)
    return JSONResponse(content=result)
