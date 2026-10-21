"""vc-stack/issue_and_verify.py without the stack: the HTTP boundary is an httpx MockTransport.

Covers the token request, the proof JWT, and how the verify step reads verify-service's answer.
The real round trip runs in vc-stack/smoke.sh.
Run: python3 vc-stack/test_issue_and_verify.py
"""

from __future__ import annotations

import base64
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

sys.path.insert(0, str(Path(__file__).resolve().parent))
import issue_and_verify as iv  # noqa: E402


def mock_client(handler) -> tuple[httpx.Client, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(record)), seen


def test_token_request_is_a_password_grant_on_the_smoke_client() -> None:
    client, seen = mock_client(lambda r: httpx.Response(200, json={"access_token": "t", "c_nonce": "n"}))
    token = iv.request_token(client, "inji", "ait-2026-0001", "inji", "ait_transcript_vc_ldp")
    assert token == {"access_token": "t", "c_nonce": "n"}
    (req,) = seen
    assert req.method == "POST"
    assert str(req.url) == f"{iv.KEYCLOAK}/realms/inji/protocol/openid-connect/token"
    assert parse_qs(req.content.decode()) == {
        "grant_type": ["password"],
        "client_id": ["smoke"],
        "username": ["ait-2026-0001"],
        "password": ["inji"],
        "scope": ["ait_transcript_vc_ldp"],
    }


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def b64url_json(segment: str) -> dict:
    return json.loads(b64url_decode(segment))


def test_proof_jwt_is_es256_signed_by_the_did_jwk_in_its_kid() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    jwt = iv.build_proof(key, client_id="smoke", audience="http://certify-nginx", nonce="local-cnonce", now=1_700_000_000)
    header_b64, claims_b64, sig_b64 = jwt.split(".")
    header, claims = b64url_json(header_b64), b64url_json(claims_b64)

    assert header["alg"] == "ES256"
    assert header["typ"] == "openid4vci-proof+jwt"
    did, fragment = header["kid"].split("#")
    assert fragment == "0"
    assert did.startswith("did:jwk:")
    jwk = b64url_json(did.removeprefix("did:jwk:"))
    assert set(jwk) == {"kty", "crv", "x", "y"}, "the did:jwk must carry the public key only"
    assert (jwk["kty"], jwk["crv"]) == ("EC", "P-256")

    assert claims == {"iss": "smoke", "aud": "http://certify-nginx", "nonce": "local-cnonce",
                      "iat": 1_700_000_000, "exp": 1_700_000_300}

    # The signature checks out against the key named in kid (JWS ES256 is raw r || s, 64 bytes).
    numbers = key.public_key().public_numbers()
    assert int.from_bytes(b64url_decode(jwk["x"]), "big") == numbers.x
    assert int.from_bytes(b64url_decode(jwk["y"]), "big") == numbers.y
    sig = b64url_decode(sig_b64)
    assert len(sig) == 64
    der = encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"))
    key.public_key().verify(der, f"{header_b64}.{claims_b64}".encode(), ec.ECDSA(hashes.SHA256()))


CREDENTIAL = {
    "type": ["VerifiableCredential", "AitTranscriptCredential"],
    "credentialSubject": {"id": "did:jwk:abc", "fullName": "Nara Wattanakul", "courses": [{"grade": "A"}]},
    "proof": {"type": "Ed25519Signature2020", "proofValue": "z..."},
}
SUCCESS = {"allChecksSuccessful": True, "schemaAndSignatureCheck": {"valid": True, "error": None},
           "expiryCheck": {"valid": True}, "statusCheck": [], "claims": {}}


def test_verify_reports_success_for_a_credential_that_passes_every_check() -> None:
    client, seen = mock_client(lambda r: httpx.Response(200, json=SUCCESS))
    assert iv.verify(client, CREDENTIAL) == "SUCCESS"
    (req,) = seen
    assert (req.method, str(req.url)) == ("POST", f"{iv.VERIFY_SERVICE}/v1/verify/v2/vc-verification")
    body = json.loads(req.content)
    assert json.loads(body["verifiableCredential"]) == CREDENTIAL
    assert body["skipStatusChecks"] is True


SIGNATURE_FAILED = {
    "allChecksSuccessful": False, "expiryCheck": None, "statusCheck": [], "claims": {},
    "schemaAndSignatureCheck": {"valid": False, "error": {"errorCode": "ERR_SIGNATURE_VERIFICATION_FAILED",
                                                          "errorMessage": "Verification Failed"}},
}


def test_verify_reports_the_error_code_of_a_failed_signature() -> None:
    client, _ = mock_client(lambda r: httpx.Response(200, json=SIGNATURE_FAILED))
    assert iv.verify(client, CREDENTIAL) == "ERR_SIGNATURE_VERIFICATION_FAILED"


def signature_checking_verifier(request: httpx.Request) -> httpx.Response:
    """Answers SUCCESS for the untouched CREDENTIAL and a signature failure for anything else."""
    sent = json.loads(json.loads(request.content)["verifiableCredential"])
    return httpx.Response(200, json=SUCCESS if sent == CREDENTIAL else SIGNATURE_FAILED)


def test_verify_step_passes_when_the_credential_verifies_and_its_tampered_copy_does_not() -> None:
    client, seen = mock_client(signature_checking_verifier)
    assert iv.verify_step(client, CREDENTIAL) == []
    original, tampered = (json.loads(json.loads(r.content)["verifiableCredential"]) for r in seen)
    assert original == CREDENTIAL
    changed = {k for k in CREDENTIAL["credentialSubject"]
               if tampered["credentialSubject"].get(k) != CREDENTIAL["credentialSubject"][k]}
    assert changed == {"id"}, f"expected credentialSubject.id changed, got {changed}"
    original_id, tampered_id = CREDENTIAL["credentialSubject"]["id"], tampered["credentialSubject"]["id"]
    assert re.fullmatch(r"did:jwk:[A-Za-z0-9_-]+", tampered_id), f"tampered id must stay a valid did:jwk, got {tampered_id!r}"
    assert tampered_id != original_id and len(tampered_id) == len(original_id) and tampered_id[:-1] == original_id[:-1]
    assert {k: v for k, v in tampered.items() if k != "credentialSubject"} == \
        {k: v for k, v in CREDENTIAL.items() if k != "credentialSubject"}


def test_verify_step_fails_when_the_tampered_copy_still_verifies() -> None:
    client, _ = mock_client(lambda r: httpx.Response(200, json=SUCCESS))
    problems = iv.verify_step(client, CREDENTIAL)
    assert len(problems) == 1 and "credentialSubject.id" in problems[0] and "ERR_SIGNATURE_VERIFICATION_FAILED" in problems[0], problems


def test_verify_step_fails_when_the_credential_itself_does_not_verify() -> None:
    client, _ = mock_client(lambda r: httpx.Response(200, json=SIGNATURE_FAILED))
    problems = iv.verify_step(client, CREDENTIAL)
    assert problems and "SUCCESS" in problems[0], problems


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
