# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

The Issuer: a credential issuer built on pinned upstream Inji images. A wallet asks Inji Certify for a credential; Certify's Data-provider plugin (`plugin/`) lists and fetches the record from an Adapter (`adapter/` is the mock one) and, with the gate on, first asks the Gateway (`gateway/`), the optional Approval gate, which runs the credential type's Checklist on the Adapter's eligibility attributes; Certify signs the record's claims (W3C VCDM 2.0, JSON-LD, Ed25519Signature2020). Why the gate sits beside the data path: `docs/adr/0001-approval-gate-beside-the-data-path.md`. Around it, a demo stack runs the whole journey locally: the Portal (`portal/`, the demo app), Keycloak, Mimoto, Inji Web and Inji Verify, revocation included.

An **Installation** (`installations/<name>/`) is one issuing deployment's settings: `ait` issues the AIT transcript, `hackathon` the Developer Passport and the Achievement. Terms are in `CONTEXT.md`. What the Issuer must become is in `wiki/project/issuer-v0.1/`; the configuration contract there is checked against the Compose files, and `spec-part-2.md` is planned work, not code.

`wallet/` carries patches, not a wallet: `wallet/apply.sh <platform>` patches Inji Wallet v0.22.1 to talk to the GCP deployment (`wallet/README.md`).

## Commands

The README has every command: [Deploy locally](README.md#deploy-locally) and [How to test](README.md#how-to-test). What to know before running them:

- Everything runs through Docker. On Windows, use WSL2 with the repo cloned into the WSL filesystem, not Git Bash and not `/mnt/c`.
- `INSTALLATION` (`ait` or `hackathon`) comes from the environment, else `vc-stack/.env`, else the marker `vc-stack/.installation`; the scripts stop before any container starts when it names no directory. Certify's seed runs only on a fresh database, so switching Installation needs `--wipe`.
- `./run-demo.sh` brings up the whole stack (`vc-stack/compose.yaml`); `vc-stack/issuer-dev.yaml` is the Issuer, the Gateway and the mock Adapter alone, as the dev server runs them. Re-run `run-demo.sh` when `data/students.json` changes.
- **The gate's switch.** Both Installations commit the gate on (`mosip.certify.gateway.enabled=true` in `certify-installation.properties`). Each stack has a no-Gateway form, `vc-stack/compose-no-gateway.yaml` and `vc-stack/issuer-dev-no-gateway.yaml`: the same folders without `gateway/`, with `vc-stack/issuer/no-gateway.yaml` setting `MOSIP_CERTIFY_GATEWAY_ENABLED=false` and `MOSIP_CERTIFY_GATEWAY_URL=NO GATEWAY` in Certify's environment. Every script runs the file `COMPOSE_FILE` names (relative to `vc-stack/`): `COMPOSE_FILE=compose-no-gateway.yaml ./run-demo.sh`, then the smoke with the same value. Any other switch setting stops Certify at startup.
- Tests are plain Python scripts, not pytest: `python3 <path>`. Most need no Docker. `./vc-stack/smoke.sh` (full stack) and `./vc-stack/issuer-smoke.sh` (Issuer alone) need the stack up, with either switch setting; both read the personas, scopes and tampered claims from `installations/<name>/smoke.json`, and both run `vc-stack/issuer-checks.sh` first. CI runs each smoke per Installation and switch setting.
- `portal/` and `data/` are bind-mounted into demo-app with `--reload`; rebuild demo-app only when `portal/requirements.txt` changes.

Deployment is manual: push, then run the `Deploy` workflow for a commit. A commit that changes an Installation's `certify_seed.sql` needs `wipe=true`, which also renews the signing key and `did:key`.

## Architecture

- **Data.** `data/students.json` is the source of truth for the AIT personas; `data/generate_csv.py` writes the git-ignored `installations/ait/adapter/student_identity_data.csv` from it (claim columns first, `courseList` among them, then the eligibility columns). Identity is per degree: a student with two degrees is two rows and two Keycloak users. The hackathon roster CSV is committed and edited by hand. Change `data/ait_courses.py`, never the frozen `design/` copy.
- **Data flow.** The token's `sub` and `scope` go from Certify to the plugin, which reads the Adapter's `GET /records?sub&scope` (first `recordId`), asks the Gateway's `POST /evaluations` when the gate is on, then reads `GET /records/{recordId}?scope`; the Gateway reads only `GET /records/{recordId}/eligibility?scope`. `adapter/openapi.yaml` is the contract (a record schema and an eligibility schema per scope, by `x-scope`); `wiki/project/issuer-v0.1/contracts.md` section 2 explains it. The Adapter serves values verbatim; the plugin is the only escaper.
- **Adapter** (`adapter/`). The mock, column-driven, reads the CSV on every request and serves the same row for every scope of its Installation; `recordId` is the row's `id`. The record is every column but `id` and the eligibility columns (`holds`, `conferralStatus`, `balance`), and the eligibility path serves those three; on the hackathon roster, which has none of them, both are the whole row but `id`. `python3 adapter/test_adapter.py --contract URL SUB SCOPE` checks any Adapter against the contract.
- **Gateway** (`gateway/`, optional). `POST /evaluations`, the read-only Checklist evaluation (`{sub, scope, recordId}`, reads only the Adapter's `/records/{recordId}/eligibility`); it writes nothing, has no database, and its startup touches nothing external. `credential_types.py` is the registry keyed by scope: each type's credential type, its eligibility model following `adapter/openapi.yaml` strictly, and its checks (a check returns its failure reason, or `None`). An answer that does not parse is a 502 `gateway_error`; a check that raises is a 500. Settings: `installations/<name>/gateway.env`.
- **Data-provider plugin** (`plugin/`, Java 21). `IssuerDataProviderPlugin` lists the token's records at the Adapter (`mosip.certify.adapter.url`, from `CERTIFY_ADAPTER_URL`), asks the Gateway's `POST /evaluations` about the first when `mosip.certify.gateway.enabled=true`, fetches it, escapes it for the quoted template and adds the trace keys `tokenSub` and `tokenClientId` (indexed in the ledger); a refusal is Certify's error (`invalid_access_token`, `no_record`, `adapter_error`, the Gateway's `error`, `gateway_error`). The switch is required: `true` with an `http(s)` Gateway URL and token, `false` with the URL `NO GATEWAY`; anything else throws in the constructor, and the startup log names the setting. Ten keys in each Installation's properties; `contracts.md` section 2a lists them. Compiled against `certify-integration-api:0.14.0` with every dependency `provided`, so the jar is one class; `run-demo.sh` builds it into `vc-stack/plugins/`.
- **Registrar approval.** The Portal shows the claim link only after a registrar approves; Certify and Keycloak know nothing of it, so with the gate off every persona with a record is issuable, and with it on every persona the Checklist passes. A deliberate scope cut: do not "fix" it unless asked.
- **The stack** (`vc-stack/`): one folder per deployment (`issuer/`, `gateway/`, `mock-adapter/`, `verify/`, `demo/`), each `name: vc-stack`, pulled together by `include:`; a no-Gateway form leaves `gateway/` out. Mount sources stay in `vc-stack/`, so folder paths start with `../`. Each group with a database has its own; the Issuer's Postgres holds only Certify's schema. `wiki/architecture/vc-stack.md` has the table.
- **The SIS bridge** (`sis-bridge/`, folder `vc-stack/sis-bridge/`), temporary: serves `/records` for the transcript over the SIS Adapter's current route until the SIS Adapter serves the contract, then it is deleted. It is in no stack file: start it with `docker compose --env-file vc-stack/.env -f vc-stack/sis-bridge/compose.yaml up -d --build`, point `CERTIFY_ADAPTER_URL` at `http://sis-bridge:8000` to use it, and keep `GATEWAY_ADAPTER_URL` on the mock, since it serves no eligibility.
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
- Generated and environment files stay git-ignored: the ait adapter CSV, `installations/<name>/mimoto-issuers-config.json`, `vc-stack/.env`, `vc-stack/certs/`, `vc-stack/data/`, `vc-stack/plugins/`, `plugin/target/`, `.demo-state/*`. No jar is committed.
- `AGENTS.md`, `PLAN.md` and `wiki/log.md` at the root are local-only and git-ignored.

## Docs

`wiki/OVERVIEW.md` is the index: what to read first, then `wiki/reference/` (lookup pages agents and operators use, not reading material). A page named `*.stale.md` with "(stale)" in its title was written by someone else and no longer holds; leave it, do not cite it as current. Retired pages are not kept; OVERVIEW names the commit to recover them from. Add a page only when no existing page can take the content, and list it in OVERVIEW.

## Agent skills

- **Issue tracker**: local Markdown outside this repo; never GitHub Issues. See `docs/agents/issue-tracker.md`.
- **Triage labels**: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`, as a `Status:` line.
- **Domain docs**: one context, `CONTEXT.md`; decisions in `docs/adr/`.
