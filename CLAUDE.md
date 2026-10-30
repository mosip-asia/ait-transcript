# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

The Issuer: a credential issuer built on pinned upstream Inji images. A wallet asks Inji Certify for a credential; Certify's data-provider plugin asks the Gateway (`gateway/`), which fetches the record from an Adapter (`adapter/` is the mock one), runs the credential type's checklist and returns the claims Certify signs (W3C VCDM 2.0, JSON-LD, Ed25519Signature2020). Around it, a demo stack runs the whole journey locally: the Portal (`portal/`, the demo app), Keycloak, Mimoto, Inji Web and Inji Verify, revocation included.

An **Installation** (`installations/<name>/`) is one issuing deployment's settings: `ait` issues the AIT transcript, `hackathon` the Developer Passport and the Achievement. Terms are in `CONTEXT.md`. What the Issuer must become is in `wiki/project/issuer-v0.1/`; the configuration contract there is checked against the Compose files, and `spec-part-2.md` is planned work, not code.

`wallet/` carries patches, not a wallet: `wallet/apply.sh <platform>` patches Inji Wallet v0.22.1 to talk to the GCP deployment (`wallet/README.md`).

## Commands

The README has every command: [Deploy locally](README.md#deploy-locally) and [How to test](README.md#how-to-test). What to know before running them:

- Everything runs through Docker. On Windows, use WSL2 with the repo cloned into the WSL filesystem, not Git Bash and not `/mnt/c`.
- `INSTALLATION` (`ait` or `hackathon`) comes from the environment, else `vc-stack/.env`, else the marker `vc-stack/.installation`; the scripts stop before any container starts when it names no directory. Certify's seed runs only on a fresh database, so switching Installation needs `--wipe`.
- `./run-demo.sh` brings up the whole stack (`vc-stack/compose.yaml`); `vc-stack/issuer-dev.yaml` is the Issuer and the mock Adapter alone, as the dev server runs them. Re-run `run-demo.sh` when `data/students.json` changes.
- Tests are plain Python scripts, not pytest: `python3 <path>`. Most need no Docker. `./vc-stack/smoke.sh` (full stack) and `./vc-stack/issuer-smoke.sh` (Issuer alone) need the stack up; both read the personas, scopes and tampered claims from `installations/<name>/smoke.json`.
- `portal/` and `data/` are bind-mounted into demo-app with `--reload`; rebuild demo-app only when `portal/requirements.txt` changes.

Deployment is manual: push, then run the `Deploy` workflow for a commit. A commit that changes an Installation's `certify_seed.sql` needs `wipe=true`, which also renews the signing key and `did:key`.

## Architecture

- **Data.** `data/students.json` is the source of truth for the AIT personas; `data/generate_csv.py` writes the git-ignored `installations/ait/adapter/student_identity_data.csv` from it (claim columns first, then the eligibility columns). Identity is per degree: a student with two degrees is two rows and two Keycloak users. The hackathon roster CSV is committed and edited by hand. Change `data/ait_courses.py`, never the frozen `design/` copy.
- **Gateway** (`gateway/`). `POST /issuances` (`contracts.md` section 2a). `credential_types.py` is the registry keyed by scope: Pydantic models of the Adapter's answers following `adapter/openapi.yaml` strictly, and each type's checks (a check returns its failure reason, or `None`). An answer that does not parse is a 502 `gateway_error`, never an empty claim; a check that raises is a 500. Every claim but `courses` is a string escaped by `escape_vc_quoted_claim`, the only escaper in the chain. `store.py` writes one identifiers-only row per 200 to `gateway.issuances`. Settings: `installations/<name>/gateway.env`.
- **Certify plugin** (`gateway/plugin/`, Java 21). `GatewayDataProviderPlugin` posts the token's claims to the Gateway and turns any refusal into Certify's error. Compiled against `certify-integration-api:0.14.0` with every dependency `provided`, so the jar is one class; `run-demo.sh` builds it into `vc-stack/plugins/`.
- **Approval gate.** Every persona is issuable at Certify and Keycloak; the Portal shows the claim link only after a registrar approves. A deliberate scope cut: do not "fix" it unless asked.
- **The stack** (`vc-stack/`): one folder per deployment (`issuer/`, `mock-adapter/`, `verify/`, `demo/`), each `name: vc-stack`, pulled together by `include:`. Mount sources stay in `vc-stack/`, so folder paths start with `../`. Each group with a database has its own. `wiki/architecture/vc-stack.md` has the table.
- **Authorization Server**: set in one place, `installations/<name>/authorization-server.env`, the only file that names a realm path; `vc-stack/.env` overrides each value.
- **Contexts**: the JSON-LD contexts in `vc-lab/contexts/` are served by `vdr`; the template's `@context` and the `credential_config` row's `context` column must name the same URL. Every claim term is top-level and untyped except `courses` (`@json`), so the signature covers every claim (`wiki/concepts/transcript-context.md`).
- **Revocation** is one Certify status API call from the Portal; Certify re-signs the status list about every 60 seconds (`wiki/concepts/vc-revocation.md`).

`bootstrap.sh` is idempotent and does what Compose cannot: `.env`, the network, Mimoto's keystore, bring-up order, the did:key refresh after a wipe, the context refresh, and validation.

## Things that bite

Read before touching the stack:

- `wiki/architecture/vc-stack.md`: Keycloak's browser URL is `localhost:9080` but its token issuer is `http://keycloak:8080`; realm changes need a recreate; the nginx containers resolve upstreams at start, so recreating `keycloak-server` or `certify` needs the proxies restarted (`run-demo.sh` does).
- `wiki/reference/vc-download-troubleshooting.md`: the four layered failures behind an empty issuer list, a login page that does not load, or "session is not valid".
- `wiki/concepts/transcript-credential.md` and `wiki/concepts/vc-revocation.md`: their "Gotchas" sections.
- Mount the plugin jar as a single file, never `additional_jars/` as a directory, which would hide the four bundled jars.
- Never `sed -i` a bind-mounted file: Docker Desktop keeps mounting the replaced file, so the next restart fails. Use `sed_in_place` in `bootstrap.sh`.
- Certify runs as root and writes `vc-stack/data/` as root; remove it from a container.

## Repository rules

- `*.sh` files are LF (`.gitattributes`); other text files are CRLF in a Windows checkout.
- Generated and environment files stay git-ignored: the ait adapter CSV, `installations/<name>/mimoto-issuers-config.json`, `vc-stack/.env`, `vc-stack/certs/`, `vc-stack/data/`, `vc-stack/plugins/`, `gateway/plugin/target/`, `.demo-state/*`. No jar is committed.
- `AGENTS.md`, `PLAN.md` and `wiki/log.md` at the root are local-only and git-ignored.

## Docs

`wiki/OVERVIEW.md` is the index: what to read first, then `wiki/reference/` (lookup pages agents and operators use, not reading material). A page named `*.stale.md` with "(stale)" in its title was written by someone else and no longer holds; leave it, do not cite it as current. Retired pages are not kept; OVERVIEW names the commit to recover them from. Add a page only when no existing page can take the content, and list it in OVERVIEW.

## Agent skills

- **Issue tracker**: local Markdown outside this repo; never GitHub Issues. See `docs/agents/issue-tracker.md`.
- **Triage labels**: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, as a `Status:` line.
- **Domain docs**: one context, `CONTEXT.md`; there is no `docs/adr/`.
