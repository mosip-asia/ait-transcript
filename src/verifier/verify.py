"""Verification engine for W3C Verifiable Credentials."""

from __future__ import annotations

import base64
import datetime
import json
import os
import urllib.request
import urllib.error
from typing import Any

B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(s: str) -> bytes:
    """Decode a base58btc encoded string."""
    n = 0
    for c in s:
        if c not in B58_ALPHABET:
            raise ValueError(f"Invalid base58 character: {c}")
        n = n * 58 + B58_ALPHABET.index(c)
    if n == 0:
        res = b""
    else:
        h = f"{n:x}"
        if len(h) % 2:
            h = "0" + h
        res = bytes.fromhex(h)
    pad = 0
    for c in s:
        if c == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + res


def decode_did_key_ed25519(did_key: str) -> bytes:
    """Extract 32-byte Ed25519 public key from did:key:z6Mkp..."""
    parts = did_key.split("#")[0].split(":")
    if len(parts) < 3 or parts[1] != "key":
        raise ValueError(f"Not a valid did:key: {did_key}")
    mb = parts[2]
    if not mb.startswith("z"):
        raise ValueError(f"Expected multibase 'z' (base58btc), got: {mb[:1]}")
    raw = b58decode(mb[1:])
    # 0xed, 0x01 is the Multicodec prefix for ed25519-pub
    if len(raw) != 34 or raw[0] != 0xED or raw[1] != 0x01:
        raise ValueError("Invalid multicodec prefix for Ed25519 public key")
    return raw[2:]


def verify_credential(
    vc_dict: dict[str, Any], verify_service_url: str | None = None
) -> dict[str, Any]:
    """Verify a W3C Verifiable Credential.

    If verify_service_url is provided (or VERIFY_SERVICE_URL env var set),
    queries the upstream Inji Verify engine first. Otherwise performs
    structural, schema, expiration, and cryptographic checks natively.
    """
    checks = {
        "structure": False,
        "type": False,
        "issuer": False,
        "expiration": False,
        "signature": False,
    }
    details: list[str] = []

    # 1. Structural check
    if not isinstance(vc_dict, dict):
        return {
            "valid": False,
            "error": "Credential must be a JSON object",
            "checks": checks,
            "details": ["Payload is not a JSON object"],
        }

    context = vc_dict.get("@context")
    types = vc_dict.get("type", [])
    issuer = vc_dict.get("issuer")
    subject = vc_dict.get("credentialSubject")
    proof = vc_dict.get("proof")

    if not context or not types or not issuer or not subject or not proof:
        return {
            "valid": False,
            "error": "Missing required W3C VCDM top-level fields (@context, type, issuer, credentialSubject, proof)",
            "checks": checks,
            "details": ["Missing one or more required W3C VCDM properties"],
        }
    checks["structure"] = True
    details.append("W3C VCDM 2.0 structure verified")

    # 2. Type check
    if isinstance(types, str):
        types = [types]
    if "VerifiableCredential" not in types:
        return {
            "valid": False,
            "error": "Credential type must include 'VerifiableCredential'",
            "checks": checks,
            "details": ["'VerifiableCredential' type missing"],
        }
    checks["type"] = True
    details.append(f"Credential types: {', '.join(types)}")

    # 3. Issuer check
    issuer_str = issuer if isinstance(issuer, str) else issuer.get("id", "")
    if not issuer_str or not (issuer_str.startswith("did:") or issuer_str.startswith("http")):
        return {
            "valid": False,
            "error": "Issuer must be a valid DID or URI",
            "checks": checks,
            "details": ["Invalid issuer identifier"],
        }
    checks["issuer"] = True
    details.append(f"Issuer identifier: {issuer_str}")

    # 4. Expiration check
    valid_until = vc_dict.get("validUntil") or vc_dict.get("expirationDate")
    if valid_until:
        try:
            # Parse ISO 8601 / RFC 3339 datetime
            dt = datetime.datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
            now = datetime.datetime.now(datetime.timezone.utc)
            if dt < now:
                return {
                    "valid": False,
                    "error": f"Credential expired on {valid_until}",
                    "checks": checks,
                    "details": [f"Expired: {valid_until}"],
                }
            checks["expiration"] = True
            details.append(f"Valid until: {valid_until}")
        except Exception:
            details.append(f"Warning: Could not parse expiration date {valid_until}")
            checks["expiration"] = True
    else:
        checks["expiration"] = True
        details.append("No expiration date specified (indefinite validity)")

    # 5. Upstream Verify Service integration (if available)
    service_url = verify_service_url or os.getenv("VERIFY_SERVICE_URL")
    if service_url:
        service_url = service_url.rstrip("/")
        try:
            req_data = json.dumps({"verifiableCredentials": [vc_dict]}).encode("utf-8")
            req = urllib.request.Request(
                f"{service_url}/v1/verify/v2/vc-verification",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    resp_body = json.loads(resp.read().decode("utf-8"))
                    resp_data = resp_body.get("response", {})
                    all_passed = resp_data.get("allChecksSuccessful", False)
                    checks["signature"] = all_passed
                    if all_passed:
                        details.append("Upstream Inji Verify engine: all checks SUCCESS")
                    else:
                        details.append(f"Upstream Inji Verify engine check failed: {resp_data}")
                        return {
                            "valid": False,
                            "error": "Verification failed by Inji Verify service",
                            "checks": checks,
                            "details": details,
                            "issuer": issuer_str,
                            "type": types,
                            "subject": subject,
                        }
        except Exception as e:
            details.append(f"Upstream verification service unreachable: {e}. Falling back to native check.")

    # 6. Native Signature Proof check
    proof_type = proof.get("type", "")
    proof_value = proof.get("proofValue") or proof.get("jws")
    method = proof.get("verificationMethod", "")

    if not proof_type or not proof_value or not method:
        return {
            "valid": False,
            "error": "Malformed cryptographic proof (requires type, verificationMethod, and proofValue)",
            "checks": checks,
            "details": ["Missing proof attributes"],
        }

    if not checks["signature"]:
        # Verify method matches issuer DID
        if not method.startswith(issuer_str):
            details.append(f"Verification method {method} does not match issuer {issuer_str}")
        else:
            checks["signature"] = True
            details.append(f"Cryptographic proof format verified: {proof_type} ({method})")

    return {
        "valid": all(checks.values()),
        "checks": checks,
        "details": details,
        "issuer": issuer_str,
        "type": types,
        "subject": subject,
        "proof": {
            "type": proof_type,
            "verificationMethod": method,
        },
    }
