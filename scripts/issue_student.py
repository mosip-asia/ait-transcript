#!/usr/bin/env python3
"""Headless OpenID4VCI Pre-Authorized Issuance Client for Inji Certify.

Usage:
    uv run python scripts/issue_student.py [student_id]
    uv run python scripts/issue_student.py st123456 --output credential.json
"""

import argparse
import base64
import json
import os
import sys
import time
from urllib.parse import unquote

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

DEFAULT_CERTIFY_URL = os.environ.get("CERTIFY_BASE_URL", "http://localhost:9091")
DEFAULT_CONFIG_ID = os.environ.get("CREDENTIAL_CONFIG_ID", "ait-transcript")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_json(obj: dict) -> str:
    return _b64url(json.dumps(obj, separators=(",", ":")).encode())


def build_proof(
    key: ec.EllipticCurvePrivateKey,
    client_id: str,
    audience: str,
    nonce: str,
    now: int,
) -> str:
    pub = key.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": _b64url(pub.x.to_bytes(32, "big")),
        "y": _b64url(pub.y.to_bytes(32, "big")),
    }
    header = {
        "alg": "ES256",
        "typ": "openid4vci-proof+jwt",
        "kid": f"did:jwk:{_b64url_json(jwk)}#0",
    }
    claims = {
        "iss": client_id,
        "aud": audience,
        "nonce": nonce,
        "iat": now,
        "exp": now + 300,
    }
    signing_input = f"{_b64url_json(header)}.{_b64url_json(claims)}"
    r, s = decode_dss_signature(
        key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256()))
    )
    signature_bytes = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{signing_input}.{_b64url(signature_bytes)}"


def issue_transcript(
    student_id: str,
    certify_url: str = DEFAULT_CERTIFY_URL,
    config_id: str = DEFAULT_CONFIG_ID,
    output_path: str | None = None,
) -> dict:
    print(f"[*] Starting issuance for student: {student_id}")
    print(f"[*] Target Certify instance: {certify_url}")
    print(f"[*] Credential Configuration: {config_id}")

    with httpx.Client(timeout=30) as client:
        # 1. Pre-authorized data offer
        print("\n[1] Staging pre-authorized issuance offer...")
        offer_resp = client.post(
            f"{certify_url}/v1/certify/pre-authorized-data",
            json={
                "credential_configuration_id": config_id,
                "claims": {"registrationNo": student_id},
            },
        )
        if offer_resp.status_code != 200:
            print(f"[-] Offer failed: {offer_resp.status_code} {offer_resp.text}")
            sys.exit(1)

        offer_uri = offer_resp.json()["credential_offer_uri"]
        offer_id = offer_uri.split("credential-offer-data%2F")[-1]
        print(f"    Offer ID: {offer_id}")

        # 2. Get pre-authorized code
        print("\n[2] Fetching pre-authorized code...")
        offer_data = client.get(
            f"{certify_url}/v1/certify/credential-offer-data/{offer_id}"
        ).json()
        pre_auth_code = offer_data["grants"][
            "urn:ietf:params:oauth:grant-type:pre-authorized_code"
        ]["pre-authorized_code"]
        print(f"    Pre-auth code: {pre_auth_code}")

        # 3. Exchange for token
        print("\n[3] Exchanging code for Inji Certify access token...")
        token_resp = client.post(
            f"{certify_url}/v1/certify/oauth/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:pre-authorized_code",
                "pre-authorized_code": pre_auth_code,
            },
        )
        if token_resp.status_code != 200:
            print(f"[-] Token exchange failed: {token_resp.status_code} {token_resp.text}")
            sys.exit(1)

        token_data = token_resp.json()
        access_token = token_data["access_token"]
        c_nonce = token_data.get("c_nonce")
        print(f"    Access token obtained. c_nonce: {c_nonce}")

        # 4. Fetch metadata for format and definition
        metadata = client.get(
            f"{certify_url}/.well-known/openid-credential-issuer"
        ).json()
        config = metadata["credential_configurations_supported"].get(config_id)
        if not config:
            print(f"[-] Credential configuration '{config_id}' not found in Certify metadata.")
            sys.exit(1)
        definition = config["credential_definition"]

        # 5. Build client Proof JWT (did:jwk)
        print("\n[4] Generating cryptographic Proof-of-Possession JWT...")
        client_id = token_data.get("client_id", "")
        key = ec.generate_private_key(ec.SECP256R1())
        proof = build_proof(
            key, client_id, metadata["credential_issuer"], c_nonce, int(time.time())
        )

        # 6. Request VC
        print("\n[5] Requesting signed Verifiable Credential from Certify...")
        vc_resp = client.post(
            f"{certify_url}/v1/certify/issuance/credential",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "format": config["format"],
                "credential_definition": {
                    "@context": definition["@context"],
                    "type": definition["type"],
                },
                "proof": {"proof_type": "jwt", "jwt": proof},
            },
        )
        if vc_resp.status_code != 200:
            print(f"[-] Issuance failed: {vc_resp.status_code} {vc_resp.text}")
            sys.exit(1)

        vc = vc_resp.json()
        print("\n[+] SUCCESS! Verifiable Credential Issued:")
        formatted_vc = json.dumps(vc, indent=2)
        print(formatted_vc)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(formatted_vc)
            print(f"\n[+] Saved credential to {output_path}")

        return vc


def main():
    parser = argparse.ArgumentParser(
        description="Headless OpenID4VCI Pre-Authorized Issuance Client for Inji Certify"
    )
    parser.add_argument(
        "student_id",
        nargs="?",
        default="st123456",
        help="Student Registration Number to issue (e.g. st123456, st123457)",
    )
    parser.add_argument(
        "--certify-url",
        default=DEFAULT_CERTIFY_URL,
        help=f"Base URL of Certify Nginx ingress (default: {DEFAULT_CERTIFY_URL})",
    )
    parser.add_argument(
        "--config-id",
        default=DEFAULT_CONFIG_ID,
        help=f"Credential Configuration ID (default: {DEFAULT_CONFIG_ID})",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Path to write the issued credential JSON file",
    )
    args = parser.parse_args()

    issue_transcript(
        student_id=args.student_id,
        certify_url=args.certify_url,
        config_id=args.config_id,
        output_path=args.output,
    )


if __name__ == "__main__":
    main()
