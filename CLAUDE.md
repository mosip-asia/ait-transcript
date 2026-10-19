# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A self-contained demo of one journey: an AIT student requests an academic transcript, a registrar approves it, the student claims it as a W3C Verifiable Credential (VCDM 2.0, JSON-LD, Ed25519Signature2020) into Inji Web, and a relying party verifies it in Inji Verify, including revocation. Everything runs in one Docker Compose stack (`vc-stack/`) built from pinned upstream Inji images plus one custom service, the FastAPI demo app in `app/`. `PRD.md` is the authority on what the demo does and does not do; its §3 non-goals and §6.3 (approval is enforced in the demo app UI only, not at issuance) are deliberate.

The documents under `wiki/project/` (the issuer proposal of PR 4, and `issuer-v0.1/` with its responsibilities, contracts and deviations) and the glossary in `CONTEXT.md` describe the planned Issuer product, not the running demo. Do not treat them as a description of the code.

`wallet/` carries patches, not a wallet: `wallet/apply.sh <platform>` clones Inji Wallet v0.22.1 and applies the `common/` and per-platform changes that let it talk to the GCP deployment. The phone app gets its own issuer list and metadata through the `api.` gateway (`vc-stack/config/mimoto-issuers-mobile.json`, `public-gateway-mobile.conf`); see `wiki/architecture/inji-mobile-wallet.md` and `wallet/README.md`.

## Commands

Everything runs through Docker; the host needs only Docker Desktop (Compose v2), `jq`, `curl` and `awk`. On Windows, use WSL2 with the repo cloned into the WSL filesystem, not Git Bash and not `/mnt/c`.

```sh
./run-demo.sh                      # full bring-up: build demo app, regenerate the Certify CSV from data/students.json, render mimoto-issuers-config.json, then vc-stack/bootstrap.sh
./run-demo.sh --wipe               # same, after tearing down volumes and ephemeral files (new signing key and did:key)
./vc-stack/bootstrap.sh --validate # only the end-to-end health checks
./vc-stack/bootstrap.sh --did-refresh  # only the post-wipe did:key refresh
```

After the first `run-demo.sh` (which creates `vc-stack/.env` and the external network), the plain Compose form works: `docker compose -f vc-stack/docker-compose.yaml up -d --build`. Re-run `./run-demo.sh` whenever `data/students.json` changes, so the Certify CSV stays in sync.

Demo app development: `app/` and `data/` are bind-mounted and uvicorn runs with `--reload`, so Python and template edits apply live. Rebuild only when `app/requirements.txt` changes:

```sh
docker compose -f vc-stack/docker-compose.yaml build demo-app
docker compose -f vc-stack/docker-compose.yaml up -d demo-app
```

Tests are plain Python scripts, not pytest. Run one by name:

```sh
./vc-stack/smoke.sh                                   # stack smoke checks over curl/jq; stack must be up; also runs the readiness script
python3 vc-stack/test_inji_web_vc_readiness.py        # config checks for the Inji Web download path, no Docker needed
python3 vc-stack/test_inji_web_vc_readiness.py --live # same plus live Mimoto/Inji Web checks
python3 app/test_auth.py                              # demo app logic; host Python or inside the image, see below
python3 app/test_requests.py
python3 data/test_ait_courses.py                      # data fixture tests
python3 data/test_generate_csv.py
python3 data/test_render_mimoto_issuers_config.py      # issuer-list rendering, web and mobile
python3 vc-stack/test_context_refresh.py              # context_refresh.sql against a throwaway Postgres; needs Docker
docker compose -f vc-stack/docker-compose.yaml run --rm --no-deps demo-app python app/test_requests.py   # the in-container form
```

The full browser OAuth and PDF download is still manual (PRD §9); the readiness script only guards the misconfigurations that broke it before.

Local URLs: demo app `:4100` (`/student/login`, `/registrar/login`), Inji Web `:4004`, Inji Verify `:4007`, Keycloak admin `:9080` (admin / admin), Certify behind nginx `:9091`. Every host port is the upstream `inji/vc-stack` default plus 1000, so both stacks can run side by side; the Docker network is `vc_stack_network` for the same reason.

Deployment is manual and ships one commit: push, then run the `Deploy` workflow (`workflow_dispatch` only) for a branch or tag. It copies `deploy/remote-deploy.sh` to the GCE VM, which checks out that commit into `/opt/ait-transcript-demo`, copies the VM's `app.env` to `vc-stack/.env`, and runs `run-demo.sh`. Nothing on the VM pulls code by itself.

## Architecture

**Data flow, which crosses four places.** `data/students.json` is the single source of truth for mock personas (registrars and students, each student with a `degrees` list). `data/generate_csv.py` turns it into `vc-stack/config/student_identity_data.csv` (git-ignored), which Certify's CSV data-provider plugin reads to build claims. The column order in `generate_csv.py`'s `CLAIM_COLUMNS` must match `data-columns` in `vc-stack/config/certify-csvdp-student.properties` exactly, because Certify maps cells to claims by position. `data/ait_courses.py` derives the course claims (`courses`, `courseTableHtml`, `courseList`) and is an adapted copy of the frozen `design/ait_courses.py`; change the `data/` copy, never `design/`. Identity is per degree, not per student: a student with two degrees is one JSON entry but two CSV rows and two Keycloak users.

**The demo app** (`app/main.py`, served by uvicorn on `:4100`) has a student side (request, see claim instructions) and a registrar side (approve, reject, revoke, reissue). `requests.py` holds the request state machine (`pending`, `approved`, `rejected`) over SQLite in `db.py`, bind-mounted at `.demo-state/demo_requests.db` so it survives `down`/`up`. `auth.py` is a signed-cookie persona picker, not authentication. `certify_client.py` is the only server-to-server integration: it talks to Certify through `certify-nginx` for `ledger-search`, the Bitstring status list and the revoke call. The app never calls Mimoto or Keycloak; claiming happens in the browser via Inji Web.

**Approval gate.** Every mock student is always issuable at the Certify and Keycloak layer. Approval is enforced only by what the demo app shows (the claim link appears after approval). This is a documented scope cut, `wiki/concepts/approval-gate.md`; do not "fix" it unless asked.

**The stack.** `vc-stack/docker-compose.yaml` runs PostgreSQL, Inji Certify 0.14 (with its nginx), Mimoto 0.21, Keycloak 24 (with its nginx), Inji Web 0.16, Inji Verify 0.17 (service and UI), a public gateway and the demo app. `bootstrap.sh` is idempotent and does the parts Compose cannot: `.env`, the Docker network, Mimoto's OIDC keystore and client cert, syncing that cert into `keycloak-realm.json`, bringing services up in order, waiting, the did:key refresh after a wipe, and end-to-end validation. Seed SQL lives in `certify_init.sql`, `mimoto_init.sql` and `verify_init.sql`; Certify's credential configuration, including the VC template and the JSON-LD context URL, is an `INSERT` in `certify_init.sql`. The AIT JSON-LD context is `vc-stack/config/academic-transcript-context.json`, served by certify-nginx and referenced as `http://host.docker.internal:9091/...` so verify-service can resolve it from inside Docker.

**Revocation.** The registrar's revoke is one Certify status API call; Certify's batch job re-signs the status list every 10 seconds in this stack, and the verifier fetches it from the URL inside the credential. There is no duplicate revocation state in the demo app; see `wiki/concepts/vc-revocation.md`, which also records the VCDM 1.1 to 2.0 migration that made `credentialStatus` appear.

## Things that bite, documented once

Read before touching the stack, and do not re-discover them:

- `wiki/architecture/vc-stack.md`: Keycloak's browser URL is `localhost:9080` while its token issuer is `http://keycloak:8080`; realm changes need a container recreate, not a restart; the Keycloak and Certify nginx containers resolve upstreams at start, so a recreated `keycloak-server` or `certify` leaves `:9080`/`:9091` at 502 until the nginx is restarted (`run-demo.sh` already restarts the proxies).
- `wiki/concepts/transcript-credential.md` and `wiki/concepts/vc-revocation.md`: each has a "Gotchas already hit" section.
- `wiki/guides/vc-download-troubleshooting.md`: the four layered failures behind an empty issuer list, a Keycloak login that does not load, or "session is not valid" on download.

## Repository rules

- `*.sh` files are forced to LF by `.gitattributes` because they run on Linux runners and the VM; the Markdown and config files in a Windows checkout are CRLF through `core.autocrlf`.
- Generated or environment-specific files are git-ignored and must stay so: `vc-stack/config/student_identity_data.csv`, `vc-stack/config/mimoto-issuers-config.json` (rendered from its `.template` with `INJI_WEB_URL`), `vc-stack/.env`, `vc-stack/certs/`, `vc-stack/data/`, `.demo-state/*`.
- `AGENTS.md`, `PLAN.md` and `wiki/log.md` at the root are local-only notes and are ignored by git; some docstrings still refer to them.
- `wiki/OVERVIEW.md` is the index of the wiki; add new pages there.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `mosip-asia/ait-transcript`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root, alongside the existing `wiki/`. See `docs/agents/domain.md`.
