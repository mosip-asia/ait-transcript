"""Thin HTTP client for Certify's ledger-search / credential-status APIs.

Certify tracks every issued VC in its own ledger, indexed by claim values
(not by our student_id) — see vc-stack/certify_init.sql. The AIT
Transcript's identifier claim is `registrationNo`, so lookups translate
student_id -> registrationNo via fixtures before calling Certify.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx

CERTIFY_BASE_URL = os.environ.get("CERTIFY_BASE_URL", "http://certify-nginx/v1/certify")
CERTIFY_DID_URL = os.environ.get("CERTIFY_DID_URL", "http://certify-nginx/.well-known/did.json")
CREDENTIAL_TYPE = "AitTranscriptCredential,VerifiableCredential"


class CertifyUnavailableError(Exception):
    """Certify (or certify-nginx) could not be reached."""


@lru_cache
def _issuer_did() -> str:
    try:
        resp = httpx.get(CERTIFY_DID_URL, timeout=5.0)
        resp.raise_for_status()
        return "did:key:" + resp.json()["verificationMethod"][0]["publicKeyMultibase"]
    except httpx.HTTPError as exc:
        raise CertifyUnavailableError(f"could not resolve issuer DID: {exc}") from exc


def list_credentials(registration_no: str) -> list[dict[str, Any]]:
    """All VCs Certify has issued for this registration number, newest first."""
    try:
        resp = httpx.post(
            f"{CERTIFY_BASE_URL}/ledger-search",
            json={
                "issuerId": _issuer_did(),
                "credentialType": CREDENTIAL_TYPE,
                "indexedAttributesEquals": {"registrationNo": registration_no},
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        rows = resp.json() if resp.content else []
    except httpx.HTTPError as exc:
        raise CertifyUnavailableError(f"ledger-search failed: {exc}") from exc

    rows.sort(key=lambda r: r.get("issueDate", ""), reverse=True)
    for row in rows:
        row["revocable"] = row.get("statusListCredentialUrl") is not None and row.get("statusListIndex") is not None
        row["revoked"] = row["revocable"] and _bit_is_set(row)
    return rows


def _bit_is_set(row: dict[str, Any]) -> bool:
    """Whether this row's assigned status-list bit is currently set (revoked)."""
    status_list_id = row.get("statusListCredentialUrl")
    index = row.get("statusListIndex")
    if status_list_id is None or index is None:
        return False
    try:
        resp = httpx.get(f"{CERTIFY_BASE_URL}/credentials/status-list/{status_list_id}", timeout=10.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CertifyUnavailableError(f"status-list fetch failed: {exc}") from exc
    encoded_list = resp.json()["credentialSubject"]["encodedList"]
    return _bitstring_bit(encoded_list, index)


def _bitstring_bit(encoded_list: str, index: int) -> bool:
    import base64
    import gzip

    assert encoded_list[0] == "u", "expected multibase base64url ('u') encoding"
    b64 = encoded_list[1:]
    raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    data = gzip.decompress(raw)
    byte = data[index // 8]
    return bool((byte >> (7 - index % 8)) & 1)


def revoke_credential(row: dict[str, Any]) -> None:
    """Revoke a VC. `row` must be an entry previously returned by list_credentials."""
    try:
        resp = httpx.post(
            f"{CERTIFY_BASE_URL}/credentials/status",
            json={
                "credentialId": row["credentialId"],
                "status": True,
                "credentialStatus": {
                    "id": row["statusListCredentialUrl"],
                    "type": "BitstringStatusListEntry",
                    "statusPurpose": row["statusPurpose"],
                    "statusListIndex": row["statusListIndex"],
                    "statusListCredential": row["statusListCredentialUrl"],
                },
            },
            timeout=10.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CertifyUnavailableError(f"revoke failed: {exc}") from exc
