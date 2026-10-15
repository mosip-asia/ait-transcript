"""Plain-assert tests for render_mimoto_issuers_config.py.

Run: python3 data/test_render_mimoto_issuers_config.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import render_mimoto_issuers_config as r  # noqa: E402

PUBLIC = {
    "INJI_WEB_URL": "https://wallet.demo.example",
    "CERTIFY_PUBLIC_BASE_URL": "https://api.demo.example",
    "KEYCLOAK_PUBLIC_BASE_URL": "https://keycloak.demo.example",
}


def _mobile_issuer(out: dict[str, str]) -> dict:
    return json.loads(out[r.MOBILE_ISSUERS_OUT.name])["response"]["issuers"][0]


def test_mimoto_file_ignores_mobile_settings() -> None:
    # Mimoto and Inji Web read this file; the phone settings must not leak into it.
    with_mobile = r.render(PUBLIC)[r.OUT.name]
    web_only = r.render({"INJI_WEB_URL": PUBLIC["INJI_WEB_URL"]})[r.OUT.name]
    assert with_mobile == web_only
    issuer = json.loads(with_mobile)["issuers"][0]
    assert issuer["redirect_uri"] == "https://wallet.demo.example/redirect"
    assert issuer["credential_issuer_host"] == "http://host.docker.internal:9091"


def test_public_mobile_list_is_phone_reachable() -> None:
    out = r.render(PUBLIC)
    issuer = _mobile_issuer(out)
    assert issuer["credential_issuer_host"] == "https://api.demo.example"
    assert issuer["wellknown_endpoint"] == "https://api.demo.example/.well-known/openid-credential-issuer"
    assert issuer["redirect_uri"] == r.MOBILE_REDIRECT_URI
    assert issuer["token_endpoint"] == "https://api.demo.example/v1/mimoto/get-token/AITUniversity"
    # Mimoto rejects an issuer whose token_endpoint does not end in its id.
    assert issuer["token_endpoint"].rsplit("/", 1)[-1] == issuer["issuer_id"]
    assert "host.docker.internal" not in out[r.MOBILE_ISSUERS_OUT.name]
    assert "localhost" not in out[r.MOBILE_ISSUERS_OUT.name]


def test_public_snippet_swaps_only_authorization_servers() -> None:
    snippet = r.render(PUBLIC)[r.GATEWAY_SNIPPET_OUT.name]
    assert "location = /v1/mimoto/issuers" in snippet
    assert "location = /.well-known/openid-credential-issuer" in snippet
    assert (
        """sub_filter '"authorization_servers":["http://keycloak:8080/realms/inji"]' """
        """'"authorization_servers":["https://keycloak.demo.example/realms/inji"]';"""
    ) in snippet
    # Variable proxy_pass must carry no URI part (wiki/guides/vc-download-troubleshooting.md #3).
    assert "proxy_pass http://$certify_nginx_upstream;" in snippet


def test_local_run_leaves_gateway_alone() -> None:
    out = r.render({})
    assert all(line.startswith("#") for line in out[r.GATEWAY_SNIPPET_OUT.name].splitlines())
    mimoto_list = json.loads(out[r.OUT.name])["issuers"][0]
    assert _mobile_issuer(out) == mimoto_list


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)} tests passed")
