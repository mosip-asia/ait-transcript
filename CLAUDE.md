# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

The Issuer: a credential issuer built on pinned upstream Inji images. A wallet asks Inji Certify for a credential; Certify's Data-provider plugin (`plugin/`) reads the student's record from an Adapter (`adapter/` is the mock one) and, with the gate on, first asks the Gateway (`gateway/`), the optional Approval gate, which runs the credential type's Checklist on the Adapter's eligibility attributes; Certify signs the record's claims (W3C VCDM 2.0, JSON-LD, Ed25519Signature2020). Why the gate sits beside the data path: `docs/adr/0001-approval-gate-beside-the-data-path.md`. Around it, a demo stack runs the whole journey locally: the Portal (`portal/`, the demo app), Keycloak, Mimoto, Inji Web and Inji Verify, revocation included.

An **Installation** (`deploy/<name>/`) is one issuing deployment's settings: `ait` issues the AIT transcript, `hackathon` the Developer Passport and the Achievement. Terms are in `CONTEXT.md`. What the Issuer must become is in `docs/project/issuer-v0.1/`; the configuration contract there is checked against the Compose files, and `spec-part-2.md` is planned work, not code.

- **Web Wallet.** End-to-end credential claiming is demonstrated via the Inji Web Wallet container.

## Commands

- Standard automation scripts in `scripts/`:
  - `./scripts/deploy.sh [installation] [--wipe]`: Builds plugin JAR if needed and brings up the Issuer Platform stack.
  - `./scripts/smoke-test.sh [certify_url] [student_id] [config_id]`: Post-deployment OpenID4VCI issuance smoke test.
  - `./scripts/release.sh`: Build and publish Docker images and release artifacts.
- Tests are plain Python scripts:
  - `python3 tests/test_installations.py`
  - `python3 tests/test_authorization_server.py`
  - `python3 tests/test_inji_web_vc_readiness.py`
  - `python3 src/verifier/test_verifier.py`
  - `python3 src/tools/test_generate_csv.py`
  - `python3 src/tools/test_render_mimoto_issuers_config.py`
  - `.venv/bin/python tests/test_issue_and_verify.py`
  - `.venv/bin/python src/adapter/test_adapter.py`
  - `.venv/bin/python src/gateway/tests/test_evaluations.py`
- Compose profiles:
  - `compose.yaml`: Inji Certify, Certify Nginx, PostgreSQL database, VDR context server, template-sync.
  - `compose.verify.yaml`: Custom branded Verifier (`src/verifier` on port 4007) and Inji Verify service (port 9095).
  - `compose.demo.yaml`: End-to-end demo with Inji Web Wallet mock (port 4004), Mimoto (port 9099), Keycloak (port 9080), demo app (port 4100), gateway, and adapter.

Deployment is manual: push, then run the `Deploy` workflow for a commit. A commit that changes an Installation's `certify_seed.sql` needs `wipe=true`, which also renews the signing key and `did:key`.

## Architecture

- **Data.** `tests/fixtures/students.json` is the source of truth for the mock personas; `src/tools/generate_csv.py` can regenerate `deploy/ait/adapter/student_identity_data.csv` from it. Identity is per degree: a student with two degrees is two rows and two Keycloak users. Both `ait` and `hackathon` adapter CSVs are committed.
- **Data flow.** The token's `sub` and `scope` go from Certify to the plugin, which asks the Gateway's `POST /evaluations` (`{sub, scope}`) when the gate is on, then reads the record at its record URL with `{sub}` filled in (`GET /student/{sub}/transcript`); the Gateway reads only its eligibility URL (`GET /student/{sub}/eligibility`). Both URLs are whole settings the deployment owns. `docs/contracts/adapter-openapi.yaml` is the contract (a record schema and an eligibility schema per scope, by `x-scope`) and, with `docs/schemas/ait-transcript-credential.v2.schema.json`, a master file: a test holds the transcript record to that schema's subject. `docs/project/issuer-v0.1/contracts.md` section 2 explains it. The Adapter serves values verbatim; the plugin is the only escaper.
- **Mock Adapter** (`mock/adapter/`). The mock, column-driven, reads the CSV on every request and keys a row by its `id`, the `sub`: `/student/{sub}/transcript` serves the record to both Installations' Certify, the scope picking its schema.
- **Gateway** (`src/gateway/`, optional). `POST /evaluations`, the read-only Checklist evaluation (`{sub, scope}`, reads only `GATEWAY_ELIGIBILITY_URL`).
- **Data-provider plugin** (`src/issuer/`, Java 21). `IssuerDataProviderPlugin` asks the Gateway's `POST /evaluations` about the token's `sub` when `mosip.certify.gateway.enabled=true`, reads the record at `mosip.certify.adapter.record-url` with `{sub}` filled in. Compiled against `certify-integration-api:0.14.0`.
- **Verifier** (`src/verifier/`). Custom branded Inji Verify UI overlay with institutional theme CSS variables and custom SVG logo.
- **Registrar approval.** The Portal shows the claim link only after a registrar approves.
- **Contexts**: the JSON-LD contexts in `deploy/<tenant>/contexts/` are served by `vdr`.
- **Revocation** is one Certify status API call from the Portal; Certify re-signs the status list about every 60 seconds (`docs/concepts/vc-revocation.md`).

`bootstrap.sh` is idempotent and does what Compose cannot: `.env`, the network, Mimoto's keystore, bring-up order, the did:key refresh after a wipe, the context refresh, and validation.

## Things that bite

Read before touching the stack:

- `docs/architecture/vc-stack.md`: Keycloak's browser URL is `localhost:9080` but its token issuer is `http://keycloak:8080`; realm changes need a recreate; the nginx containers resolve upstreams at start, so recreating `keycloak-server` or `certify` needs the proxies restarted (`run-demo.sh` does).
- `docs/reference/vc-download-troubleshooting.md`: the four layered failures behind an empty issuer list, a login page that does not load, or "session is not valid".
- `docs/concepts/transcript-credential.md` and `docs/concepts/vc-revocation.md`: their "Gotchas" sections.
- Mount the plugin jar as a single file, never `additional_jars/` as a directory, which would hide the four bundled jars.
- Never `sed -i` a bind-mounted file: Docker Desktop keeps mounting the replaced file, so the next restart fails. Use `sed_in_place` in `bootstrap.sh`.
- Certify runs as root and writes `vc-stack/data/` as root; remove it from a container.

## Repository rules

- `*.sh` files are LF (`.gitattributes`); other text files are CRLF in a Windows checkout.
- Generated and environment files stay git-ignored: `deploy/<name>/mimoto-issuers-config.json`, `vc-stack/.env`, `vc-stack/certs/`, `vc-stack/data/`, `vc-stack/plugins/`, `src/issuer/target/`, `.demo-state/`. No jar is committed.
- `AGENTS.md`, `PLAN.md` and `docs/log.md` at the root are local-only and git-ignored.

## Docs

`docs/OVERVIEW.md` is the index: what to read first, then `docs/reference/` (lookup pages agents and operators use, not reading material). A page named `*.stale.md` with "(stale)" in its title was written by someone else and no longer holds; leave it, do not cite it as current. Retired pages are not kept; OVERVIEW names the commit to recover them from. Add a page only when no existing page can take the content, and list it in OVERVIEW.

## Agent skills

- **Issue tracker**: local Markdown outside this repo; never GitHub Issues. See `docs/agents/issue-tracker.md`.
- **Triage labels**: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, as a `Status:` line.
- **Domain docs**: one context, `CONTEXT.md`; decisions in `docs/adr/`.
