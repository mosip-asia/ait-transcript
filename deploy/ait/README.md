# AIT installation

The files the stack mounts when `INSTALLATION=ait` (in `.env` or the environment): `./scripts/deploy.sh ait`. Certify's seed runs only on a fresh database, so switching a local stack from another installation needs `--wipe` (`./scripts/deploy.sh ait --wipe`), which also renews the signing key and `did:key`.

How the infra team deploys this directory (the service set, every variable and mounted file, the secrets a deployment replaces, and the ingress allowlist, which is the same for both installations) is the configuration contract, [`docs/project/issuer-v0.1/configuration-contract.md`](../../docs/project/issuer-v0.1/configuration-contract.md); this file lists the values. The committed Gateway token, the realm's users and their passwords, and the `smoke` client are test-only fixtures that a deployment replaces.

| File | Read by | Notes |
|---|---|---|
| `certify-installation.properties` | Certify (`installation` profile) | Certify's settings, including the Authorization Server keys (read from `authorization-server.env`) and the Data-provider plugin's keys (below); `did-url` is `CERTIFY_DID`, set in `.env` |
| `authorization-server.env` | Certify and the Portal (`demo-app`), through Compose's `env_file` | The Authorization Server this installation trusts: issuer, JWKS URL, token endpoint, browser URL and wallet client id, each `${KEY:-<stand-in realm `inji`'s value>}`. An environment points the installation at another server by setting the same variable in `.env`, with no file changed. Certify's properties, Mimoto's issuer template and the Portal's sign-out link read these settings; the configuration contract's Authorization Server section lists them |
| `certify_seed.sql` | Postgres, first start only | The `credential_config` row for `ait-transcript`, mounted after `deploy/base/certify_init.sql` |
| `keycloak-realm.json` | Keycloak (`--import-realm`) | Realm `inji`: one user per CSV `id`, the `wallet-demo` client, the test-only `smoke` client, the `ait_transcript_vc_ldp` scope |
| `gateway.env` | The Gateway (`gateway/`), through Compose's `env_file` | Its settings, listed below |
| `mimoto-issuers-config.json.template` | `src/tools/render_mimoto_issuers_config.py` | Mimoto's issuer list (wallet test harness), with `${INJI_WEB_URL}` left to fill |
| `public-gateway-mobile.conf.template` | `src/tools/render_mimoto_issuers_config.py` | The `api.` gateway's phone-only nginx locations. Its presence makes the script also render `deploy/base/mimoto-issuers-mobile.json` and `public-gateway-mobile.conf` (mounted by Compose); an installation without it renders only Mimoto's list |
| `mimoto-issuers-config.json` | Mimoto, Inji Web | Rendered from the template. Git-ignored |
| `adapter/student_identity_data.csv` | The mock adapter (`src/adapter/`, mounted read-only at `/data`) | Mock transcript records. After the claim columns come `holds` (a JSON list), `conferralStatus` and `balance`, the eligibility attributes. To change a student's eligibility edit the file (or regenerate via `src/tools/generate_csv.py`): the adapter reads it on every request, no restart of anything |
| `smoke.json` | `scripts/smoke-test.sh`, `tests/` | The installation's test fixtures, below |

The installation's own values:

- Authorization Server: the stand-in Keycloak realm `inji` (`http://keycloak:8080/realms/inji`) unless the environment sets `AUTH_SERVER_*` in `.env`; see `authorization-server.env`
- Keycloak realm: `inji`, with wallet client `wallet-demo`; every user's password is `inji` (test-only)
- Test-only client `smoke`: public, direct-access grant, the `ait_transcript_vc_ldp` scope and a hardcoded `client_id` claim; only `scripts/smoke-test.sh` uses it
- Scope: `ait_transcript_vc_ldp`
- Credential configuration: `ait-transcript`, type `AitTranscriptCredential`
- Issuer display: "AIT University Registrar"; Mimoto issuer id `AITUniversity`
- Adapter CSV: `adapter/student_identity_data.csv`, one row per degree, keyed by the `id` column (the Keycloak username)
- Certify's Data-provider plugin: the ten keys of contracts.md section 2a, in `certify-installation.properties` (edit the file and restart Certify, `docker compose restart certify`), with the gate on (`mosip.certify.gateway.enabled=true`; a no-Gateway form sets it off in Certify's environment). Here the Gateway's `read-timeout-ms` is `15000`, well above the 3 s of the Gateway's one Adapter call, and `auth-token` equals `GATEWAY_AUTH_TOKEN` (committed value `dev-only-ait-gateway-token`, test-only)
- Gateway settings: `gateway.env`, whose variables the [configuration contract](../../docs/project/issuer-v0.1/configuration-contract.md)'s `gateway` section lists (edit the file and recreate the container, `docker compose up -d gateway`). Here `GATEWAY_ENABLED_SCOPES` is `ait_transcript_vc_ldp`
- Test fixtures, in `smoke.json`, a list with one entry per credential type (here one): `credentialConfig` (`ait-transcript`, the only configuration Certify must list), `scope`, `eligible` (`ait-2026-0001`, issued and verified, then tampered), `unknown` (`ait-2026-9999`, a realm user the adapter has no record of: `no_record` from the Gateway and from Certify), `refused` (each persona with the check that fails: `ait-2026-0002` `no_holds`, `ait-2026-0003` `conferred`, `ait-2026-0004` `zero_balance`), `tamper` (the claim paths changed in the tampered copies: `fullName`, `courses[0].courses[0].grade`), `mimotoTemplate` (the Inji Web PDF template in `deploy/base/`)
