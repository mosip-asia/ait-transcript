"""Scripted issuance and verification for vc-stack/smoke.sh, without a browser or a wallet.

issue:  a token from the installation's realm (direct-access grant on the test-only `smoke` client, for the
        persona and the credential scope), a proof JWT signed with a fresh key as did:jwk, Certify's
        /issuance/credential; the credential is written to a file.
verify: verify-service's v2 vc-verification must answer SUCCESS for that file, and
        ERR_SIGNATURE_VERIFICATION_FAILED for each copy with one claim changed: the holder DID
        (credentialSubject.id), fullName, and one grade inside courses.
refused: the same credential request must be refused with the OpenID4VCI error body whose `error` is the given
        code (checklist_failed for a persona the Gateway's checklist refuses, gateway_error with the Gateway down).

Deviation from the ticket's "Ed25519": the proof key is ES256 (P-256), because the seed's proof_types_supported
allows RS256/ES256 only, and Inji Web uses ES256.

It runs in the demo-app image (httpx, cryptography) inside the Docker network, where the URLs below resolve and
the token issuer is http://keycloak:8080 (the one Certify accepts), from the repository root (it reads
installations/<name>/keycloak-realm.json). demo-app does not mount vc-stack/, so the run mounts this file:

  docker compose -f vc-stack/docker-compose.yaml run --rm --no-deps \\
      -v "$PWD/vc-stack/issue_and_verify.py:/demo/vc-stack/issue_and_verify.py:ro" demo-app \\
      python vc-stack/issue_and_verify.py issue ait ait-2026-0001 ait_transcript_vc_ldp .demo-state/smoke-credential.json
  (same, ending in: python vc-stack/issue_and_verify.py verify .demo-state/smoke-credential.json)
  (same, ending in: python vc-stack/issue_and_verify.py refused ait ait-2026-0002 ait_transcript_vc_ldp checklist_failed)
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import sys
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

# The same variable sets Certify's accepted token issuer (docker-compose.yaml).
KEYCLOAK = os.environ.get("KEYCLOAK_DOCKER_AUTH_SERVER", "http://keycloak:8080")
CERTIFY = "http://certify-nginx"
VERIFY_SERVICE = "http://verify-service:8080"
SMOKE_CLIENT = "smoke"
PROOF_LIFETIME = 300


def _json(resp: httpx.Response) -> dict:
    if resp.is_error:
        raise RuntimeError(f"{resp.request.method} {resp.request.url} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_json(obj: dict) -> str:
    return _b64url(json.dumps(obj, separators=(",", ":")).encode())


def request_token(client: httpx.Client, realm: str, persona: str, password: str, scope: str) -> dict:
    """Direct-access grant on the test-only smoke client; the response carries the access token and c_nonce."""
    return _json(client.post(
        f"{KEYCLOAK}/realms/{realm}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": SMOKE_CLIENT, "username": persona, "password": password,
              "scope": scope},
    ))


def build_proof(key: ec.EllipticCurvePrivateKey, client_id: str, audience: str, nonce: str, now: int) -> str:
    """OpenID4VCI proof JWT, ES256, naming its own P-256 public key as did:jwk in kid."""
    pub = key.public_key().public_numbers()
    jwk = {"kty": "EC", "crv": "P-256", "x": _b64url(pub.x.to_bytes(32, "big")), "y": _b64url(pub.y.to_bytes(32, "big"))}
    header = {"alg": "ES256", "typ": "openid4vci-proof+jwt", "kid": f"did:jwk:{_b64url_json(jwk)}#0"}
    claims = {"iss": client_id, "aud": audience, "nonce": nonce, "iat": now, "exp": now + PROOF_LIFETIME}
    signing_input = f"{_b64url_json(header)}.{_b64url_json(claims)}"
    r, s = decode_dss_signature(key.sign(signing_input.encode(), ec.ECDSA(hashes.SHA256())))
    return f"{signing_input}.{_b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"


def credential_request(client: httpx.Client, installation: str, persona: str, scope: str) -> httpx.Response:
    """The persona's OpenID4VCI credential request, the same one a wallet makes, answered as Certify answers it."""
    realm = json.loads((Path("installations") / installation / "keycloak-realm.json").read_text(encoding="utf-8"))
    user = next(u for u in realm["users"] if u["username"] == persona)
    password = next(c["value"] for c in user["credentials"] if c["type"] == "password")

    metadata = _json(client.get(f"{CERTIFY}/.well-known/openid-credential-issuer"))
    config = next(c for c in metadata["credential_configurations_supported"].values() if c.get("scope") == scope)
    definition = config["credential_definition"]

    token = request_token(client, realm["realm"], persona, password, scope)
    proof = build_proof(ec.generate_private_key(ec.SECP256R1()), SMOKE_CLIENT, metadata["credential_issuer"],
                        token["c_nonce"], int(time.time()))
    return client.post(
        f"{CERTIFY}/v1/certify/issuance/credential",
        headers={"Authorization": f"Bearer {token['access_token']}"},
        json={
            "format": config["format"],
            "credential_definition": {"@context": definition["@context"], "type": definition["type"]},
            "proof": {"proof_type": "jwt", "jwt": proof},
        },
    )


def issue(client: httpx.Client, installation: str, persona: str, scope: str) -> dict:
    """One credential for the persona."""
    return _json(credential_request(client, installation, persona, scope))["credential"]


def refusal_code(resp: httpx.Response) -> str:
    """The `error` of Certify's OpenID4VCI error body for a refused credential request."""
    if not resp.is_error:
        raise RuntimeError(f"expected a refusal, got {resp.status_code}: {resp.text}")
    return resp.json().get("error", "")


def verify(client: httpx.Client, credential: dict) -> str:
    """verify-service's answer as one word: SUCCESS, else the signature check's error code."""
    result = _json(client.post(
        f"{VERIFY_SERVICE}/v1/verify/v2/vc-verification",
        json={"verifiableCredential": json.dumps(credential), "skipStatusChecks": True},
    ))
    if result.get("allChecksSuccessful"):
        return "SUCCESS"
    error = (result.get("schemaAndSignatureCheck") or {}).get("error") or {}
    return error.get("errorCode") or f"FAILED {json.dumps(result)}"


def tampered_copies(credential: dict) -> dict[str, dict]:
    """Copies of a transcript credential, each with one signed claim changed, keyed by the claim's path."""
    subject = credential["credentialSubject"]
    holder = subject["id"]
    courses = copy.deepcopy(subject["courses"])
    course = courses[0]["courses"][0]
    course["grade"] = "F" if course["grade"] != "F" else "A"
    changes = {
        # Swap the last character for another base64url one: the value stays syntactically a valid did:jwk IRI
        # (the decoded JWK need not be valid), so verify-service reaches the signature check.
        "id": {"id": holder[:-1] + ("A" if holder[-1] != "A" else "B")},
        "fullName": {"fullName": subject["fullName"] + " Jr"},
        "courses[0].courses[0].grade": {"courses": courses},
    }
    return {path: {**credential, "credentialSubject": {**subject, **change}} for path, change in changes.items()}


def verify_step(client: httpx.Client, credential: dict) -> list[str]:
    """The credential must verify; each tampered copy (the holder, fullName, a grade inside courses) must fail its signature.

    Returns what went wrong, empty when every outcome is as expected.
    """
    problems = []
    outcome = verify(client, credential)
    if outcome != "SUCCESS":
        problems.append(f"credential: expected SUCCESS, got {outcome}")
    for path, tampered in tampered_copies(credential).items():
        outcome = verify(client, tampered)
        if outcome != "ERR_SIGNATURE_VERIFICATION_FAILED":
            problems.append(f"tampered credentialSubject.{path}: expected ERR_SIGNATURE_VERIFICATION_FAILED, got {outcome}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    steps = parser.add_subparsers(dest="step", required=True)
    p_issue = steps.add_parser("issue", help="issue a credential and write it to OUT")
    p_issue.add_argument("installation")
    p_issue.add_argument("persona", help="Keycloak username, e.g. ait-2026-0001")
    p_issue.add_argument("scope", help="credential scope, e.g. ait_transcript_vc_ldp")
    p_issue.add_argument("out", type=Path)
    p_verify = steps.add_parser("verify", help="verify a credential file, then a tampered copy")
    p_verify.add_argument("credential", type=Path)
    p_refused = steps.add_parser("refused", help="the credential request must be refused with CODE")
    p_refused.add_argument("installation")
    p_refused.add_argument("persona")
    p_refused.add_argument("scope")
    p_refused.add_argument("code", help="the expected OpenID4VCI error code, e.g. checklist_failed")
    args = parser.parse_args()

    with httpx.Client(timeout=60) as client:
        if args.step == "refused":
            code = refusal_code(credential_request(client, args.installation, args.persona, args.scope))
            if code != args.code:
                print(f"FAIL: {args.persona}: expected the error {args.code}, got {code!r}", file=sys.stderr)
                return 1
            print(f"OK: {args.scope} for {args.persona} refused with {code}")
            return 0
        if args.step == "issue":
            credential = issue(client, args.installation, args.persona, args.scope)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(credential, indent=2), encoding="utf-8")
            print(f"OK: issued {args.scope} for {args.persona} -> {args.out}")
            return 0
        credential = json.loads(args.credential.read_text(encoding="utf-8"))
        problems = verify_step(client, credential)
        if problems:
            for problem in problems:
                print(f"FAIL: {problem}", file=sys.stderr)
            return 1
        print(f"OK: credential verifies (SUCCESS); tampered {', '.join(tampered_copies(credential))} each fail"
              " (ERR_SIGNATURE_VERIFICATION_FAILED)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
