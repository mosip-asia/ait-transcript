# Hackathon installation

The files the stack mounts when `INSTALLATION=hackathon` (in `vc-stack/.env` or the environment): `INSTALLATION=hackathon ./run-demo.sh`. Everything else in `vc-stack/` is the same for every installation. Certify's seed runs only on a fresh database, so switching a local stack from another installation needs `--wipe` (`INSTALLATION=hackathon ./run-demo.sh --wipe`), which also renews the signing key and `did:key`.

How the infra team deploys this directory (the service set, every variable and mounted file, the secrets a deployment replaces, and the ingress allowlist, which is the same for both installations) is the configuration contract, [`wiki/project/issuer-v0.1/configuration-contract.md`](../../wiki/project/issuer-v0.1/configuration-contract.md); this file lists the values. The committed Gateway token, the realm's users and their passwords, and the `smoke` client are test-only fixtures that a deployment replaces.

| File | Read by | Notes |
|---|---|---|
| `certify-installation.properties` | Certify (`installation` profile) | Certify's settings: the Authorization Server keys (read from `authorization-server.env`), the Gateway data-provider plugin's six keys (below), the issuer display; `bootstrap.sh` rewrites `did-url` after a wipe |
| `authorization-server.env` | Certify and the Portal (`demo-app`), through Compose's `env_file`; `bootstrap.sh`, `smoke.sh` | The Authorization Server this installation trusts: issuer, JWKS URL, token endpoint, browser URL and wallet client id, each `${KEY:-<stand-in realm `hackathon`'s value>}`. An environment points the installation at another server by setting the same variable in `vc-stack/.env` (the VM's `app.env`), with no file changed. Certify's properties, Mimoto's issuer template and the Portal's sign-out link read these settings; the configuration contract's Authorization Server section lists them |
| `certify_seed.sql` | Postgres, first start only | The `credential_config` rows for `developer-passport` and `achievement-certificate`, mounted after `vc-stack/certify_init.sql` |
| `keycloak-realm.json` | Keycloak (`--import-realm`) | Realm `hackathon`: one user per roster `id`, the `wallet-demo` client, the test-only `smoke` client, the `developer_passport_vc_ldp` and `achievement_certificate_vc_ldp` scopes with Certify's audience. `bootstrap.sh` syncs the `wallet-demo` certificate into it |
| `gateway.env` | The Gateway (`gateway/`), through Compose's `env_file` | Its settings, listed below |
| `mimoto-issuers-config.json.template` | `data/render_mimoto_issuers_config.py` | Mimoto's issuer list (wallet test harness), with `${INJI_WEB_URL}` left to fill |
| `mimoto-issuers-config.json` | Mimoto, Inji Web | Rendered by `run-demo.sh` from the template, then patched by `bootstrap.sh`. Git-ignored |
| `adapter/student_identity_data.csv` | The mock adapter (`adapter/`, mounted read-only at `/data`) | The roster, committed and edited by hand: one row per participant, keyed by `id` (the Keycloak username). The adapter reads it on every request, no restart of anything |
| `smoke.json` | `vc-stack/smoke.sh`, `vc-stack/issuer-smoke.sh`, `gateway/tests/test_issuances.py`, `vc-stack/test_inji_web_vc_readiness.py` | The installation's test fixtures, below |

The installation's own values:

- Authorization Server: the stand-in Keycloak realm `hackathon` (`http://keycloak:8080/realms/hackathon`) unless the environment sets `AUTH_SERVER_*` in `vc-stack/.env`; see `authorization-server.env`
- Keycloak realm: `hackathon`, with wallet client `wallet-demo`; every user's password is `inji` (test-only)
- Test-only client `smoke`: public, direct-access grant, the two scopes and a hardcoded `client_id` claim; only `vc-stack/issue_and_verify.py` (run by `smoke.sh`) uses it
- Scopes: `developer_passport_vc_ldp`, `achievement_certificate_vc_ldp`
- Credential configuration: `developer-passport`, type `DeveloperPassportCredential`, VCDM 2.0, context `vc-lab/contexts/developer-passport/v1.json` on the VDR (`http://host.docker.internal:9098/contexts/developer-passport/v1.json`); claims `teamId`, `teamName`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`, each the roster column of that name
- Credential configuration: `achievement-certificate`, type `AchievementCertificateCredential`, VCDM 2.0, context `vc-lab/contexts/achievement/v1.json` on the VDR (`http://host.docker.internal:9098/contexts/achievement/v1.json`); claims `teamId` and `award`, each the roster column of that name
- Gateway checks: the Developer Passport has `on_roster`, passed when the roster row's `teamId` is not empty; the Achievement has `on_roster`, then `winner`, passed when the row's `winner` is `true`; every check is always evaluated. A participant who is not on the roster at all gets `no_record`
- Issuer display: "AIT Hackathon"; Mimoto issuer id `AITHackathon`; credential displays "AIT Developer Passport" and "AIT Achievement Certificate" (colours and labels from `ait-vc`'s rows); the issuer template lists no credential types, Certify's metadata does
- Roster columns: `id`, `teamId`, `teamName`, `winner`, `award`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`. The personas:
  - `hack-2026-0001`: team `team-01` "Sandbox Pioneers", the winning team: gets both credentials
  - `hack-2026-0002`: team `team-02` "Chain Gang", not a winner: gets the Developer Passport, refused the Achievement (`winner` fails, `on_roster` passes)
  - `hack-2026-0003`: registered, no team (empty `teamId`): refused both, `on_roster` fails (and `winner`, as the row is no winner)
- Certify data-provider plugin, in `certify-installation.properties` (contracts.md section 2a; these six keys and nothing else; edit the file and restart Certify, `docker compose restart certify`):
  - `mosip.certify.integration.data-provider-plugin`: `GatewayDataProviderPlugin`
  - `mosip.certify.integration.scan-base-package`: `asia.mosip.issuer.gateway.plugin`
  - `mosip.certify.gateway.url`: `http://gateway:8000`
  - `mosip.certify.gateway.auth-token`: the shared bearer token; must equal `GATEWAY_AUTH_TOKEN` below (the committed value, `dev-only-hackathon-gateway-token`, is test-only)
  - `mosip.certify.gateway.connect-timeout-ms`: `2000`
  - `mosip.certify.gateway.read-timeout-ms`: `15000`
- Gateway settings, in `gateway.env` (edit the file and recreate the container, `docker compose up -d gateway`):
  - `GATEWAY_ENABLED_SCOPES`: `developer_passport_vc_ldp achievement_certificate_vc_ldp` (space-separated)
  - `GATEWAY_ADAPTER_URL`: `http://adapter:8000` (the mock Adapter) unless the environment sets `GATEWAY_ADAPTER_URL` in `vc-stack/.env`
  - `GATEWAY_AUTH_TOKEN`: equal to `mosip.certify.gateway.auth-token` above; test-only
  - `GATEWAY_DATABASE_URL`: Certify's Postgres, where the Gateway creates its `gateway` schema
- Test fixtures, in `smoke.json`, a list with one entry per credential type (Certify must list exactly these configurations): `credentialConfig`, `scope`, `eligible` (one persona or a list, each issued and verified, then tampered: `hack-2026-0001` and the non-winning `hack-2026-0002` for the Developer Passport, `hack-2026-0001` for the Achievement), `unknown` (`hack-2026-9999` for both types, a persona the adapter has no record of: the Gateway's 404 `no_record`), `refused` (each persona with the check that fails, or the list of checks that fail together), `tamper` (the claim paths changed in the tampered copies: `teamName` for the Developer Passport, `award` for the Achievement). The Developer Passport refuses `hack-2026-0003` (`on_roster`); the Achievement refuses `hack-2026-0002` (`winner`) and `hack-2026-0003` (`on_roster` and `winner`)
