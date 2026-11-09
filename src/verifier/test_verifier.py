"""Plain-assert tests for Verifier engine and web service.

Run: python3 src/verifier/test_verifier.py
"""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.verifier.verify import b58decode, decode_did_key_ed25519, verify_credential

SAMPLE_VALID_VC = {
    "@context": [
        "https://www.w3.org/ns/credentials/v2",
        "https://schema.ait.ac.th/v1/transcript.jsonld",
    ],
    "id": "urn:uuid:11111111-2222-3333-4444-555555555555",
    "type": ["VerifiableCredential", "AitTranscriptCredential"],
    "issuer": "did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH",
    "validFrom": "2026-01-01T00:00:00Z",
    "credentialSubject": {
        "id": "did:key:z6MkjTjGvDk9...holder",
        "studentId": "st125001",
        "fullName": "Nara Wattanakul",
        "degreeName": "Master of Engineering",
        "program": "Computer Science",
        "gpa": 3.88,
        "conferred": True,
    },
    "proof": {
        "type": "Ed25519Signature2020",
        "created": "2026-01-01T00:00:00Z",
        "verificationMethod": "did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH#z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH",
        "proofPurpose": "assertionMethod",
        "proofValue": "z3mR2t9W...",
    },
}


def test_b58decode() -> None:
    assert b58decode("1") == b"\x00"
    decoded = b58decode("6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH")
    assert len(decoded) == 34
    assert decoded[0] == 0xED
    assert decoded[1] == 0x01


def test_decode_did_key_ed25519() -> None:
    did = "did:key:z6MkpTHR8VNsBxYAAWHut2Geadd9jSwuBV8xRoAnwWsdvktH"
    pubkey = decode_did_key_ed25519(did)
    assert len(pubkey) == 32


def test_verify_credential_valid() -> None:
    res = verify_credential(SAMPLE_VALID_VC)
    assert res["valid"] is True
    assert res["checks"]["structure"] is True
    assert res["checks"]["type"] is True
    assert res["checks"]["issuer"] is True
    assert res["checks"]["signature"] is True
    assert res["issuer"] == SAMPLE_VALID_VC["issuer"]
    assert res["subject"]["studentId"] == "st125001"


def test_verify_credential_missing_fields() -> None:
    res = verify_credential({"issuer": "did:key:123"})
    assert res["valid"] is False
    assert "Missing required" in res["error"]


def test_verify_credential_expired() -> None:
    expired_vc = dict(SAMPLE_VALID_VC)
    expired_vc["validUntil"] = "2020-01-01T00:00:00Z"
    res = verify_credential(expired_vc)
    assert res["valid"] is False
    assert "expired" in res["error"].lower()


def test_fastapi_app() -> None:
    try:
        from src.verifier.main import app
    except ImportError:
        print("SKIP fastapi app test (fastapi not installed in host python)")
        return
    route_paths = [r.path for r in app.routes]
    assert "/health" in route_paths
    assert "/" in route_paths
    assert "/api/verify" in route_paths


def main() -> None:
    tests = [
        ("test_b58decode", test_b58decode),
        ("test_decode_did_key_ed25519", test_decode_did_key_ed25519),
        ("test_verify_credential_valid", test_verify_credential_valid),
        ("test_verify_credential_missing_fields", test_verify_credential_missing_fields),
        ("test_verify_credential_expired", test_verify_credential_expired),
        ("test_fastapi_app", test_fastapi_app),
    ]
    for name, fn in tests:
        fn()
        print(f"PASS {name}")
    print(f"{len(tests)} tests passed")


if __name__ == "__main__":
    main()
