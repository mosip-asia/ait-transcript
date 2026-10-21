# Hackathon installation

The files the stack mounts when `INSTALLATION=hackathon` (in `vc-stack/.env` or the environment): `INSTALLATION=hackathon ./run-demo.sh`. Everything else in `vc-stack/` is the same for every installation. Certify's seed runs only on a fresh database, so switching a local stack from another installation needs `--wipe` (`INSTALLATION=hackathon ./run-demo.sh --wipe`), which also renews the signing key and `did:key`.

| File | Read by | Notes |
|---|---|---|
| `certify-csvdp-student.properties` | Certify (`csvdp-student` profile) | Certify's settings: the authorization server (realm `hackathon`), the Gateway data-provider plugin's six keys (below), the issuer display; `bootstrap.sh` rewrites `did-url` after a wipe |
| `certify_seed.sql` | Postgres, first start only | The `credential_config` row for `developer-passport`, mounted after `vc-stack/certify_init.sql` |
| `keycloak-realm.json` | Keycloak (`--import-realm`) | Realm `hackathon`: one user per roster `id`, the `wallet-demo` client, the test-only `smoke` client, the `developer_passport_vc_ldp` scope with Certify's audience. `bootstrap.sh` syncs the `wallet-demo` certificate into it |
| `gateway.env` | The Gateway (`gateway/`), through Compose's `env_file` | Its settings, listed below |
| `mimoto-issuers-config.json.template` | `data/render_mimoto_issuers_config.py` | Mimoto's issuer list (wallet test harness), with `${INJI_WEB_URL}` left to fill |
| `mimoto-issuers-config.json` | Mimoto, Inji Web | Rendered by `run-demo.sh` from the template, then patched by `bootstrap.sh`. Git-ignored |
| `adapter/student_identity_data.csv` | The mock adapter (`adapter/`, mounted read-only at `/data`) | The roster, committed and edited by hand: one row per participant, keyed by `id` (the Keycloak username). The adapter reads it on every request, no restart of anything |
| `smoke.json` | `vc-stack/smoke.sh`, `gateway/tests/test_issuances.py`, `vc-stack/test_inji_web_vc_readiness.py` | The installation's test fixtures, below |

The installation's own values:

- Keycloak realm: `hackathon`, with wallet client `wallet-demo`; every user's password is `inji` (test-only)
- Test-only client `smoke`: public, direct-access grant, the `developer_passport_vc_ldp` scope and a hardcoded `client_id` claim; only `vc-stack/issue_and_verify.py` (run by `smoke.sh`) uses it
- Scope: `developer_passport_vc_ldp`
- Credential configuration: `developer-passport`, type `DeveloperPassportCredential`, VCDM 2.0, context `vc-lab/contexts/developer-passport/v1.json` on the VDR (`http://host.docker.internal:9098/contexts/developer-passport/v1.json`); claims `teamId`, `teamName`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`, each the roster column of that name
- Gateway check: `on_roster`, passed when the roster row's `teamId` is not empty; a participant who is not on the roster at all gets `no_record`
- Issuer display: "AIT Hackathon"; Mimoto issuer id `AITHackathon`; credential display "AIT Developer Passport" (colours and labels from `ait-vc`'s row)
- Roster columns: `id`, `teamId`, `teamName`, `winner`, `award`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`. The personas:
  - `hack-2026-0001`: team `team-01` "Sandbox Pioneers", the winning team
  - `hack-2026-0002`: team `team-02` "Chain Gang", not a winner
  - `hack-2026-0003`: registered, no team (empty `teamId`), so `on_roster` fails
- Certify data-provider plugin, in `certify-csvdp-student.properties` (contracts.md section 2a; these six keys and nothing else; edit the file and restart Certify, `docker compose restart certify`):
  - `mosip.certify.integration.data-provider-plugin`: `GatewayDataProviderPlugin`
  - `mosip.certify.integration.scan-base-package`: `asia.mosip.issuer.gateway.plugin`
  - `mosip.certify.gateway.url`: `http://gateway:8000`
  - `mosip.certify.gateway.auth-token`: the shared bearer token; must equal `GATEWAY_AUTH_TOKEN` below (the committed value, `dev-only-hackathon-gateway-token`, is test-only)
  - `mosip.certify.gateway.connect-timeout-ms`: `2000`
  - `mosip.certify.gateway.read-timeout-ms`: `15000`
- Gateway settings, in `gateway.env` (edit the file and recreate the container, `docker compose up -d gateway`):
  - `GATEWAY_ENABLED_SCOPES`: `developer_passport_vc_ldp`
  - `GATEWAY_ADAPTER_URL`: `http://adapter:8000` (the mock adapter)
  - `GATEWAY_AUTH_TOKEN`: equal to `mosip.certify.gateway.auth-token` above; test-only
  - `GATEWAY_DATABASE_URL`: Certify's Postgres, where the Gateway creates its `gateway` schema
- Test fixtures, in `smoke.json`: `credentialConfig` (`developer-passport`, the only configuration Certify must list), `scope`, `eligible` (`hack-2026-0001`, issued and verified, then tampered), `refused` (each persona with the check that fails: `hack-2026-0003`, `on_roster`), `tamper` (the claim paths changed in the tampered copies: `teamName`)
