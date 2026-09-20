"""Inji Web OpenId4VCI readiness — prevents VC download regressions.

Config checks (no Docker): token_endpoint same-origin :4004, Keycloak redirect, Mimoto Keycloak URLs.

Live checks (--live, stack must be up): Mimoto issuers/configuration APIs and that
credentials/download is reachable via the Inji Web proxy (not blocked with 403).

Full browser OAuth + PDF is still manual (PRD §9); this guards the misconfigurations that
caused empty issuers, Keycloak not loading, and "session is not valid" on download.

Run:
  python3 vc-stack/test_inji_web_vc_readiness.py
  python3 vc-stack/test_inji_web_vc_readiness.py --live
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

STACK_DIR = Path(__file__).resolve().parent
REPO_ROOT = STACK_DIR.parent

INJI_WEB_ORIGIN = "http://localhost:4004"
KEYCLOAK_PUBLIC = "http://localhost:9080"
ISSUER_ID = "AITUniversity"
MIMOTO_ISSUERS = f"{INJI_WEB_ORIGIN}/v1/mimoto/issuers"
MIMOTO_CONFIG = f"{INJI_WEB_ORIGIN}/v1/mimoto/issuers/{ISSUER_ID}/configuration"
MIMOTO_DOWNLOAD = f"{INJI_WEB_ORIGIN}/v1/mimoto/credentials/download"
EXPECTED_TOKEN = f"{INJI_WEB_ORIGIN}/v1/mimoto/get-token/{ISSUER_ID}"


def _http_json(url: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
        return e.code, payload


def test_issuers_config_token_endpoint_uses_inji_web_proxy() -> None:
    cfg = json.loads((STACK_DIR / "config/mimoto-issuers-config.json").read_text(encoding="utf-8"))
    issuer = cfg["issuers"][0]
    token_ep = issuer["token_endpoint"]
    assert token_ep == EXPECTED_TOKEN, (
        f"token_endpoint must be same-origin Inji Web proxy (expected {EXPECTED_TOKEN}, got {token_ep}). "
        "Re-run vc-stack/bootstrap.sh to refresh issuer config."
    )
    assert issuer["authorization_audience"].startswith("http://keycloak:8080/"), issuer["authorization_audience"]
    assert issuer["proxy_token_endpoint"].startswith("http://keycloak:8080/"), issuer["proxy_token_endpoint"]
    assert issuer["redirect_uri"] == f"{INJI_WEB_ORIGIN}/redirect"


def test_bootstrap_mimoto_public_base_is_4004() -> None:
    text = (STACK_DIR / "bootstrap.sh").read_text(encoding="utf-8")
    assert 'LOCAL_MIMOTO_PUBLIC_BASE_URL="http://localhost:4004"' in text


def test_mimoto_cors_allows_inji_web_host_port() -> None:
    props = (STACK_DIR / "config/mimoto-default.properties").read_text(encoding="utf-8")
    assert "mosip.security.origins=http://localhost:4004" in props, (
        "Mimoto CORS must allow Inji Web on :4004 (not inji's default :3004) or VC download returns 403 "
        "and Inji Web shows 'session is not valid or session is completed'."
    )


def test_mimoto_keycloak_external_is_browser_url() -> None:
    props = (STACK_DIR / "config/mimoto-default.properties").read_text(encoding="utf-8")
    assert "keycloak.external.url=http://localhost:9080" in props
    assert "keycloak.internal.url=http://keycloak:8080" in props


def test_keycloak_wallet_demo_redirect_includes_inji_web() -> None:
    realm = json.loads((STACK_DIR / "config/keycloak-realm.json").read_text(encoding="utf-8"))
    client = next(c for c in realm["clients"] if c["clientId"] == "wallet-demo")
    redirects = client["redirectUris"]
    assert "http://localhost:4004/redirect" in redirects


def test_live_issuer_list_and_configuration() -> None:
    status, payload = _http_json(MIMOTO_ISSUERS)
    assert status == 200, f"GET issuers failed: {status} {payload}"
    issuers = payload.get("response", {}).get("issuers", [])
    assert any(i.get("issuer_id") == ISSUER_ID for i in issuers)

    status, payload = _http_json(MIMOTO_CONFIG)
    assert status == 200, f"GET configuration failed: {status} {payload}"
    assert not payload.get("errors"), f"configuration errors (Keycloak well-known?): {payload.get('errors')}"
    resp = payload.get("response") or {}
    auth_ep = resp.get("authorization_endpoint", "")
    assert auth_ep.startswith(f"{KEYCLOAK_PUBLIC}/"), auth_ep
    supported = resp.get("credentials_supported") or []
    assert any(c.get("name") == "ait-transcript" for c in supported)

    status, payload = _http_json(f"{MIMOTO_ISSUERS}/{ISSUER_ID}")
    assert status == 200
    token_ep = payload.get("response", {}).get("token_endpoint", "")
    assert token_ep == EXPECTED_TOKEN, token_ep


def test_live_download_endpoint_reachable_via_inji_web_proxy() -> None:
    """Without a valid OAuth/PKCE session Mimoto rejects the body — but must not 403 (auth/CORS break)."""
    data = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(
        MIMOTO_DOWNLOAD,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": INJI_WEB_ORIGIN,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw}
    assert status != 403, f"credentials/download returned 403 — Inji Web proxy or Mimoto auth misconfigured: {payload}"
    errors = payload.get("errors") or []
    messages = " ".join(str(e.get("errorMessage", "")) for e in errors).lower()
    assert "invalid code verifier" in messages or "session" in messages or status in (400, 500), (
        f"unexpected download error (want PKCE/session rejection, not infra failure): {status} {payload}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="HTTP checks against running stack")
    args = parser.parse_args()

    test_issuers_config_token_endpoint_uses_inji_web_proxy()
    test_bootstrap_mimoto_public_base_is_4004()
    test_mimoto_cors_allows_inji_web_host_port()
    test_mimoto_keycloak_external_is_browser_url()
    test_keycloak_wallet_demo_redirect_includes_inji_web()

    if args.live:
        test_live_issuer_list_and_configuration()
        test_live_download_endpoint_reachable_via_inji_web_proxy()

    mode = "config + live" if args.live else "config"
    print(f"vc-stack/test_inji_web_vc_readiness.py: all checks passed ({mode})")


if __name__ == "__main__":
    main()
