# Issuer v0.1 — configuration contract to infra

Status: draft of 2026-10-21, for the handover due 2026-11-20. Terms follow [`CONTEXT.md`](../../../CONTEXT.md). This is the deployment configuration of [`contracts.md`](contracts.md) section 6, written to the list in [`spec-hackathon-chain.md`](spec-hackathon-chain.md) → Configuration contract to infra. It describes both installations; their values are the directories [`installations/ait/`](../../../installations/ait/README.md) and [`installations/hackathon/`](../../../installations/hackathon/README.md), and everything else it names lives in `vc-stack/`. Any later change to this page or to either directory goes to the infra team before it is applied.

Not yet handed to the infra team (record the date here when it happens, YYYY-MM-DD), with both `installations/<name>/` directories.

The `Deploy` workflow (`.github/workflows/deploy.yml`) ships the demo to the team's own GCE VM with `run-demo.sh`; it is not the infra deployment and this page does not describe it.

## The two asks

Both travel with this page. Each is a request to the infra team, made with the handover by 2026-11-20 and needed in place for both installations by 2026-12-18, the hackathon chain deadline.

1. **Stable public hostnames.** Thas asks for stable public hostnames for every URL in [URLs in credentials or fetched by verifiers](#urls-in-credentials-or-fetched-by-verifiers), per installation, from the first real issuance: Certify's public base URL, which is the public gateway's hostname (it becomes the credential issuer and the host of every status-list URL and of the JSON-LD contexts, which the gateway serves from the `vdr` container), and the Authorization Server's issuer. A credential carries these URLs for life, so Dev and UAT credentials are throwaway because their URLs encode the environment.
2. **Signing-key custody.** Thas asks the infra team to hold the signing key of each Certify instance. Certify supports a PKCS12 keystore (today's local form: Certify creates `local.p12` in its keystore mount on first start) or PKCS#11 (an HSM); the keystore type, path and password are `mosip.kernel.keymanager.hsm.*` in `vc-stack/config/certify-default.properties`.

## Service set and images

The service set is identical for both installations: one Compose file, `vc-stack/docker-compose.yaml`, with `INSTALLATION` naming the directory every per-installation file comes from. Certify is listed once per instance; this chain runs one instance per installation. A second instance (another token issuer or data-provider plugin) is a second `certify` and `certify-nginx` pair with its own properties file.

| Compose service | Component | Image | Deployed |
|---|---|---|---|
| `database` | Postgres: Certify's, Verify's and Mimoto's databases, and the Gateway's `gateway` schema in Certify's | `postgres:15` | yes |
| `certify` | Inji Certify, with the Gateway data-provider plugin | `injistack/inji-certify-with-plugins:0.14.0` | yes |
| `certify-nginx` | Certify's nginx | `nginx:stable` | yes |
| `keycloak-server` | Keycloak, the Authorization Server's stand-in | `quay.io/keycloak/keycloak:24.0` | yes |
| `keycloak` | Keycloak's nginx | `nginx:stable` | yes |
| `gateway` | The Gateway (checklist runner) | built from `gateway/Dockerfile` | yes |
| `adapter` | The mock data adapter | built from `adapter/Dockerfile` | yes |
| `vdr` | The static mock VDR (JSON-LD contexts) | `nginx:stable` | yes |
| `verify-service` | Verifier service (Inji Verify) | `injistack/inji-verify-service:0.17.0` | yes |
| `verify-ui` | Verify UI (Inji Verify) | `injistack/inji-verify-ui:0.17.0` | yes |
| `demo-app` | The Portal (still named `demo-app` in Compose) | built from `portal/Dockerfile` | yes |
| `public-gateway` | Public gateway (nginx) | `nginx:stable` | yes |
| `mimoto-service` | Mimoto | `injistack/mimoto:0.21.0` | no: local test harness |
| `inji-web` | Inji Web | `injistack/inji-web:0.16.0` | no: local test harness |

Stock images are pinned by tag as committed; `nginx:stable` and `postgres:15` are moving tags, which infra may pin by digest.

Where the images come from: CI publishes no image. The `Plugin` workflow publishes only the plugin jar, as a workflow artifact (below); the `Test` workflow never publishes. The three images Thas builds (Gateway, mock adapter, Portal) are built by `run-demo.sh` (`docker compose build demo-app adapter gateway`) from the Dockerfiles of the commit being run, with the repository root as build context. No registry exists yet (owner's decision), so infra builds them from the tagged commit the same way. The spec named two built images (Gateway, Portal) and a CI publication; the adapter is a third, and nothing is published.

## Plugin jar

- **One generic artifact**, `gateway-data-provider-plugin.jar`, built from `gateway/plugin/` against `io.inji.certify:certify-integration-api:0.14.0` (Java 21, every dependency `provided`, so the jar carries one class). The same jar serves every installation; the six keys of `contracts.md` section 2a in the installation's Certify properties configure it.
- **How infra receives it** (proposed default): the `Plugin` workflow's artifact of the tagged commit. The workflow runs on every push to a branch other than `main`, on pull requests and by hand; for a tag, run it by hand on the tag (Actions → Plugin → Run workflow). The artifact is named `gateway-data-provider-plugin-<commit sha>` and holds the jar; it expires with the repository's artifact retention, so infra keeps its own copy. The same jar can be built from the commit: `docker run --rm -v "$PWD/gateway/plugin:/src" -w /src maven:3.9-eclipse-temurin-21 mvn -q package` writes `gateway/plugin/target/gateway-data-provider-plugin.jar`.
- **Mount**: a single file, read-only, at `/home/inji/additional_jars/gateway-data-provider-plugin.jar`, never the directory, which would hide the four jars bundled in the image. Compose refuses to start Certify when the file is missing. A changed jar needs Certify recreated and its nginx restarted. (The spec wrote `/home/mosip/additional_jars/`; the image's path is `/home/inji/`.)

## Per service: environment, files and ports

Every environment variable, env file, mounted file and host port of the Compose file, per service. Scope: `installation` comes from `installations/<name>/` (the values are in [Per-installation settings](#per-installation-settings)); `shared` is the same for every installation (a file in `vc-stack/` or the repository, or a literal in Compose); `environment` comes from a Compose variable in `vc-stack/.env` and differs per deployed host ([Compose variables](#compose-variables)). A mount's Source is its repository path, `<name>` standing for the installation. These tables are checked against the Compose file ([How this page is checked](#how-this-page-is-checked)).

### Compose variables

Compose substitutes these from `vc-stack/.env` (written by `bootstrap.sh` with the local defaults, copied from the VM's `app.env` by the `Deploy` workflow), in the Compose file and in the installation's `authorization-server.env`.

| Variable | Used by | Local default | A deployment sets |
|---|---|---|---|
| `INSTALLATION` | every per-installation mount and env file; `demo-app` | none, required | `ait` or `hackathon` |
| `CERTIFY_PUBLIC_BASE_URL` | `certify` (domain URL, allowed audience), `demo-app` | `http://certify-nginx` | Certify's public base URL: the public gateway's hostname (ask 1, [URLs](#urls-in-credentials-or-fetched-by-verifiers)) |
| `AUTH_SERVER_ISSUER` | `certify`, `demo-app`, through `authorization-server.env` | the stand-in realm's ([Authorization Server](#authorization-server)) | the environment's Authorization Server, when it is not the stand-in (ask 1) |
| `AUTH_SERVER_JWKS_URL` | `certify`, `demo-app`, through `authorization-server.env` | the stand-in realm's ([Authorization Server](#authorization-server)) | the environment's Authorization Server, when it is not the stand-in |
| `AUTH_SERVER_TOKEN_ENDPOINT` | `certify`, `demo-app`, through `authorization-server.env` | the stand-in realm's ([Authorization Server](#authorization-server)) | the environment's Authorization Server, when it is not the stand-in |
| `AUTH_SERVER_PUBLIC_URL` | `certify`, `demo-app`, through `authorization-server.env` | the stand-in realm's ([Authorization Server](#authorization-server)) | the environment's Authorization Server, when it is not the stand-in |
| `AUTH_SERVER_WALLET_CLIENT_ID` | `certify`, `demo-app`, through `authorization-server.env` | the stand-in realm's ([Authorization Server](#authorization-server)) | the environment's Authorization Server, when it is not the stand-in |
| `KEYCLOAK_DOCKER_AUTH_SERVER` | `keycloak-server` (`--hostname-url`); the stand-in values of `AUTH_SERVER_ISSUER` and `AUTH_SERVER_TOKEN_ENDPOINT` | `http://keycloak:8080` | the stand-in's issuer base; its tokens carry `iss=<this>/realms/<realm>` |
| `KEYCLOAK_INTERNAL_BASE_URL` | the stand-in value of `AUTH_SERVER_JWKS_URL` | `http://host.docker.internal:9080` | a URL from which Certify fetches the stand-in realm's keys |
| `KEYCLOAK_PUBLIC_BASE_URL` | `keycloak-server` (`--hostname-admin-url`), `keycloak`, `mimoto-service`; the stand-in value of `AUTH_SERVER_PUBLIC_URL` | `http://localhost:9080` | the stand-in Keycloak's browser-facing URL |
| `INJI_WEB_URL` | `mimoto-service`, `inji-web`, `demo-app` | `http://localhost:4004` | test harness only |
| `INJI_VERIFY_URL` | `demo-app` | `http://localhost:4007` | the Verify UI's public URL |
| `INJI_VERIFY_PUBLIC_BASE_URL` | `verify-service` | `http://localhost:9095` | the verifier service's URL |
| `INJI_VERIFY_DID_URI` | `verify-service`, `verify-ui` | `did:web:localhost%3A9095:v1:verify` | the verifier's DID |
| `INJI_VERIFY_DID_PUBLIC_KEY_URI` | `verify-service` | `did:web:localhost%3A9095:v1:verify#key-0` | the verifier's key id |
| `INJI_VERIFY_REDIRECT_URI` | `verify-service` | `http://localhost:4007` | the Verify UI's public URL |

`bootstrap.sh` also reads `vc-stack/.env` for values Compose does not use: `PUBLIC_BASE_URL`, `STUDENT_CONTEXT_URL` (the AIT context URL, below) and the harness's `MIMOTO_PUBLIC_BASE_URL` and `OIDC_P12_PASSWORD`.

### `database`

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `POSTGRES_USER` | | shared | `postgres`, the superuser every service uses today |
| env | `POSTGRES_PASSWORD` | | shared | Secret, committed test-only ([Secrets](#secrets)) |
| mount | `/docker-entrypoint-initdb.d/certify_init.sql` | `vc-stack/certify_init.sql` | shared | Certify's schema; runs on an empty data directory only |
| mount | `/docker-entrypoint-initdb.d/mimoto_init.sql` | `vc-stack/mimoto_init.sql` | shared | Mimoto's database (test harness) |
| mount | `/docker-entrypoint-initdb.d/verify_init.sql` | `vc-stack/verify_init.sql` | shared | Verify's database |
| mount | `/docker-entrypoint-initdb.d/certify_seed.sql` | `installations/<name>/certify_seed.sql` | installation | The `credential_config` rows (templates, contexts, scopes); runs after `certify_init.sql`, on an empty data directory only |
| port | `6440:5432` | | shared | Internal |

Compose mounts no data volume, so Postgres keeps its data in the image's anonymous volume; a deployment gives it persistent storage.

### `certify`

Runs as `root` with `host.docker.internal` mapped to the host (the local context URLs use that name).

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `container_user` | | shared | `mosip` |
| env | `active_profile_env` | | shared | `default, csvdp-student`: loads `certify-default.properties` and the installation's `certify-csvdp-student.properties` |
| env | `SPRING_CONFIG_NAME` | | shared | `certify` |
| env | `SPRING_CONFIG_LOCATION` | | shared | `/home/mosip/config/` |
| env | `enable_certify_artifactory` | | shared | `false`: configuration from the mounts, nothing downloaded |
| env | `download_hsm_client` | | shared | `false`; a PKCS#11 deployment changes it (ask 2) |
| env | `mosip_certify_domain_url` | | environment | From `CERTIFY_PUBLIC_BASE_URL`: the credential issuer and the host of every status-list URL |
| env_file | `installations/<name>/authorization-server.env` | | installation | The Authorization Server's five settings ([Authorization Server](#authorization-server)), each overridable in `vc-stack/.env` |
| env | `AUTH_SERVER_ISSUER` | | installation | The properties' authorization URL and issuer URI |
| env | `AUTH_SERVER_JWKS_URL` | | installation | The properties' JWK set URI |
| env | `AUTH_SERVER_TOKEN_ENDPOINT` | | installation | Not read by Certify |
| env | `AUTH_SERVER_PUBLIC_URL` | | installation | Not read by Certify |
| env | `AUTH_SERVER_WALLET_CLIENT_ID` | | installation | The first of the properties' allowed audiences |
| mount | `/home/mosip/config/certify-default.properties` | `vc-stack/config/certify-default.properties` | shared | Base settings: database, keystore (type, path, password), cache, status list |
| mount | `/home/mosip/config/certify-csvdp-student.properties` | `installations/<name>/certify-csvdp-student.properties` | installation | The per-instance properties: the Authorization Server keys read from the settings (authorization URL, issuer URI, JWK set URI, and the allowed audiences: the wallet client, the in-network credential endpoints and `<CERTIFY_PUBLIC_BASE_URL>/v1/certify/issuance/credential`), the plugin's six keys including the Gateway token, the issuer display, `did-url`, the indexed mappings. `bootstrap.sh` rewrites its `did-url` line after a fresh keystore |
| mount | `/home/inji/CERTIFY_PKCS12` | `vc-stack/data/CERTIFY_PKCS12` | shared | The keystore directory; Certify creates `local.p12`, the signing key, on first start (git-ignored; ask 2) |
| mount | `/home/mosip/config/vp_request_config.json` | `vc-stack/config/vp_request_config.json` | shared | Stock Certify file |
| mount | `/home/inji/additional_jars/gateway-data-provider-plugin.jar` | `vc-stack/plugins/gateway-data-provider-plugin.jar` | shared | The plugin jar, a single read-only file ([Plugin jar](#plugin-jar)) |
| port | `9090:8090` | | shared | Internal: Certify directly, every API |

### `certify-nginx`

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| mount | `/etc/nginx/conf.d/default.conf` | `vc-stack/certify-nginx.conf` | shared | Routes `/v1/certify/`, `/.well-known/did.json` and `/.well-known/openid-credential-issuer` to Certify. Its access log records `Authorization` headers (format `authdebug`), which a deployment drops |
| mount | `/config/server` | `vc-stack/config` | shared | Served at `/` with a directory index: the shared configuration, including `certify-default.properties` with the keystore and database passwords. Never public |
| mount | `/config/installation/mimoto-issuers-config.json` | `installations/<name>/mimoto-issuers-config.json` | installation | Test harness: Mimoto's issuer list at `/mimoto-issuers-config.json` |
| port | `9091:80` | | shared | Internal: the public gateway carries Certify's public paths ([Ingress allowlist](#ingress-allowlist)) |

### `keycloak-server`

Command, as in Compose: `start-dev --import-realm --hostname-strict=true --hostname-url=<KEYCLOAK_DOCKER_AUTH_SERVER> --hostname-port=9080 --hostname-admin-url=<KEYCLOAK_PUBLIC_BASE_URL> --proxy=edge --proxy-headers=xforwarded`. The issuer comes from `--hostname-url`, the admin console's URL from `--hostname-admin-url`; Keycloak runs behind its nginx (`--proxy=edge`, trusting its `X-Forwarded-*` headers). `start-dev` is Keycloak's development mode; Keycloak stands in for the campus Authorization Server, and how it runs in production is infra's.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `KEYCLOAK_ADMIN` | | shared | Secret, committed test-only |
| env | `KEYCLOAK_ADMIN_PASSWORD` | | shared | Secret, committed test-only |
| mount | `/opt/keycloak/data/import/realm.json` | `installations/<name>/keycloak-realm.json` | installation | Imported on start; a changed realm needs the container recreated. The committed realm is a fixture ([Test-only items](#test-only-items-and-what-a-deployment-replaces)) |

### `keycloak`

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `KEYCLOAK_PUBLIC_BASE_URL` | | environment | Substituted into the template by nginx's entrypoint |
| mount | `/etc/nginx/templates/default.conf.template` | `vc-stack/keycloak-nginx.conf.template` | shared | Proxies Keycloak and rewrites its browser URLs to the public one |
| port | `9080:8080` | | shared | Public: the Authorization Server |

### `gateway`

No host port; reached as `http://gateway:8000`. Restarts until Postgres accepts connections, then creates its `gateway` schema in Certify's database.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env_file | `installations/<name>/gateway.env` | | installation | The Gateway's four settings below |
| env | `GATEWAY_ENABLED_SCOPES` | | installation | Space-separated scopes the Gateway serves |
| env | `GATEWAY_ADAPTER_URL` | | installation | `http://adapter:8000`, the mock adapter; the real adapter's URL later (`contracts.md` section 2b) |
| env | `GATEWAY_AUTH_TOKEN` | | installation | Secret: equals the plugin's `mosip.certify.gateway.auth-token` |
| env | `GATEWAY_DATABASE_URL` | | installation | Secret: Certify's Postgres, database `inji_certify` |

### `adapter`

No host port; reached as `http://adapter:8000`.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `ADAPTER_CSV` | | shared | `/data/student_identity_data.csv` |
| mount | `/data` | `installations/<name>/adapter` | installation | Read-only; the CSV is read on every request, so an edit needs no restart |

### `vdr`

No host port; reached through `public-gateway`'s `/contexts/`.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| mount | `/usr/share/nginx/html/contexts` | `vc-lab/contexts` | shared | Read-only; every installation's JSON-LD contexts, served under `/contexts/` |

### `verify-service`

Runs as `root` with `host.docker.internal` mapped to the host (it fetches the local context URLs).

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `active_profile_env` | | shared | `default` |
| env | `DATABASE_HOST` | | shared | `database` |
| env | `DATABASE_PORT` | | shared | `5432` |
| env | `DATABASE_NAME` | | shared | `inji_verify` |
| env | `DATABASE_SCHEMA` | | shared | `verify` |
| env | `DATABASE_USERNAME` | | shared | `postgres` |
| env | `DATABASE_PASSWORD` | | shared | Secret, committed test-only |
| env | `INJI_VP_REQUEST_LONG_POLLING_TIMEOUT` | | shared | `55000` |
| env | `INJI_VP_SUBMISSION_BASE_URL` | | environment | `<INJI_VERIFY_PUBLIC_BASE_URL>/v1/verify` |
| env | `INJI_DID_VERIFY_URI` | | environment | From `INJI_VERIFY_DID_URI` |
| env | `INJI_DID_VERIFY_PUBLIC_KEY_URI` | | environment | From `INJI_VERIFY_DID_PUBLIC_KEY_URI` |
| env | `INJI_KEYSTORE_FILE_PASS` | | shared | Secret, committed test-only |
| env | `INJI_VERIFY_REDIRECT_URI` | | environment | The Verify UI's URL |
| env | `INJI_VERIFY_CLAIMS_WITH_META_DATA` | | shared | Stock list |
| port | `9095:8080` | | shared | Internal |

### `verify-ui`

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `DEFAULT_TITLE` | | shared | `Inji Verify` |
| env | `DEFAULT_LANG` | | shared | `en` |
| env | `INTERNET_CONNECTIVITY_CHECK_ENDPOINT` | | shared | `https://dns.google/` |
| env | `INTERNET_CONNECTIVITY_CHECK_TIMEOUT` | | shared | `10000` |
| env | `OVP_QR_HEADER` | | shared | `INJI_OVP://payload=` |
| env | `VERIFIABLE_CLAIMS_CONFIG_URL` | | shared | `/assets/config.json`, the mount below |
| env | `VP_SUBMISSION_SUPPORTED` | | shared | `false` |
| env | `CLIENT_ID` | | shared | `inji-verify-ui` |
| env | `CLIENT_ID_DID` | | environment | From `INJI_VERIFY_DID_URI` |
| env | `DISPLAY_TIMEOUT` | | shared | `120000` |
| env | `VERIFY_SERVICE_API_URL` | | shared | `/v1/verify`, which the UI's nginx proxies to `verify-service` |
| mount | `/usr/share/nginx/html/assets/config.json` | `vc-stack/config/verify-config.json` | shared | The claim types the UI offers to request; lists the transcript, no hackathon type |
| port | `4007:8000` | | shared | Public: the Verify UI |

### `public-gateway`

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| mount | `/etc/nginx/conf.d/default.conf` | `vc-stack/public-gateway-nginx.conf` | shared | Routes `/contexts/` to `vdr`, and `/v1/certify/`, `/.well-known/`, `/realms/`, `/v1/verify/`, `/v1/mimoto/` to the other services |
| mount | `/etc/nginx/mobile/public-gateway-mobile.conf` | `vc-stack/config/public-gateway-mobile.conf` | shared | Phone-only locations for the Inji mobile wallet, rendered for an installation that carries the template (`ait`); test harness |
| mount | `/etc/nginx/mobile/mimoto-issuers-mobile.json` | `vc-stack/config/mimoto-issuers-mobile.json` | shared | The phone's issuer list, rendered with the file above; test harness |
| port | `9098:80` | | shared | Public: Certify's public base URL and the JSON-LD contexts, for the paths of the [Ingress allowlist](#ingress-allowlist) only |

### `demo-app`

The Portal. Its image already contains `portal/` and `data/`; the source mounts and uvicorn's `--reload` are for local development, and the `vc-stack/config` and `installations` mounts let `run-demo.sh` render the issuer lists in this container. A deployment needs only `.demo-state` persistent.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `AIT_DEMO_DB` | | shared | `/demo/.demo-state/demo_requests.db`, the request database (SQLite) |
| env | `INJI_WEB_URL` | | environment | Student deep links (test harness) |
| env | `INJI_VERIFY_URL` | | environment | Links to the Verify UI |
| env | `CERTIFY_PUBLIC_BASE_URL` | | environment | Read only by the issuer-list render |
| env | `INSTALLATION` | | installation | Which directory the render writes into |
| env_file | `installations/<name>/authorization-server.env` | | installation | The Authorization Server's five settings ([Authorization Server](#authorization-server)), each overridable in `vc-stack/.env` |
| env | `AUTH_SERVER_ISSUER` | | installation | The issuer-list render (phone metadata) |
| env | `AUTH_SERVER_JWKS_URL` | | installation | Not read |
| env | `AUTH_SERVER_TOKEN_ENDPOINT` | | installation | The issuer-list render, and the smoke's token request (`vc-stack/issue_and_verify.py` runs in this image) |
| env | `AUTH_SERVER_PUBLIC_URL` | | installation | The sign-out link, and the issuer-list render (phone metadata) |
| env | `AUTH_SERVER_WALLET_CLIENT_ID` | | installation | The sign-out link, and the issuer-list render |
| mount | `/demo/portal` | `portal` | shared | Development only |
| mount | `/demo/data` | `data` | shared | Development only |
| mount | `/demo/.demo-state` | `.demo-state` | shared | The request database; persistent |
| mount | `/demo/vc-stack/config` | `vc-stack/config` | shared | Render output (phone-only files) |
| mount | `/demo/installations` | `installations` | shared | Render output (`mimoto-issuers-config.json`) |
| port | `4100:4100` | | shared | Public: the Portal |

### `mimoto-service`

Test harness, not deployed.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `container_user` | | shared | `mosip` |
| env | `active_profile_env` | | shared | `default` |
| env | `SPRING_CONFIG_NAME` | | shared | `mimoto` |
| env | `SPRING_CONFIG_LOCATION` | | shared | `/home/mosip/` |
| env | `SPRING_CLOUD_BOOTSTRAP_LOCATION` | | shared | The bootstrap properties mount |
| env | `oidc_p12_password` | | shared | The OIDC keystore's password (harness) |
| env | `WALLET_BINDING_PARTNER_API_KEY` | | shared | Dummy value |
| env | `SPRING_DATASOURCE_URL` | | shared | `jdbc:postgresql://database:5432/inji_mimoto` |
| env | `POSTGRES_USER` | | shared | `postgres` |
| env | `POSTGRES_PASSWORD` | | shared | The superuser's password |
| env | `GOOGLE_OAUTH_CLIENT_ID` | | shared | Dummy value |
| env | `GOOGLE_OAUTH_CLIENT_SECRET` | | shared | Dummy value |
| env | `SPRING_CLOUD_LOADBALANCER_ENABLED` | | shared | `false` |
| env | `SPRING_CLOUD_DISCOVERY_ENABLED` | | shared | `false` |
| env | `KEYCLOAK_EXTERNAL_URL` | | environment | From `KEYCLOAK_PUBLIC_BASE_URL` |
| env | `MOSIP_INJI_WEB_URL` | | environment | From `INJI_WEB_URL` |
| env | `MOSIP_SECURITY_ORIGINS` | | environment | From `INJI_WEB_URL` |
| mount | `/home/mosip/mimoto-default.properties` | `vc-stack/config/mimoto-default.properties` | shared | |
| mount | `/home/mosip/mimoto-bootstrap.properties` | `vc-stack/config/mimoto-bootstrap.properties` | shared | |
| mount | `/home/mosip/mimoto-issuers-config.json` | `installations/<name>/mimoto-issuers-config.json` | installation | Rendered from the installation's template (git-ignored) |
| mount | `/home/mosip/mimoto-trusted-verifiers.json` | `vc-stack/config/mimoto-trusted-verifiers.json` | shared | |
| mount | `/home/mosip/certs/oidckeystore.p12` | `vc-stack/certs/oidckeystore.p12` | shared | Generated by `bootstrap.sh` (git-ignored) |
| port | `9099:8099` | | shared | Internal; not deployed |

### `inji-web`

Test harness, not deployed.

| Kind | Name | Source | Scope | Notes |
|---|---|---|---|---|
| env | `DEFAULT_LANG` | | shared | `en` |
| env | `MIMOTO_URL` | | environment | `<INJI_WEB_URL>/v1/mimoto` |
| mount | `/home/mosip/mimoto-default.properties` | `vc-stack/config/mimoto-default.properties` | shared | |
| mount | `/home/mosip/mimoto-issuers-config.json` | `installations/<name>/mimoto-issuers-config.json` | installation | |
| mount | `/home/mosip/mimoto-trusted-verifiers.json` | `vc-stack/config/mimoto-trusted-verifiers.json` | shared | |
| mount | `/home/mosip/credential-template.html` | `vc-stack/config/credential-template.html` | shared | PDF template |
| mount | `/home/mosip/AITUniversity-ait-transcript-template.html` | `vc-stack/config/AITUniversity-ait-transcript-template.html` | shared | The transcript's PDF template |
| mount | `/etc/nginx/conf.d/default.conf` | `vc-stack/nginx.conf` | shared | |
| port | `4004:3004` | | shared | Internal; not deployed |

## Per-installation settings

The values in `installations/<name>/`; each directory's `README.md` lists its files.

| Setting | `ait` | `hackathon` |
|---|---|---|
| Stand-in Keycloak realm, the default Authorization Server ([Authorization Server](#authorization-server)) | `inji` | `hackathon` |
| Scopes | `ait_transcript_vc_ldp` | `developer_passport_vc_ldp`, `achievement_certificate_vc_ldp` |
| Credential configurations and types | `ait-transcript` (`AitTranscriptCredential`) | `developer-passport` (`DeveloperPassportCredential`), `achievement-certificate` (`AchievementCertificateCredential`) |
| JSON-LD contexts (`vc-lab/contexts/`) | `transcript/v1.json` | `developer-passport/v1.json`, `achievement/v1.json` |
| Adapter CSV (`adapter/student_identity_data.csv`) | Generated from `data/students.json` (git-ignored), one row per degree | The committed roster, edited by hand, one row per participant |
| Enabled Gateway types (`GATEWAY_ENABLED_SCOPES`) | `ait_transcript_vc_ldp` | `developer_passport_vc_ldp achievement_certificate_vc_ldp` |
| Gateway checks | `no_holds`, `conferred`, `zero_balance` | Developer Passport `on_roster`; Achievement `on_roster`, `winner` |
| Gateway token (`GATEWAY_AUTH_TOKEN`, equal to the plugin's `mosip.certify.gateway.auth-token`), committed test-only value | `dev-only-ait-gateway-token` | `dev-only-hackathon-gateway-token` |
| Issuer display | "AIT University Registrar" | "AIT Hackathon" |
| Wallet client; test-only client | `wallet-demo`; `smoke` | `wallet-demo`; `smoke` |
| Mimoto issuer template (local only) | `mimoto-issuers-config.json.template` (issuer id `AITUniversity`) and `public-gateway-mobile.conf.template` | `mimoto-issuers-config.json.template` (issuer id `AITHackathon`) |
| Test fixtures | `smoke.json` | `smoke.json` |

## Authorization Server

What an installation trusts is five settings in `installations/<name>/authorization-server.env`, the only configuration files that name a realm path. Compose reads that file as an `env_file` of `certify` and `demo-app`; `bootstrap.sh` and `smoke.sh` read it back through `docker compose config`, so every reader sees the same values. Each line is `KEY=${KEY:-<stand-in value>}`: an environment that sets the variable in `vc-stack/.env` (on the VM, `app.env`) wins, and one that does not runs against the installation's stand-in Keycloak realm. Pointing an installation at another server, the campus realm for instance, is setting the five variables there; no file changes. The stand-in values follow the `KEYCLOAK_*` [Compose variables](#compose-variables).

| Setting | Read by | `ait`, local and CI | `hackathon`, local and CI | Another environment |
|---|---|---|---|---|
| `AUTH_SERVER_ISSUER` | Certify (`mosip.certify.authorization.url`, `mosip.certify.authn.issuer-uri`, so its metadata's `authorization_servers`); the phone metadata's rewrite | `http://keycloak:8080/realms/inji` | `http://keycloak:8080/realms/hackathon` | The server's issuer, exactly as its tokens carry `iss`, reachable from Mimoto in the network |
| `AUTH_SERVER_JWKS_URL` | Certify (`mosip.certify.authn.jwk-set-uri`) | `http://host.docker.internal:9080/realms/inji/protocol/openid-connect/certs` | `http://host.docker.internal:9080/realms/hackathon/protocol/openid-connect/certs` | The server's JWKS URL, reachable from Certify |
| `AUTH_SERVER_TOKEN_ENDPOINT` | Mimoto's issuer list (`authorization_audience`, `proxy_token_endpoint`), rendered by `data/render_mimoto_issuers_config.py` and patched by `bootstrap.sh`; the smoke's token request | `http://keycloak:8080/realms/inji/protocol/openid-connect/token` | `http://keycloak:8080/realms/hackathon/protocol/openid-connect/token` | The server's token endpoint, reachable in the network |
| `AUTH_SERVER_PUBLIC_URL` | The Portal's sign-out link; `bootstrap.sh` and `smoke.sh` (Mimoto's `authorization_endpoint` must start with it); the phone metadata | `http://localhost:9080/realms/inji` | `http://localhost:9080/realms/hackathon` | The issuer as a browser reaches it; for a server with one public name, the issuer itself |
| `AUTH_SERVER_WALLET_CLIENT_ID` | Mimoto's issuer list (`client_id`); Certify's first allowed audience; the Portal's sign-out link | `wallet-demo` | `wallet-demo` | The client the server registers for Mimoto (test harness) |

Dev runs the stand-in today: `app.env` sets no `AUTH_SERVER_*` variable, so its values are the stand-in's with the VM's `KEYCLOAK_PUBLIC_BASE_URL`. `smoke.sh` runs only against the stand-in, because its direct-access grant on the `smoke` client needs the realm's test users; it fails unless the stand-in realm is the configured issuer. The Keycloak containers keep running whichever server is configured.

## Secrets

Every committed value below is test-only; a deployment replaces each one.

| Secret | Where it is read | Committed value |
|---|---|---|
| The Gateway's shared bearer token | The Gateway, `GATEWAY_AUTH_TOKEN` in `gateway.env`; Certify's plugin, `mosip.certify.gateway.auth-token` in `certify-csvdp-student.properties`. Both must be equal; one per installation | `dev-only-<name>-gateway-token` |
| The Gateway's database URL | The Gateway, `GATEWAY_DATABASE_URL` in `gateway.env`, for its `gateway` schema in Certify's Postgres | The `postgres` superuser; a dedicated role limited to the `gateway` schema is recorded debt |
| Postgres superuser password | `database` (`POSTGRES_PASSWORD`), Certify (`spring.datasource.password` in `certify-default.properties`), `verify-service` (`DATABASE_PASSWORD`), the Gateway's URL, Mimoto | `postgres` |
| Certify's keystore password | Certify, `mosip.kernel.keymanager.hsm.keystore-pass` in `certify-default.properties`, for the keystore in `vc-stack/data/CERTIFY_PKCS12/` (ask 2) | `local` |
| Keycloak's admin credentials | `keycloak-server`, `KEYCLOAK_ADMIN` and `KEYCLOAK_ADMIN_PASSWORD` | `admin` / `admin` |
| The Portal's client secret | None in this chain: the Portal does not sign in through OpenID Connect (`portal/auth.py` is a persona picker). Its session-cookie key, `AIT_DEMO_SESSION_SECRET`, is read by `portal/auth.py` and not set by Compose, so the committed default applies; a deployment adds it to the Portal's environment | A default in `portal/auth.py` |
| Certify's Redis password | Certify, `spring.data.redis.password` in `certify-default.properties`, read only if the deployment scales Certify with Redis (`spring.cache.type=redis`, see the scaling note); the committed `spring.cache.type=simple` never connects, and Compose runs no Redis | `redis` |
| Verify's keystore password | `verify-service`, `INJI_KEYSTORE_FILE_PASS` | `mosip` |
| Realm users' passwords | `keycloak-realm.json` | `inji` for every user; fixtures, not deployed |

Test harness only, not deployed: Mimoto's `oidc_p12_password` (also `OIDC_P12_PASSWORD` in `.env`), `WALLET_BINDING_PARTNER_API_KEY` and `GOOGLE_OAUTH_CLIENT_SECRET`.

## URLs in credentials or fetched by verifiers

Each needs a stable public hostname from the first real issuance (ask 1). Dev and UAT credentials are throwaway because these URLs encode the environment.

| URL | Set by | Local value | Why it must be stable |
|---|---|---|---|
| JSON-LD context, one per credential type | The template's `@context` and the row's `context` column in `installations/<name>/certify_seed.sql` | `http://host.docker.internal:9098/contexts/<type>/v1.json`, through `public-gateway` to `vdr` | Embedded in every credential; fetched by every verifier |
| Status-list URL | Certify, from `mosip_certify_domain_url` (`CERTIFY_PUBLIC_BASE_URL`) | `http://certify-nginx/v1/certify/credentials/status-list/<id>` | Embedded in every credential (`credentialStatus.statusListCredential`); fetched by every verifier for revocation |
| Issuer identifier | `mosip.certify.data-provider-plugin.did-url` in the installation's properties and every `credential_config` row, refreshed by `bootstrap.sh` from the live keystore | `did:key:…` | Embedded; a `did:key` needs no host, the `did:web` that arrives with the mock VDR publisher task resolves on its host's `/.well-known/did.json` |
| Credential issuer (OpenID4VCI) | `mosip.certify.identifier`, Certify's domain URL | `http://certify-nginx` | Wallets fetch its metadata. It is not the access tokens' audience: Certify accepts a token whose `aud` holds one of `mosip.certify.authn.allowed-audiences` in the installation's properties, which are the wallet client (`AUTH_SERVER_WALLET_CLIENT_ID`, `wallet-demo` in both stand-in realms, whose client has its own audience mapper) and the credential endpoint `…/v1/certify/issuance/credential`, in the network or on `CERTIFY_PUBLIC_BASE_URL` (the `smoke` client's mapper and, in `hackathon`, both scopes' mappers add `http://certify-nginx/v1/certify/issuance/credential`) |
| The Authorization Server's issuer | `AUTH_SERVER_ISSUER` ([Authorization Server](#authorization-server)) | `http://keycloak:8080/realms/<realm>` | In every access token and Certify's metadata; Certify's issuer URI must equal it |

In a deployment every context URL is `<CERTIFY_PUBLIC_BASE_URL>/contexts/<type>/v1.json`, so Certify's public base URL is the public gateway's hostname: `public-gateway` is the only service that routes `/contexts/` (to `vdr`; `certify-nginx` has no such route), and it also forwards Certify's OpenID4VCI paths, so one host serves the credential issuer, the status lists and the contexts. What that host must block is in [Ingress allowlist](#ingress-allowlist). `bootstrap.sh` enforces the rule: its validation fails unless every `credential_config` row's `context` is `<base>/contexts/<type>/v<n>.json,https://www.w3.org/ns/credentials/v2` and the issuer metadata lists the same `@context`, the base being taken from `STUDENT_CONTEXT_URL` in `.env` when set, else from `CERTIFY_PUBLIC_BASE_URL` when it is `https`, else the local `http://host.docker.internal:9098`.

Each row carries its context URL twice, and both must name it identically: the `context` column (plain text) and the `@context` array inside the `vc_template` column, which is base64-encoded JSON. At bring-up `bootstrap.sh` moves the `ait-transcript` row to `<base>/contexts/transcript/v1.json` with `vc-stack/context_refresh.sql`, which rewrites both columns, then restarts Certify (and the harness's Mimoto). That script matches only the `ait-transcript` row and the `transcript` path, so the hackathon rows (`developer-passport`, `achievement-certificate`) keep `http://host.docker.internal:9098/contexts/<type>/v1.json`, and a hackathon bring-up with an `https` base fails the validation above. Until a script covers them, a hackathon deployment edits `installations/hackathon/certify_seed.sql` before the database's first start, in each of the two rows: the first URL of the `context` column, and the `vc_template` value, decoded from base64, its `@context` entry for the same URL replaced, and re-encoded as base64 on a single line (Certify's decoder rejects line breaks). On a database already seeded, the same two columns are updated in place, as `context_refresh.sql` does for the AIT row, and Certify is restarted. **Gap, for the owner to close before the hackathon deploy:** no committed step rewrites the hackathon rows; either `context_refresh.sql` is widened to every row and context, or the deployed seed is written with the public URLs.

Every credential's `id` also starts with `mosip.certify.data-provider-plugin.id-field-prefix-uri`, `https://ait.example/credential/` in both installations: embedded, never fetched.

## Ingress allowlist

Every host port of the Compose file. Public ports are public for the paths listed only; every other path on them is internal. Services without a host port (`keycloak-server`, `gateway`, `adapter`, `vdr`) are internal; `vdr` is reached through `public-gateway`. Certify's management, ledger-search, status and credential-configuration APIs are unauthenticated in stock Certify, so this list is part of what infra deploys.

| Host port | Service | Exposure | Public paths |
|---|---|---|---|
| `9080` | `keycloak` | public | The Authorization Server: `/realms/<realm>/` and `/resources/`. Internal: `/admin/` |
| `4100` | `demo-app` | public | The Portal |
| `4007` | `verify-ui` | public | The Verify UI |
| `9098` | `public-gateway` | public | Certify's public base URL (ask 1). Public: `/contexts/` (the `vdr` container; verifiers fetch it) and Certify's OpenID4VCI endpoints: `/.well-known/openid-credential-issuer`, `/.well-known/did.json`, `/v1/certify/.well-known/`, `/v1/certify/issuance/`, and `GET /v1/certify/credentials/status-list/` (verifiers fetch it). Every other path is blocked. Its `/v1/certify/` route forwards every Certify API to `certify` directly, so the ingress blocks `/v1/certify/ledger-search`, the status API `POST /v1/certify/credentials/status` (revoke), the credential-configuration API and the actuator; `/.well-known/` forwards to `certify-nginx`, so only the two documents above pass; `/v1/verify/` is `verify-service` (internal); `/v1/mimoto/` and, in `ait`, the phone-only locations are the test harness; `/realms/` duplicates `9080` and, if kept, is restricted as there |
| `9091` | `certify-nginx` | internal | None: wallets and verifiers reach Certify's public paths through `public-gateway` (`9098`). The Portal and the harness's Mimoto call it in the network, `bootstrap.sh` on the host. Never public: it also serves `/` (the configuration directory, passwords included) and `/mimoto-issuers-config.json` |
| `9090` | `certify` | internal | None: Certify directly |
| `9095` | `verify-service` | internal | None: the Verify UI reaches it in the network (VP submission from phones is off) |
| `6440` | `database` | internal | None: Postgres |
| `9099` | `mimoto-service` | internal | None: test harness, not deployed |
| `4004` | `inji-web` | internal | None: test harness, not deployed |

## Cache and scaling

One pod per Certify instance, because two things live in the pod. The cache: with `spring.cache.type=simple`, as committed in `certify-default.properties`, Certify keeps issuance state in the pod's memory, not shared between pods. The keystore: with PKCS12, Certify reads `local.p12` from its keystore mount (`/home/inji/CERTIFY_PKCS12`, from `vc-stack/data/CERTIFY_PKCS12`) and creates it when it is missing, so a pod with its own empty mount signs with a different key and `did:key`. If infra scales Certify, both move out of the pod: the cache to Redis (`spring.cache.type=redis` and the `spring.data.redis.*` keys of the same file, today placeholders; Compose runs no Redis), and the keystore to one file every pod of the instance mounts, or to an HSM through PKCS#11 (ask 2). The Gateway and the adapter keep no state in memory.

## Start order and readiness

1. Postgres first. Its init scripts and the installation's seed run on an empty data directory only, so a changed seed needs a fresh database. Certify and the Gateway need it; the Gateway restarts until it connects.
2. Keycloak (`keycloak-server`, then its nginx) before Certify validates tokens: Certify fetches the server's keys from `AUTH_SERVER_JWKS_URL`.
3. Certify, then `certify-nginx`; the adapter and the Gateway in any order (neither the Gateway nor the plugin calls anything at startup); `vdr` before `public-gateway`.
4. `certify-nginx`, `keycloak` and `public-gateway` name their upstreams through variables with `resolver 127.0.0.11 valid=10s`, so they re-resolve per request (cached ten seconds) and follow a recreated upstream without a restart. `127.0.0.11` is Docker's embedded DNS and exists only under Docker; elsewhere that line names the platform's resolver. What does not re-resolve is restarted by `bootstrap.sh`: `verify-ui`'s stock proxy to `verify-service`, and the harness's Mimoto (it loads Certify's metadata at start) and Inji Web (`vc-stack/nginx.conf` names `mimoto-service` directly). In Mode B, its default and the Keycloak mode this chain runs, it restarts `keycloak`, `certify-nginx`, `mimoto-service`, `inji-web`, `public-gateway` and `verify-ui` after every bring-up; Mode A (`--mode=a`, the eSignet mock) restarts only `mimoto-service`, `inji-web` and `verify-ui`. A deployment without `bootstrap.sh` restarts `verify-ui` after recreating `verify-service`.
5. After a fresh keystore (first start, or a wipe), `bootstrap.sh` reads the live `did:key` from `/.well-known/did.json`, writes it into every `credential_config` row and the properties' `did-url`, and restarts Certify. With a key held by infra (ask 2), `did-url` is set once.
6. Certify caches its credential configurations: a changed row needs Certify restarted (and Mimoto, in the harness). A changed jar needs Certify recreated; a changed realm, `keycloak-server` recreated; a changed `gateway.env`, the Gateway recreated; a changed Authorization Server setting, Certify and `demo-app` recreated and the issuer list rendered again (`run-demo.sh`); a changed adapter CSV, nothing.

## Test-only items and what a deployment replaces

- The `smoke` client in each realm is a test-only client: public, direct-access grant, used only by `vc-stack/issue_and_verify.py` through `smoke.sh`. Infra disables or removes it where it decides.
- The realm users are fixtures: one per adapter row, sequential usernames, every password `inji`. A deployment imports a realm built from its real roster or students, with per-user passwords or federated sign-in, or points the installation at another Authorization Server through its settings ([Authorization Server](#authorization-server)); eSignet is such a change.
- The `wallet-demo` client allows the redirect URI and web origin `*`; a deployment lists its wallets' own.
- Every committed secret ([Secrets](#secrets)), including the two Gateway tokens; the Gateway's superuser database access.
- Development modes: Keycloak's `start-dev`, the Portal's `--reload` and source mounts, `certify-nginx`'s `Authorization` logging and its index of the configuration directory.
- The mock adapter: the real data adapter (`contracts.md` section 2b) replaces it later by changing `GATEWAY_ADAPTER_URL`.

## How this page is checked

`vc-stack/test_configuration_contract.py` (host only, no Docker; CI's host-tests job runs it) compares this page with `vc-stack/docker-compose.yaml` in both directions: each check fails on an entry present on one side only.

- [Service set and images](#service-set-and-images): the service names equal Compose's, and each Image cell equals the service's `image`, or `built from <Dockerfile path>`.
- [Per service](#per-service-environment-files-and-ports): the rows (service, Kind, Name, Scope, and Source for a mount) equal Compose's: the name of every `environment` entry; every `env_file` path, and the variable names in it, read from every installation's `gateway.env` (which must all name the same variables); every volume's container target and its source as a repository path, `<name>` for the installation; and every `ports` entry as written. Scope is derived from the Compose value or source: `installation` when it contains `${INSTALLATION}`, `environment` for any other `${…}`, else `shared`.
- [Compose variables](#compose-variables): the Variable column equals the `${…}` names Compose interpolates, in the Compose file and in every installation's env files.
- [Ingress allowlist](#ingress-allowlist): the host ports equal Compose's published host ports, each with its service, and each Exposure is `public` or `internal`.

It does not check values (environment values, Compose defaults, "A deployment sets", the Notes column), command flags such as Keycloak's, mount options, the allowlist's paths or whether a port's exposure is right, any URL (the URL table, the context URLs, the nginx routes), the [Secrets](#secrets), the [Per-installation settings](#per-installation-settings), or the start order and scaling text. Last run 2026-10-28: pass. The secrets, URLs and per-installation settings were checked by hand against `installations/ait/`, `installations/hackathon/` and `vc-stack/config/` on 2026-10-21.
