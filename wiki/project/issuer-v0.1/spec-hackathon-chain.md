# Issuer platform v0.1 — hackathon chain spec

Status: draft of 2026-10-20, written from the closed build decisions; not yet split into build issues. Terms follow [`CONTEXT.md`](../../../CONTEXT.md). Ownership is in [`responsibilities.md`](responsibilities.md), the interfaces in [`contracts.md`](contracts.md), the departures from the proposal in [`deviations.md`](deviations.md). This page says what the hackathon chain is, how each piece behaves and how it is accepted; the build issues that come out of it say the same per ticket.

The hackathon chain is the part of v0.1 that must be deployed by the infra team before the holidays: the mock adapter and the checklist runner, the REST data-provider plugin for Certify, the context fix, the hackathon configurations, and the configuration contract to infra. Everything else in v0.1 (admin API, VC Lab publish step, Portal, mock VDR publisher, hard copy, pilot) comes after and is out of this page's scope.

Milestones that bound it:

| Milestone | Date | Meaning |
|---|---|---|
| Plugin go/no-go | 2026-11-13 | One transcript issued end to end through the Gateway by the REST plugin, or v0.1 falls back to the Postgres data-provider plugin fed by the Gateway |
| Handover to infra | 2026-11-20 | Configuration contract delivered; stable public hostnames and signing-key custody asked |
| Hackathon chain deadline | 2026-12-18 | Both installations deployed by infra; the only hard date in v0.1 |
| Hackathon dry run | 2026-12-31 | Run by the hackathon organiser, not by Thas; needs the chain deployed |

## Problem Statement

The running demo issues one credential type from one Certify whose data-provider plugin reads a CSV, approval is enforced only in the demo app's UI, the course claims are not covered by the issuer signature because of how the JSON-LD context is scoped, and the hackathon's two credential types live in a frozen repository on VCDM 1.1 behind a Node issuance page and policy service. None of this can be handed to the infra team as a product: there is no gate at the credential endpoint, no second installation, no versioned context, no description of what to deploy.

The hackathon needs a working Issuer platform that issues Developer Passport and Achievement credentials to participants who sign in, pass a roster check and claim into any OpenID4VCI wallet, deployed by the infra team by 2026-12-18 for a dry run on 2026-12-31. AIT needs the same Issuer platform, configured for the transcript, so that one codebase serves both.

## Solution

One Issuer platform, two installations that differ only in configuration. A wallet signs the participant or student in through the Authorization Server and asks Certify for a credential; Certify's data-provider plugin, a thin Java REST client, posts the token's claims to the Gateway; the Gateway picks the credential type from the token's scope, fetches the record and its eligibility attributes from the data adapter (a CSV-backed mock in v0.1), evaluates the credential type's checklist, and returns the claims to sign or refuses with a checklist result; Certify signs a VCDM 2.0 credential with a status-list entry and hands it to the wallet. The transcript's JSON-LD context is fixed so every claim is signed, served from a versioned URL on a static mock VDR. The hackathon's two types are rows in the hackathon installation's Certify, on the same chain, with a roster CSV in the same mock adapter and a Keycloak realm of their own. A configuration contract tells the infra team what to deploy for each installation.

## User Stories

1. As a hackathon participant, I want to sign in with the account the organiser gave me and claim a Developer Passport into my wallet, so that I can prove I am a registered participant on a team.
2. As a hackathon participant on a winning team, I want to claim an Achievement credential, so that I can prove my team's award.
3. As a hackathon participant who is registered but not placed on a team, I want my Developer Passport request refused rather than issued empty, so that credentials always mean what they say.
4. As a hackathon participant on a team that did not win, I want my Achievement request refused, so that an Achievement is only ever held by a winner.
5. As a hackathon participant, I want to claim with any OpenID4VCI-conformant wallet, so that I am not tied to one wallet product.
6. As a hackathon organiser, I want to decide who is on the roster, which team they are on and who won by editing one CSV, so that no code change is needed between registration, team formation and the awards.
7. As a hackathon organiser, I want a participant's eligibility to be decided the moment they ask, so that there is no approval queue to staff during the event.
8. As a hackathon organiser, I want the credentials my participants hold to carry a revocation entry, so that a wrongly issued credential can be revoked later.
9. As a hackathon organiser, I want one issuer identity and one issuer display for both credential types, so that participants see one organiser, not two.
10. As a hackathon organiser, I want participants to sign in through a Keycloak realm Thas runs, so that the dry run does not depend on another track's sign-in server being ready.
11. As a wallet developer, I want the hackathon Certify's issuer metadata to list exactly the two credential types with their scopes and display metadata, so that my wallet can render the offer without special cases.
12. As a wallet developer, I want a refused request to come back as a standard OpenID4VCI error body, so that my wallet shows a failure instead of hanging or crashing.
13. As a verifier operator, I want to verify a Developer Passport, an Achievement or a transcript with a stock JSON-LD 1.1 verifier by fetching the context, the status list and the issuer's DID document from public URLs, so that I never have to ask the Issuer.
14. As a verifier operator, I want a tampered grade inside the transcript's course list to fail verification, so that the signature covers every claim and not only the envelope.
15. As a verifier operator, I want a tampered top-level claim such as the holder's name to fail verification, so that the whole credential is covered.
16. As a verifier operator, I want the transcript context to be served at a versioned URL, so that a later context change does not silently alter what an older credential means.
17. As an AIT student, I want my transcript request refused with reasons when I have a hold, an unconferred degree or an outstanding balance, so that I know what to resolve.
18. As an AIT student with two degrees, I want each degree to issue under its own sign-in identity, so that there is never a question of which degree I am claiming.
19. As an AIT student, I want to claim my transcript into any OpenID4VCI wallet, so that my choice of wallet is mine.
20. As the Issuer platform owner, I want the checks for each credential type to be code in the Gateway, so that the hackathon's roster predicates and AIT's eligibility predicates ship without a checklist file format.
21. As the Issuer platform owner, I want the data-provider plugin to know one URL, one secret and two timeouts and nothing about claims, so that every business rule lives in the Gateway and the plugin never changes between installations.
22. As the Issuer platform owner, I want the Gateway to own the error vocabulary, so that the plugin never learns a new error code.
23. As the Issuer platform owner, I want the Gateway to record every issuance at the moment the plugin call succeeds, so that the admin API's search can be built on it later without re-deriving anything from Certify's ledger.
24. As the Issuer platform owner, I want one `docker-compose.yaml` and one `installations/<name>/` directory per installation, so that the service set is identical and only files differ.
25. As the Issuer platform owner, I want to run either installation locally by setting one variable, so that I can test the hackathon and AIT stacks on the same machine, one at a time.
26. As the Issuer platform owner, I want the context fix to open with the six-step Compose check, so that the signing and verifying paths are observed to handle a JSON literal before the context is relied on.
27. As the Issuer platform owner, I want the swap from the CSV mock to a real data adapter to be a configuration change, so that the real adapter can arrive without a code change in the Gateway.
28. As the Issuer platform owner, I want the swap from the Keycloak realm to eSignet to be one configuration change per installation, so that the hackathon can take eSignet if it arrives in time.
29. As the Issuer platform owner, I want the plugin jar built in CI and by the local bring-up script, so that no jar is ever committed.
30. As the Issuer platform owner, I want `smoke.sh` to prove each installation issues and verifies every credential type it serves and refuses the cases it must refuse, so that a regression is caught before the infra team deploys.
31. As the Issuer platform owner, I want the go/no-go on the plugin decided by one transcript issued end to end through the Gateway by 2026-11-13, so that the fallback is taken in time if the plugin path fails.
32. As the Issuer platform owner, I want the repository's directories named by the glossary, so that a reader of `CONTEXT.md` finds `gateway/`, `portal/` and `vc-lab/` where the terms say.
33. As a member of the infra team, I want one document that lists every image, environment variable, mounted file, per-installation setting and public endpoint, so that I can deploy an installation without reading the code.
34. As a member of the infra team, I want Certify listed once per instance per installation, so that an installation with more than one Certify later is a repetition of a known block.
35. As a member of the infra team, I want the ingress allowlist stated as configuration, so that Certify's unauthenticated internal APIs are never exposed by accident.
36. As a member of the infra team, I want to know how the plugin jar reaches me, so that I can mount it as the contract says.
37. As a member of the infra team, I want the contract to say which secrets exist and where each is read, so that I can provision them without guessing.
38. As a member of the infra team, I want the request for stable public hostnames and signing-key custody stated with the handover, so that I can plan them before the dry run.
39. As the data adapter's future owner, I want the mock adapter to speak the contract I will implement, including the eligibility attributes, so that my adapter is a drop-in replacement.
40. As a reviewer of the build, I want each component to have a stated acceptance check I can run, so that "done" is observed and not asserted.

## Implementation Decisions

### Directory layout

Directories are named by `CONTEXT.md` terms. The first build pull request renames the demo app and adds the Gateway; paths in `vc-stack/`, the Dockerfile and `CLAUDE.md` move with it.

| Directory | Holds | Chain |
|---|---|---|
| `portal/` | The FastAPI application, today `app/`, renamed in the first build pull request. Its behaviour does not change in this chain | Rename only |
| `gateway/` | The Python Gateway (FastAPI): checklist runner, record mapping, the issuance record; later the admin API and the mock VDR publisher | Built |
| `gateway/plugin/` | The Maven project of the Certify data-provider plugin, one generic jar | Built |
| `adapter/` | The CSV-backed mock data adapter, its own container, implementing `contracts.md` section 2b | Built |
| `vdr/` | The static mock VDR: an nginx container serving the JSON-LD contexts under `/contexts/`; the `PUT` receiver, the DID document and the status-list push are later tasks | Built (static part) |
| `vc-lab/` | The authored credential artifacts. In this chain: `vc-lab/contexts/transcript/v1.json`, `vc-lab/contexts/developer-passport/v1.json`, `vc-lab/contexts/achievement/v1.json`. Templates, display metadata and the publish step join it in the VC Lab task | Contexts only |
| `installations/ait/` | The AIT installation: Certify properties and `credential_config` rows, Keycloak realm `inji`, the generated adapter CSV (git-ignored), Gateway settings, wallet test-harness configuration (Mimoto issuers), the ingress allowlist | Built |
| `installations/hackathon/` | The hackathon installation: the same set of files for Developer Passport and Achievement, Keycloak realm `hackathon`, a committed mock roster CSV | Built |
| `vc-stack/` | The one `docker-compose.yaml`, `bootstrap.sh`, `smoke.sh`, the shared nginx configurations and seed SQL that do not differ per installation; `vc-stack/plugins/` is the git-ignored build output of the plugin jar | Changed |
| `data/` | The mock personas (`students.json`) and the generators, unchanged in place; the generated CSV moves to `installations/ait/adapter/` | Changed |

Each `installations/<name>/` directory carries a short `README.md` naming its files and the values that are the installation's own (realm, scopes, credential types, adapter CSV, Gateway token name). The prose that explains the files to the infra team is the configuration contract (below), one page for both installations.

### Compose changes

- One `docker-compose.yaml`, no profiles, no second file. An `INSTALLATION` variable in `vc-stack/.env` names the directory under `installations/` that every per-installation mount and `env_file` reads from. Locally one installation runs at a time; `./run-demo.sh` and `bootstrap.sh` take the variable and refuse to start when it names no directory.
- New services: `gateway` (Thas's image, built from `gateway/`), `adapter` (Thas's image, built from `adapter/`, bind-mounting the installation's CSV), `vdr` (stock nginx, serving `vc-lab/contexts/` read-only under `/contexts/`). All three join `vc_stack_network`; `gateway` also reaches Certify's Postgres.
- Certify: the plugin jar is mounted as a single file into `/home/mosip/additional_jars/`, never as a directory, so the four jars bundled in `inji-certify-with-plugins:0.14.0` stay visible. The per-installation properties file replaces today's `certify-csvdp-student.properties` and selects `GatewayDataProviderPlugin` with the four `mosip.certify.gateway.*` keys of `contracts.md` section 2a. Certify's seed SQL (the `credential_config` rows) comes from the installation directory.
- Keycloak: the realm file comes from the installation directory (`inji` for AIT, `hackathon` for the hackathon). The hardcoded `client_id` protocol mapper the demo realm already carries for the wallet client is kept in both realms, as `contracts.md` section 1 requires of every client that obtains tokens for Certify.
- Public gateway (nginx): routes `/contexts/` to the `vdr` container. The `/academic-transcript-context.json` and `/student-context.json` locations go, with the `certify-nginx` static context route and `vc-stack/config/academic-transcript-context.json`.
- Mimoto and Inji Web stay as the wallet test harness, in the local Compose only; the Mimoto issuer list is rendered from the installation's template so each installation's Certify is the one issuer it shows.
- `run-demo.sh` builds the plugin jar through a Maven container into `vc-stack/plugins/` before bringing the stack up, then runs `bootstrap.sh` as today. `smoke.sh` takes the installation from the same variable.
- The demo's approval queue (the demo app's `pending`/`approved` state deciding whether a claim link is shown) stops being the gate: the gate is the Gateway. Removing the queue from the Portal is the Portal task, not this chain; in this chain the Portal is renamed and keeps working against the renamed paths.

### Mock adapter

A separate container, read-only, speaking `contracts.md` section 2b over HTTP. The real adapter replaces it by changing the Gateway's adapter URL.

Behaviour:

- Serves the three proposed paths of section 2b: the degree list, one degree's record, and the eligibility attributes for a degree. Both installations use the same image; the CSV differs.
- The record is the CSV row keyed by the identity column, which is the sign-in `sub`. One row per sign-in identity, so the degree list has exactly one entry per `sub` and its `degreeId` is the row's `id`; there is no degree selection in v0.1 ("one identity per degree").
- The eligibility endpoint returns the row's eligibility columns. For the AIT CSV these are `holds` (a list), `conferralStatus` and `balance`, as section 2b names them. For the roster CSV they are the roster columns the Gateway's hackathon predicates read (`teamId`, `winner`).
- The AIT CSV is generated from `data/students.json` as today, which gains an eligibility block per degree so that the mock personas include at least one student failing each of the three transcript checks. `courseTableHtml` leaves the generator and the CSV.
- The roster CSV is committed under `installations/hackathon/adapter/` with fictitious participants: at least one on a winning team, one on a team that did not win, and one registered but not on any team.
- The CSV is read at startup and on each request from the mounted file, so editing the file and restarting the container is the whole procedure for changing eligibility; no Certify restart is needed, which is the point of moving the CSV out of Certify.
- A missing row is a 404; nothing else is an error.

Accepted when:

- Each of the three paths answers for a known `sub` in both installations with the body shape of section 2b, and 404 for an unknown one.
- The adapter contract, with the eligibility attributes, is handed to the data adapter's future owners once this mock exercises it (contact C4 in the plan; not blocking).

### Gateway: checklist runner

A Python (FastAPI) service. In this chain it serves one endpoint, `POST /issuances`, exactly as `contracts.md` section 2a specifies; the admin API and the mock VDR publisher are later tasks in the same service.

Behaviour:

- Authenticates the plugin by the shared bearer token of section 2a; any other token is 401.
- Requires `sub` and `scope` in the body and ignores every other claim. Matches the scopes the installation serves inside a space-separated `scope`; no match is 400 `unknown_scope`.
- Credential types are code: a registry of three types (transcript, Developer Passport, Achievement), each naming its scope, its credential type, its check set and its mapping from the adapter's record to the template's variable names. The installation's settings list which scopes are enabled; nothing else differs between installations.
- Fetches the degree list, the record and the eligibility attributes from the adapter for the `sub`; no record is 404 `no_record`.
- Evaluates the type's checks in order over the eligibility attributes, every check always evaluated so the result lists all of them. Transcript: `no_holds` (empty `holds`), `conferred` (`conferralStatus` is conferred), `zero_balance` (`balance` is zero). Developer Passport: `on_roster` (`teamId` non-empty). Achievement: `on_roster`, then `winner` (`winner` true). A failed check is a 403 with the checklist result body of section 2a: `error`, `credentialType`, and every check with `passed`, plus `reason` on the failed ones.
- On success returns a flat object whose keys are the template's variable names, scalars as strings, nested JSON allowed. Transcript: the record's fields, `courses` as the array, and `courseList` derived from `courses` as the one-line summary a wallet card shows; `courseTableHtml` is never returned. Developer Passport: `teamId`, `teamName`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`, straight from the roster columns. Achievement: `teamId`, `award`. Never Certify's reserved keys (`_holderId`, `_issuer`, `id`, `validFrom`, `validUntil`, `credentialStatus`).
- At the moment it answers 200 it writes the issuance record: a `gateway` schema in Certify's Postgres with a row of identifiers only (`sub`, credential type, scope, the token's `client_id`, a timestamp); no credential body. The search and revoke endpoints over it are the admin API task.
- Owns the error vocabulary: `checklist_failed`, `no_record`, `unknown_scope`, and nothing else in this chain. Never calls the adapter at startup, so Certify and the Gateway start in any order.

Accepted when:

- Over HTTP, with the mock adapter: 200 with the full claim set for an eligible `sub` of each enabled type; 403 with every check listed and a reason on the failed one for each failing persona; 404 for an unknown `sub`; 400 for a scope the installation does not serve; 401 without the token.
- The 200 body for the transcript persona, after the plugin's stringify rule, is exactly what today's CSV row gives the template, minus `courseTableHtml`.
- One row appears in the `gateway` schema per 200 and none per refusal.

### Certify data-provider plugin

A Java 21 Maven project in `gateway/plugin/`, compiled against `certify-integration-api:0.14.0`, every Certify-provided library `provided`, no shaded dependencies. Bean `GatewayDataProviderPlugin` in package `asia.mosip.issuer.gateway.plugin`, selected by `mosip.certify.integration.data-provider-plugin`, with `mosip.certify.integration.scan-base-package` pointing at the package. One generic jar for both installations. The loading mechanics are in [`certify-data-provider-plugin.md`](../../research/certify-data-provider-plugin.md).

Behaviour:

- `fetchData` posts the claims map Certify hands it, minus `accessTokenHash`, to `{url}/issuances` with `Authorization: Bearer <auth-token>`, on its own HTTP client with the two configured timeouts (defaults 2000 ms connect, 10000 ms read). A token without `sub` is `invalid_access_token` before any call, the only code the plugin owns.
- On 200 it applies one rule: every top-level value that is an object or array becomes its JSON text, then the object goes back to Certify. No field mapping, no claim names.
- On any non-2xx it throws `DataProviderExchangeException` with the body's `error` string as the code, or `gateway_error` when there is no body, the JSON is malformed, the connection is refused or times out.
- No work at startup; Certify starts whether or not the Gateway is up.
- Configuration is the six keys of `contracts.md` section 2a and nothing else.

Accepted when:

- The jar built by CI and by `run-demo.sh` loads into `inji-certify-with-plugins:0.14.0` from the single-file mount: Certify starts with no missing-bean or duplicate-bean error and its logs show the plugin selected.
- Go/no-go, by 2026-11-13: one transcript is issued end to end through the Gateway in the AIT installation (sign-in, token, credential request, plugin call, 200, signed credential) and verifies in the Verifier. A refused persona gives the wallet the OpenID4VCI error body with `checklist_failed` as the code. If this is not reached, v0.1 takes the Postgres data-provider plugin fed by the Gateway, and the tickets after this one adjust.
- The issued transcript's `credentialSubject` equals the one today's CSV plugin produces for the same persona, minus `courseTableHtml`; the diff is part of the acceptance.

### Context fix (option 1a)

The transcript context's claim terms move to the top level and `courses` becomes a JSON literal, so every claim is covered by the signature. Why and what the processors do is in [`signing-coverage.md`](../../research/signing-coverage.md) and [`certify-json-literal.md`](../../research/certify-json-literal.md).

Behaviour:

- The task opens with the six-step Compose check of `certify-json-literal.md` section 4 (library versions inside the running images; the fixed context served; one transcript issued; verified by `verify-service`; a tampered grade and a tampered `fullName` both rejected; optionally the single `rdf:JSON` quad inspected). Steps 4 and 5 passing is the gate; if either fails, the fallback is option 1b (the ten inner course terms defined), at the same URL.
- Context content: the proposed context in `wiki/schemas/academic-transcript-context.proposed.json` minus `courseTableHtml` and minus the `xsd:date` typings. One rule: every claim is an untyped string, except `courses`, typed `@json`. `courseList` stays. The inner `id` and `type` mappings disappear with the lift and come from the base context. The vocabulary IRI stays the placeholder `https://ait.example/transcript#` until the context moves onto the real VDR host.
- Numbers are strings everywhere, inside `courses` (`lec`, `lab`, `credits`, `gpa`, `cumGpa`) and in the three totals. No datatype on anything.
- Source file `vc-lab/contexts/transcript/v1.json`, served at `{vdr}/contexts/transcript/v1.json` by the `vdr` container. The Certify template's `@context` and the `credential_config` row's `context` column name that URL from day one; they must agree exactly. `vc-stack/config/academic-transcript-context.json`, the `certify-nginx` route and `proposed.json` are removed in the same change so the context lives in one place.
- `courseTableHtml` is removed everywhere: context, Certify template, CSV columns, display metadata, `smoke.sh`, the concept page.
- The credential schema becomes v2 in `wiki/schemas/` (schema and example), each schema naming the context version it describes. The context series starts at v1. In v0.1, v1 may be edited in place; the promise that every published version stays published starts once a credential must survive a change, after v0.1.
- No Student ID context: the `StudentIDCredential` leftovers (the public gateway's `/student-context.json` location, the Verify UI entry) go when the hackathon configurations land, not with this task.

Accepted when:

- Steps 1 to 5 of the Compose check pass and are recorded as observed, not expected, in `certify-json-literal.md`.
- Schema v2 and example v2 are in `wiki/schemas/`.
- One wiki note on the context records the no-datatype rule, the dropped inner `id` and `type`, the jsonld-java caveat (JSON-LD 1.1 processors only) and the versioning promise, and `wiki/concepts/transcript-credential.md` no longer describes `courseTableHtml`.

### Hackathon configurations

The hackathon installation issues two credential types on the same chain as the transcript: Developer Passport (check: `on_roster`) and Achievement (checks: `on_roster`, `winner`). The inventory of what exists today is in [`hackathon-configurations.md`](../../research/hackathon-configurations.md); its migration table's presentation, anchor and validity rows reduce to the two roster predicates.

Behaviour:

- Two `credential_config` rows in `installations/hackathon/`, migrated to VCDM 2.0: context column and template `@context` both `https://www.w3.org/ns/credentials/v2` plus the type's context on the VDR; `validFrom` and `validUntil` from Certify (`${validFrom}`, `${validUntil}`, with the expiry set by Certify's `vc-expiry-duration`); the dot-notation `credentialStatus` block; `credential_status_purpose` revocation, now live. Scopes `developer_passport_vc_ldp` and `achievement_certificate_vc_ldp`, types `DeveloperPassportCredential` and `AchievementCertificateCredential`, the existing display metadata and colours.
- Claim sets are the existing ones minus the chain terms. Developer Passport: `teamId`, `teamName`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`. Achievement: `teamId`, `award`. Nothing is derived: every value is a roster column the organiser fills. `vpid`, `anchorId` and the per-type validity columns do not exist.
- Contexts `vc-lab/contexts/developer-passport/v1.json` and `vc-lab/contexts/achievement/v1.json`, terms at the top level, every claim an untyped string, served by the `vdr` container like the transcript's.
- Roster CSV, one row per participant keyed by the sign-in `sub`: `id`, `teamId`, `teamName`, `winner`, `award`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint`. The same mock adapter image serves it; a registered participant without a team has an empty `teamId`.
- Keycloak realm `hackathon`: a user per roster row with the row's `id` as username and `sub`; the two client scopes with Certify's audience; a wallet client with the hardcoded `client_id` mapper; the `smoke` test client described under Testing. The authorization server is single-valued per Certify instance, so eSignet is the one-line swap in the Certify properties if Track 2 delivers it; the realm stays the default.
- One DID and one issuer display for the installation, as the transcript installation has. The `did:key` refreshed at bring-up stays in this chain; `did:web` arrives with the mock VDR publisher task.
- The Mimoto issuer template for the installation lists the hackathon Certify with both types, so Inji Web shows both tiles in the local test harness.
- The frozen `ait-vc` repository is read, never changed.

Accepted when:

- `INSTALLATION=hackathon ./run-demo.sh` brings the stack up and `smoke.sh` passes: Certify's issuer metadata lists exactly the two configurations with their claims and the realm's issuer; realm usernames match the roster's `id` column; one Developer Passport and one Achievement are issued for the winning participant and both verify in `verify-service`; the Developer Passport issues and the Achievement is refused (`winner` false) for the non-winning team member; the Developer Passport is refused (`on_roster` false) for the participant without a team; a tampered claim in each type fails verification.
- `INSTALLATION=ait ./run-demo.sh` and `smoke.sh` still pass with the same script.
- The `StudentIDCredential` leftovers are gone.
- A short note at the top of `hackathon-configurations.md` records that the Issuer platform carries the two types on roster predicates.

### Configuration contract to infra

`contracts.md` section 6 names the handover; this page says what the document must list. It is one page, `wiki/project/issuer-v0.1/configuration-contract.md`, with `installations/<name>/` holding the values. Any later change goes to the infra team before it is applied.

It must list:

- The service set of an installation, identical for both: Certify (listed once per instance; one instance per installation in this chain) with its nginx, Postgres, Gateway, adapter, `vdr`, Keycloak with its nginx, Verifier service and UI, Portal, public gateway. Mimoto and Inji Web are marked local test harness, not deployed.
- Every image and tag: the stock ones pinned as today, and the two Thas builds (Gateway, Portal), with where CI publishes them.
- The plugin jar: that it is one generic artifact, how infra receives it (the proposed default is a CI artifact of the tagged commit), and that it is mounted as a single file at Certify's `additional_jars/` path, never as a directory.
- Per service, the environment variables and the mounted files, with which come from `installations/<name>/` and which are the same everywhere; for Certify, the per-instance properties file, the seed SQL, the keystore mount and the audience and issuer settings that name the Authorization Server.
- Per-installation settings as a table with the two columns `ait` and `hackathon`: realm, scopes, credential types, adapter CSV, enabled Gateway types, Mimoto issuer template (local only).
- Every secret and where it is read: the Gateway's shared bearer token (set in Certify's plugin properties and in the Gateway), the Gateway's database URL to Certify's Postgres (for the `gateway` schema), Certify's keystore password, Keycloak's admin credentials, the Portal's client secret.
- Every URL that is embedded into a credential or fetched by a verifier and therefore needs a stable public hostname: the context URL on the `vdr` container, Certify's status-list URL, the issuer identifier, the Authorization Server's issuer. Dev and UAT credentials are throwaway because these encode the environment.
- The ingress allowlist. Public: Certify's OpenID4VCI endpoints, the Authorization Server, the Portal, the Verify UI, and the `vdr` container's `/contexts/` path (verifiers fetch it). Internal only: Certify's management, ledger-search, status and credential-configuration APIs, the Gateway, the adapter, Postgres.
- Cache and scaling: one pod per Certify instance with simple cache, or Redis if infra scales it.
- Start order and readiness: Keycloak before Certify's token validation, Postgres before Certify and the Gateway, and the nginx proxies restarted after their upstreams recreate (the behaviour `run-demo.sh` already handles).
- The two asks that travel with the handover: stable public hostnames for the URLs above from the first real issuance, and signing-key custody (Certify supports PKCS12 or PKCS#11).
- The `smoke` test client in each realm, marked as a test-only client for infra to disable or remove where it decides.

Accepted when the infra team has the page and both `installations/<name>/` directories and raises no missing item; delivered by 2026-11-20 so that both installations are deployed by 2026-12-18.

## Testing Decisions

Good tests here observe external behaviour over the stack's HTTP surfaces and never reach into a container's internals. Three seams, the highest first:

- **The Compose stack, end to end** (`vc-stack/smoke.sh`, extended). The existing seam and the main one: issuer metadata, realm alignment, CSV alignment, and now one scripted issuance per credential type followed by verification through `verify-service`'s `vc-verification` endpoint, plus the refused cases and the tampering cases. The plugin go/no-go, the context check's steps 3 to 5 and both installations' acceptance all run here. Prior art: `smoke.sh`, `bootstrap.sh --validate`, `test_inji_web_vc_readiness.py --live`.
- **The Gateway's HTTP API** (`POST /issuances`) with the mock adapter beside it, as plain Python scripts in the repository's style (`test_*.py`, no pytest), run against the Compose stack or against the two containers alone. Prior art: `vc-stack/test_context_refresh.py`, which runs against a throwaway container.
- **The adapter's HTTP API** (section 2b), the same way.

The plugin has no seam of its own: it is proven through the first seam (Certify loads it, the credential diff is empty). The Java project carries no test framework in v0.1.

Scripted issuance: `smoke.sh` needs a credential without a browser. A small Python script in `vc-stack/` obtains a token from the installation's realm with the direct-access grant on a `smoke` client for the persona under test and the credential scope, signs a proof JWT with a fresh Ed25519 key as `did:jwk`, calls Certify's `/issuance/credential`, and writes the credential to a file. It is also the pattern the hard-copy task reuses in the Portal. The `smoke` client exists only for this and is listed as such in the configuration contract.

Tampering cases change one value inside `courses` and one top-level claim (transcript), and one claim per hackathon type, and expect `ERR_SIGNATURE_VERIFICATION_FAILED` from `verify-service`.

## Out of Scope

- The Portal's behaviour: the approval queue's removal, the staff side (search, revoke), the student side, and the hard copy. In this chain the Portal is only renamed.
- The admin API (`contracts.md` section 3): search, checklist listing and evaluate. The `gateway` schema is written here; it is read there.
- The VC Lab publish step, templates and display metadata as authored files, and the credential-configuration call to Certify. Templates stay embedded in each installation's seed SQL until that task.
- The mock VDR publisher: the `PUT` receiver, the DID document (`did:web`), the status-list push. The `vdr` container in this chain serves static contexts only.
- The pilot, its environment and its data.
- A checklist file format, multi-source authentication for the Gateway, Authentik.
- A required-presentation check kind, a policy service, the VPID, anchoring or chaining: the hackathon issues on roster predicates. Further hackathon credential types are a credential-configuration change later.
- A Student ID credential.
- eSignet: the swap is one configuration change per installation and is taken only if Track 2 delivers; the mock eSignet in `ait-vc` is not ported.
- The real data adapter, the VDR host, campus directory federation, deployment itself, hostnames and key custody: other owners' work, asked for through the configuration contract.

## Further Notes

Points the decisions left to this spec, settled here and open to change when the build issues are written:

- Directory names `adapter/` and `vdr/` follow the glossary's "Data adapter" and "VDR"; `CONTEXT.md` has no term for the adapter itself, a gap for the glossary.
- The adapter's eligibility endpoint returns the row's eligibility columns, whichever CSV is mounted; the paths of section 2b are unchanged, and the degree list has one entry per `sub`.
- `on_roster` means a non-empty `teamId`; a registered participant without a team is refused, not 404.
- The hackathon claim sets are the existing ones minus `vpid`, `anchorId` and the per-type validity columns; the roster CSV carries the endpoint columns as plain values the organiser fills.
- `courseList` is derived by the Gateway from `courses` so the adapter contract stays data-only.
- The three contexts live under `vc-lab/contexts/<name>/v1.json` and the `vdr` container serves that directory; the installation directories hold the Certify rows that name the URLs.
- The configuration contract is a wiki page with the two installation directories as its values.
- The scripted issuance and the `smoke` client are the test harness for every acceptance check above.

Documents this chain changes when built: `contracts.md` section 6 points at the configuration contract page; `deviations.md` row 16 and the context note record what was observed; `hackathon-configurations.md` gets its top note; `certify-json-literal.md` section 4 moves from expected to observed; `CLAUDE.md` and `wiki/architecture/vc-stack.md` describe the renamed directories, the `INSTALLATION` variable and the three new services. An architecture decision record in `docs/adr/` on "one chain for both installations, no chain in the hackathon" is worth writing when the hackathon configurations land.

For `/to-tickets`: the blocking edges are directory layout and Compose changes first; then the mock adapter and the Gateway together, the plugin and the context fix in parallel against them; the hackathon configurations after the Gateway, the plugin and the context fix; the configuration contract last, after both installations pass `smoke.sh`.
