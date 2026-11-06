"""The Authorization Server is a per-environment setting of each installation.

installations/<name>/authorization-server.env holds the stand-in realm's values, each overridable in vc-stack/.env
(an environment's own server). Certify's properties and Mimoto's issuer list are rendered here from those settings, as
Compose and Certify resolve them, for the stand-in and for the campus realm, and no tracked file outside the settings
names a realm path.

Host only, no Docker. Run: python3 vc-stack/test_authorization_server.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALLATIONS = REPO_ROOT / "installations"
NAMES = sorted(p.parent.name for p in INSTALLATIONS.glob("*/smoke.json"))
sys.path.insert(0, str(REPO_ROOT / "data"))
import render_mimoto_issuers_config as r  # noqa: E402

KEYS = ["AUTH_SERVER_ISSUER", "AUTH_SERVER_JWKS_URL", "AUTH_SERVER_TOKEN_ENDPOINT", "AUTH_SERVER_PUBLIC_URL",
        "AUTH_SERVER_WALLET_CLIENT_ID"]
REALMS = {"ait": "inji", "hackathon": "hackathon"}
# The campus realm of spec-part-2.md → Campus sign-in, on Dev; the client id is a placeholder until campus IT names it.
CAMPUS = "https://oauth-dev.ait-itserv.dpi.ait.ac.th/realms/ait-dev"
CAMPUS_ENV = {
    "AUTH_SERVER_ISSUER": CAMPUS,
    "AUTH_SERVER_JWKS_URL": f"{CAMPUS}/protocol/openid-connect/certs",
    "AUTH_SERVER_TOKEN_ENDPOINT": f"{CAMPUS}/protocol/openid-connect/token",
    "AUTH_SERVER_PUBLIC_URL": CAMPUS,
    "AUTH_SERVER_WALLET_CLIENT_ID": "inji-issuer-mimoto",
}
CERTIFY_DOMAIN = "http://certify-nginx"
# Tracked files that may name a realm path: the settings, documents, tests (their fixtures), the phone's issuer list
# (rendered from the settings and committed), and the hackathon roster, whose authEndpoint is a credential claim.
REALM_PATH_ALLOWED = [
    re.compile(p) for p in (
        r"^installations/[^/]+/authorization-server\.env$",
        r"\.md$",
        r"(^|/)test_[^/]*\.py$",
        r"Test\.java$",
        r"^vc-stack/config/mimoto-issuers-mobile\.json$",
        r"^installations/hackathon/adapter/student_identity_data\.csv$",
    )
]
# A path into one of the installations' stand-in realms.
REALM_PATH = re.compile(r"/realms/(?:%s)\b" % "|".join(
    json.loads((INSTALLATIONS / name / "keycloak-realm.json").read_text(encoding="utf-8"))["realm"] for name in NAMES))


def stand_in(installation: str) -> dict[str, str]:
    realm = f"/realms/{REALMS[installation]}"
    return {
        "AUTH_SERVER_ISSUER": f"http://keycloak:8080{realm}",
        "AUTH_SERVER_JWKS_URL": f"http://host.docker.internal:9080{realm}/protocol/openid-connect/certs",
        "AUTH_SERVER_TOKEN_ENDPOINT": f"http://keycloak:8080{realm}/protocol/openid-connect/token",
        "AUTH_SERVER_PUBLIC_URL": f"http://localhost:9080{realm}",
        "AUTH_SERVER_WALLET_CLIENT_ID": "wallet-demo",
    }


def certify_properties(installation: str, env: dict[str, str]) -> dict[str, str]:
    """The installation's Certify properties with their placeholders resolved as Certify sees them in the container."""
    known = {**r.authorization_server(installation, env), "mosip.certify.domain.url": CERTIFY_DOMAIN}
    text = (INSTALLATIONS / installation / "certify-installation.properties").read_text(encoding="utf-8")
    props = {}
    for line in text.replace("\\\n", "").splitlines():
        if line.strip() and not line.startswith("#"):
            key, value = line.split("=", 1)
            props[key] = re.sub(r"\$\{([^}]+)\}", lambda m: known.get(m.group(1), m.group(0)), value)
    return props


def mimoto_issuer(installation: str, env: dict[str, str]) -> dict:
    out = r.render({"INSTALLATION": installation, **env})
    return json.loads(out[INSTALLATIONS / installation / "mimoto-issuers-config.json"])["issuers"][0]


def test_every_installation_has_the_same_settings_each_overridable() -> None:
    assert set(NAMES) == set(REALMS), NAMES
    for name in NAMES:
        lines = [line for line in (INSTALLATIONS / name / "authorization-server.env").read_text(encoding="utf-8")
                 .splitlines() if line.strip() and not line.startswith("#")]
        assert [line.split("=", 1)[0] for line in lines] == KEYS, (name, lines)
        for line in lines:
            key = line.split("=", 1)[0]
            assert line.startswith(f"{key}=${{{key}:-") and line.endswith("}"), (name, line)


def test_the_stand_in_is_the_default_and_the_values_are_unchanged() -> None:
    for name in NAMES:
        assert r.authorization_server(name, {}) == stand_in(name), name


def test_the_stand_in_follows_the_keycloak_bases_of_the_environment() -> None:
    env = {"KEYCLOAK_PUBLIC_BASE_URL": "https://keycloak.demo.example", "KEYCLOAK_INTERNAL_BASE_URL": "http://kc:1"}
    settings = r.authorization_server("ait", env)
    assert settings["AUTH_SERVER_PUBLIC_URL"] == "https://keycloak.demo.example/realms/inji"
    assert settings["AUTH_SERVER_JWKS_URL"] == "http://kc:1/realms/inji/protocol/openid-connect/certs"
    assert settings["AUTH_SERVER_ISSUER"] == "http://keycloak:8080/realms/inji"
    # Compose's ${X:-default} takes the default for an empty value too.
    assert r.authorization_server("ait", {"AUTH_SERVER_ISSUER": ""}) == stand_in("ait")


def test_an_environment_points_an_installation_at_the_campus_realm() -> None:
    for name in NAMES:
        assert r.authorization_server(name, CAMPUS_ENV) == CAMPUS_ENV, name


def test_certify_trusts_the_configured_server() -> None:
    for name in NAMES:
        for env, want in ((stand_in(name), stand_in(name)), (CAMPUS_ENV, CAMPUS_ENV)):
            props = certify_properties(name, env)
            assert props["mosip.certify.authorization.url"] == want["AUTH_SERVER_ISSUER"], (name, props)
            assert props["mosip.certify.authn.issuer-uri"] == want["AUTH_SERVER_ISSUER"], (name, props)
            assert props["mosip.certify.authn.jwk-set-uri"] == want["AUTH_SERVER_JWKS_URL"], (name, props)
            audiences = re.findall(r"'([^']*)'", props["mosip.certify.authn.allowed-audiences"])
            assert audiences == [
                want["AUTH_SERVER_WALLET_CLIENT_ID"],
                "http://certify-nginx:80/v1/certify/issuance/credential",
                "http://certify-nginx/v1/certify/issuance/credential",
                f"{CERTIFY_DOMAIN}/v1/certify/issuance/credential",
            ], (name, audiences)


def test_mimotos_issuer_list_names_the_configured_server() -> None:
    for name in NAMES:
        for env, want in (({}, stand_in(name)), (CAMPUS_ENV, CAMPUS_ENV)):
            issuer = mimoto_issuer(name, env)
            assert issuer["authorization_audience"] == want["AUTH_SERVER_TOKEN_ENDPOINT"], (name, issuer)
            assert issuer["proxy_token_endpoint"] == want["AUTH_SERVER_TOKEN_ENDPOINT"], (name, issuer)
            assert issuer["client_id"] == want["AUTH_SERVER_WALLET_CLIENT_ID"], (name, issuer)


def test_the_phones_metadata_maps_the_issuer_to_its_public_url() -> None:
    public = {"CERTIFY_PUBLIC_BASE_URL": "https://api.demo.example", "KEYCLOAK_PUBLIC_BASE_URL": "https://kc.demo.example"}
    snippet = r.render({"INSTALLATION": "ait", **public})[r.GATEWAY_SNIPPET_OUT]
    assert ("""'"authorization_servers":["http://keycloak:8080/realms/inji"]' """
            """'"authorization_servers":["https://kc.demo.example/realms/inji"]'""") in snippet
    snippet = r.render({"INSTALLATION": "ait", **public, **CAMPUS_ENV})[r.GATEWAY_SNIPPET_OUT]
    assert f"""'"authorization_servers":["{CAMPUS}"]' '"authorization_servers":["{CAMPUS}"]'""" in snippet


def test_no_tracked_file_outside_the_settings_names_a_realm_path() -> None:
    tracked = subprocess.run(["git", "ls-files"], cwd=REPO_ROOT, check=True, capture_output=True, text=True).stdout
    offenders = []
    for path in tracked.splitlines():
        if any(p.search(path) for p in REALM_PATH_ALLOWED) or not (REPO_ROOT / path).is_file():
            continue
        try:
            text = (REPO_ROOT / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        offenders += [f"{path}: {m}" for m in REALM_PATH.findall(text)]
    assert not offenders, offenders


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
