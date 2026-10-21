# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A self-contained demo of one journey: an AIT student requests an academic transcript, a registrar approves it, the student claims it as a W3C Verifiable Credential (VCDM 2.0, JSON-LD, Ed25519Signature2020) into Inji Web, and a relying party verifies it in Inji Verify, including revocation. Everything runs in one Docker Compose stack (`vc-stack/`) built from pinned upstream Inji images plus one custom service, the FastAPI demo app (the Portal) in `portal/`. `PRD.md` is the authority on what the demo does and does not do; its §3 non-goals and §6.3 (approval is enforced in the demo app UI only, not at issuance) are deliberate.

The documents under `wiki/project/` (the issuer proposal of PR 4, and `issuer-v0.1/` with its responsibilities, contracts and deviations) and the glossary in `CONTEXT.md` describe the planned Issuer product, not the running demo. Do not treat them as a description of the code.

`wallet/` carries patches, not a wallet: `wallet/apply.sh <platform>` clones Inji Wallet v0.22.1 and applies the `common/` and per-platform changes that let it talk to the GCP deployment. The phone app gets its own issuer list and metadata through the `api.` gateway (`vc-stack/config/mimoto-issuers-mobile.json`, `public-gateway-mobile.conf`); see `wiki/architecture/inji-mobile-wallet.md` and `wallet/README.md`.

## Commands

Everything runs through Docker; the host needs only Docker Desktop (Compose v2), `jq`, `curl` and `awk`. On Windows, use WSL2 with the repo cloned into the WSL filesystem, not Git Bash and not `/mnt/c`.

`INSTALLATION` names the directory under `installations/` the stack runs (`ait` or `hackathon`). The scripts read it from the environment, else from `vc-stack/.env`, else from the git-ignored one-line marker `vc-stack/.installation` (written by `deploy/remote-deploy.sh` so a VM reboot keeps it), and stop before any container starts when it names no directory; `bootstrap.sh` writes the value it ran with into `.env`. Certify's seed runs only on a fresh database, so switching a local stack to another installation needs `--wipe`.

```sh
INSTALLATION=ait ./run-demo.sh     # full bring-up: build demo app, regenerate the adapter CSV from data/students.json, render the installation's mimoto-issuers-config.json, build the plugin jar into vc-stack/plugins/, then vc-stack/bootstrap.sh
./run-demo.sh --wipe               # same, after tearing down volumes and ephemeral files (new signing key and did:key)
INSTALLATION=hackathon ./run-demo.sh --wipe   # switch to the hackathon installation (the Developer Passport and the Achievement)
./vc-stack/bootstrap.sh --validate # only the end-to-end health checks
./vc-stack/bootstrap.sh --did-refresh  # only the post-wipe did:key refresh
```

After the first `run-demo.sh` (which creates `vc-stack/.env`, naming the installation, and the external network), the plain Compose form works: `docker compose -f vc-stack/docker-compose.yaml up -d --build`. Re-run `./run-demo.sh` whenever `data/students.json` changes, so the adapter CSV stays in sync; the plain Compose form needs the plugin jar `run-demo.sh` builds into `vc-stack/plugins/`.

Demo app development: `portal/` and `data/` are bind-mounted and uvicorn runs with `--reload`, so Python and template edits apply live. Rebuild only when `portal/requirements.txt` changes:

```sh
docker compose -f vc-stack/docker-compose.yaml build demo-app
docker compose -f vc-stack/docker-compose.yaml up -d demo-app
```

Tests are plain Python scripts, not pytest. Run one by name:

```sh
./vc-stack/smoke.sh                                   # stack smoke checks over curl/jq; stack must be up; also runs the readiness script and issue_and_verify.py. The same script for every installation: personas, scope and tampered claims of every credential type come from installations/<name>/smoke.json, a list with one entry per type
python3 vc-stack/test_issue_and_verify.py             # issue_and_verify.py's token request, proof JWT and verify outcomes, HTTP mocked; needs portal/requirements.txt, no Docker
python3 vc-stack/test_inji_web_vc_readiness.py        # config checks for the Inji Web download path, no Docker needed
python3 vc-stack/test_inji_web_vc_readiness.py --live # same plus live Mimoto/Inji Web checks
python3 vc-stack/test_installation_guard.py           # the scripts refuse a missing INSTALLATION; bash only, no Docker
python3 vc-stack/test_installations.py                # every installation's realm users match its adapter CSV, and its smoke personas are among them; no Docker
python3 portal/test_auth.py                           # demo app logic; host Python or inside the image, see below
python3 portal/test_requests.py
python3 data/test_ait_courses.py                      # data fixture tests
python3 data/test_generate_csv.py
python3 data/test_render_mimoto_issuers_config.py      # issuer-list rendering, web and mobile
python3 adapter/test_adapter.py                       # mock adapter on a generated CSV and on the hackathon roster; needs portal/requirements.txt, no Docker. smoke.sh runs it against the container, the edit case against a second adapter on a copy of the CSV: test_adapter.py http://adapter:8000 <csv> http://adapter-copy:8000 <copy>
python3 gateway/tests/test_credential_types.py         # the transcript's, the Developer Passport's and the Achievement's checklists and claim mappings; needs gateway/ and portal/requirements.txt, no Docker
python3 gateway/tests/test_issuances.py                # POST /issuances with the mock adapter in-process, store faked, for every type in every installation's smoke.json; no Docker. smoke.sh runs it in the gateway image against the containers: test_issuances.py http://gateway:8000 <csv> <smoke.json>
python3 vc-stack/test_context_refresh.py              # context_refresh.sql against a throwaway Postgres; needs Docker
docker run --rm -v "$PWD/gateway/plugin:/src" -w /src maven:3.9-eclipse-temurin-21 mvn -q package   # the plugin jar and its JUnit tests (stand-in Gateway on a local port); CI: .github/workflows/plugin.yml
docker compose -f vc-stack/docker-compose.yaml run --rm --no-deps demo-app python portal/test_requests.py   # the in-container form
```

`vc-stack/issue_and_verify.py` issues a credential without a browser (direct-access grant on the realm's test-only `smoke` client, an ES256 proof JWT as `did:jwk`, Certify's `/issuance/credential`), writes it to a file, then checks it in verify-service's `v2/vc-verification`: `SUCCESS`, and `ERR_SIGNATURE_VERIFICATION_FAILED` for each copy with the holder id or one of the claim paths it is given changed (the installation's `smoke.json` `tamper`: `fullName` and one grade inside `courses` for the transcript, `teamName` for the Developer Passport, `award` for the Achievement). Its `refused` step expects the request refused with a given OpenID4VCI error code (`checklist_failed` for a refused persona, `gateway_error` with the Gateway down). It needs the stack up and runs inside the Docker network (Certify accepts only tokens issued as `http://keycloak:8080`) from the demo-app image, which carries `httpx` and `cryptography`; rebuild demo-app first if `portal/requirements.txt` changed. demo-app does not mount `vc-stack/`, so the run mounts the script; the exact commands are in its docstring and in `smoke.sh`.

The full browser OAuth and PDF download is still manual (PRD §9); the readiness script only guards the misconfigurations that broke it before.

Local URLs: demo app `:4100` (`/student/login`, `/registrar/login`), Inji Web `:4004`, Inji Verify `:4007`, Keycloak admin `:9080` (admin / admin), Certify behind nginx `:9091`. Every host port is the upstream `inji/vc-stack` default plus 1000, so both stacks can run side by side; the Docker network is `vc_stack_network` for the same reason.

Deployment is manual and ships one commit: push, then run the `Deploy` workflow (`workflow_dispatch` only) for a branch or tag. It copies `deploy/remote-deploy.sh` to the GCE VM, which checks out that commit into `/opt/ait-transcript-demo`, copies the VM's `app.env` to `vc-stack/.env`, writes the installation name (`ait` unless `app.env` names one) to `vc-stack/.installation` so it survives reboots, and runs `run-demo.sh`. Nothing on the VM pulls code by itself. The first deploy of a commit that changes the seed (`installations/ait/certify_seed.sql`) needs `wipe=true`, which also renews the signing key and `did:key`.

## Architecture

**Data flow, which crosses four places.** `data/students.json` is the single source of truth for mock personas (registrars and students, each student with a `degrees` list). `data/generate_csv.py` turns it into `installations/ait/adapter/student_identity_data.csv` (git-ignored), which the `adapter` container serves over HTTP (`contracts.md` section 2b) to the Gateway, which builds Certify's claims from it: the claim columns (`CLAIM_COLUMNS` in `generate_csv.py`) come first, the eligibility columns (`level, holds, conferralStatus, balance`) after them. Every cell holds its value verbatim (`courses` and `holds` as JSON text, which the adapter decodes); the adapter serves the other cells as written, and the Gateway is the only place a claim is escaped for Certify's template. `data/ait_courses.py` derives the course claims (`courses`, `courseList`) and is an adapted copy of the frozen `design/ait_courses.py`; change the `data/` copy, never `design/`. Identity is per degree, not per student: a student with two degrees is one JSON entry but two CSV rows and two Keycloak users. The hackathon installation has no generator: its roster, `installations/hackathon/adapter/student_identity_data.csv`, is committed and edited by hand, one row per participant. The adapter is column-driven, so the same image serves both: the record path serves every column but `id`, the eligibility path every column beyond the transcript's record (on the roster, the whole row).

**The demo app** (`portal/main.py`, served by uvicorn on `:4100`) has a student side (request, see claim instructions) and a registrar side (approve, reject, revoke, reissue). `requests.py` holds the request state machine (`pending`, `approved`, `rejected`) over SQLite in `db.py`, bind-mounted at `.demo-state/demo_requests.db` so it survives `down`/`up`. `auth.py` is a signed-cookie persona picker, not authentication. `certify_client.py` is the only server-to-server integration: it talks to Certify through `certify-nginx` for `ledger-search`, the Bitstring status list and the revoke call. The app never calls Mimoto or Keycloak; claiming happens in the browser via Inji Web.

**The Gateway** (`gateway/`, FastAPI, service `gateway`, no host port) serves `POST /issuances` of `contracts.md` section 2a, the checklist runner the Certify data-provider plugin calls on every credential request. `credential_types.py` is the registry of credential types keyed by scope (the transcript; the Developer Passport with its one check `on_roster`, a non-empty `teamId`; the Achievement with `on_roster` then `winner`, the roster's `winner` column being `true`): each names its checks and the template's claims, taken by name from the adapter's record unless derived, and every string claim is escaped by its `escape_vc_quoted_claim`, the only escaper in the chain, because Certify substitutes claims into a quoted Velocity template; a claim the record lacks or serves as null is a 502 `gateway_error`, never an empty or `"None"` claim. `main.py` authenticates the shared bearer token, fetches from the adapter, evaluates the checks and maps refusals to 400/401/403/404 and adapter or database failures to 502 `gateway_error`; it never calls the adapter at startup. `store.py` writes one identifiers-only row per 200 into `gateway.issuances` in Certify's Postgres, creating the schema on start. Settings come from `installations/<name>/gateway.env`.

**The Certify plugin** (`gateway/plugin/`, Maven, Java 21) is `GatewayDataProviderPlugin`, Certify's data provider: it posts the access-token claims minus `accessTokenHash` to the Gateway with the bearer token, turns every top-level object or array of the 200 into its JSON text (the template's unquoted `${courses}` needs text), and turns any other answer into `DataProviderExchangeException` with the body's `error`, else `gateway_error` (also when the Gateway is unreachable or slow); no `sub` is `invalid_access_token`. It calls nothing at startup. It is compiled against `io.inji.certify:certify-integration-api:0.14.0` with every dependency `provided`, so the jar carries one class. `run-demo.sh` builds it into git-ignored `vc-stack/plugins/`, and Compose mounts that single file into `/home/inji/additional_jars/` (never the directory, which would hide the four bundled jars). It is selected by the six keys of `contracts.md` section 2a in the installation's Certify properties; its token must equal `GATEWAY_AUTH_TOKEN` in `gateway.env`.

**Approval gate.** Every mock student is always issuable at the Certify and Keycloak layer. Approval is enforced only by what the demo app shows (the claim link appears after approval). This is a documented scope cut, `wiki/concepts/approval-gate.md`; do not "fix" it unless asked.

**The stack.** `vc-stack/docker-compose.yaml` runs PostgreSQL, Inji Certify 0.14 (with its nginx), Mimoto 0.21, Keycloak 24 (with its nginx), Inji Web 0.16, Inji Verify 0.17 (service and UI), a public gateway, the static mock VDR (`vdr`, stock nginx) and the demo app. `bootstrap.sh` is idempotent and does the parts Compose cannot: `.env`, the Docker network, Mimoto's OIDC keystore and client cert, syncing that cert into `keycloak-realm.json`, bringing services up in order, waiting, the did:key refresh after a wipe, and end-to-end validation. Seed SQL lives in `certify_init.sql`, `mimoto_init.sql` and `verify_init.sql`; Certify's credential configuration, including the VC template and the JSON-LD context URL, is an `INSERT` in the installation's `certify_seed.sql`. The AIT JSON-LD context is versioned: v1 is `vc-lab/contexts/transcript/v1.json`, served by the `vdr` container under `/contexts/` through the public gateway and referenced as `http://host.docker.internal:9098/contexts/transcript/v1.json`, so Certify and verify-service can resolve it from inside Docker. The template's `@context` and the row's `context` column must name that URL identically. Every claim term is top-level and untyped except `courses` (`@json`), so the signature covers every claim; see `wiki/concepts/transcript-context.md`. The hackathon installation's contexts, `vc-lab/contexts/developer-passport/v1.json` and `vc-lab/contexts/achievement/v1.json`, are served and referenced the same way, every term an untyped string.

**Installations.** What differs per installation (Certify properties, including the authorization server's realm, and `credential_config` rows, Keycloak realm, Gateway settings, Mimoto issuer list, adapter CSV, and the test fixtures `smoke.json`) lives in `installations/<name>/`, mounted through `${INSTALLATION}` in the one `docker-compose.yaml`; everything in `vc-stack/` is shared, and the scripts read the realm and the Mimoto issuer id from the installation's files. `ait` issues the transcript (realm `inji`); `hackathon` issues the Developer Passport and the Achievement (realm `hackathon`, a committed roster). Each `installations/<name>/README.md` lists the files and the installation's own values. CI's `stack-smoke` job runs once per installation, each on a fresh runner.

**Revocation.** The registrar's revoke is one Certify status API call; Certify's batch job re-signs the status list every 10 seconds in this stack, and the verifier fetches it from the URL inside the credential. There is no duplicate revocation state in the demo app; see `wiki/concepts/vc-revocation.md`, which also records the VCDM 1.1 to 2.0 migration that made `credentialStatus` appear.

## Things that bite, documented once

Read before touching the stack, and do not re-discover them:

- `wiki/architecture/vc-stack.md`: Keycloak's browser URL is `localhost:9080` while its token issuer is `http://keycloak:8080`; realm changes need a container recreate, not a restart; the Keycloak and Certify nginx containers resolve upstreams at start, so a recreated `keycloak-server` or `certify` leaves `:9080`/`:9091` at 502 until the nginx is restarted (`run-demo.sh` already restarts the proxies).
- `wiki/concepts/transcript-credential.md` and `wiki/concepts/vc-revocation.md`: each has a "Gotchas already hit" section.
- `wiki/guides/vc-download-troubleshooting.md`: the four layered failures behind an empty issuer list, a Keycloak login that does not load, or "session is not valid" on download.

## Repository rules

- `*.sh` files are forced to LF by `.gitattributes` because they run on Linux runners and the VM; the Markdown and config files in a Windows checkout are CRLF through `core.autocrlf`.
- Generated or environment-specific files are git-ignored and must stay so: `installations/ait/adapter/student_identity_data.csv`, `installations/<name>/mimoto-issuers-config.json` (rendered from its `.template` with `INJI_WEB_URL`), `vc-stack/.env`, `vc-stack/certs/`, `vc-stack/data/`, `vc-stack/plugins/` (the plugin jar and its Maven cache), `gateway/plugin/target/`, `.demo-state/*`. No jar is ever committed.
- `AGENTS.md`, `PLAN.md` and `wiki/log.md` at the root are local-only notes and are ignored by git; some docstrings still refer to them.
- `wiki/OVERVIEW.md` is the index of the wiki; add new pages there.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `mosip-asia/ait-transcript`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, alongside the existing `wiki/`. See `docs/agents/domain.md`.
