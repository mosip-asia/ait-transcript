# Issuer v0.1 — part 2 spec

Status: draft of 2026-10-26, written from the closed build decisions and the code on `feat/hackathon-chain`; not yet reviewed by the owner. Terms follow [`CONTEXT.md`](../../../CONTEXT.md). Ownership is in [`responsibilities.md`](responsibilities.md), the interfaces in [`contracts.md`](contracts.md), the departures from the proposal in [`deviations.md`](deviations.md), the deployment in [`configuration-contract.md`](configuration-contract.md). The first part of v0.1 is the [hackathon chain spec](spec-hackathon-chain.md); this page builds on what that part built and does not restate it.

Part 2 is the rest of v0.1: campus sign-in for the AIT installation, the admin API, the mock VDR publisher with published status lists, the VC Lab publish step, the Portal's staff and student sides, the hard copy, and the end-to-end test that closes v0.1. All of it is ours under `responsibilities.md` section 2. The pilot's environment, users and data are out of this page's scope; the Portal's student side, the PDF template and the hard copy are what the pilot runs on.

Milestones that bound it:

| Milestone | Date | Meaning |
|---|---|---|
| Hackathon chain deadline | 2026-12-18 | Part 1 deployed by infra; part 2 must not delay it, so part 2 lands on `main` only after part 1 does |
| v0.1 target | 2027-01-15 | Everything on this page accepted and tagged |
| v0.1 pessimistic | about 2027-03-08 | Every task at its long end |
| Pilot | set by the pilot-date decision | Needs the student side, the PDF template and the hard copy deployed |

## Problem Statement

Part 1 put the gate in the right place: a credential is issued only when the Gateway's checklist passes at the moment Certify asks. Everything around that gate is still the demo. The Portal signs people in with a persona picker, not the Authorization Server; it still runs the approve and reject queue the decisions removed; staff can find a student's credentials only by the exact registration number Certify's ledger search accepts; a student refused by the checklist sees a generic wallet error and never learns why. Nothing produces a hard copy the pilot's students can hand to someone. The status list is served by Certify itself, contexts reach the VDR container through a bind mount, and credential templates live as base64 inside seed SQL that only a database wipe can change. None of this matches the contracts the team accepted, and the publishing contract that Jo is to build against does not exist as running code.

## Solution

The AIT installation's students and staff sign in through the campus realm, which Certify trusts directly. The Issuer stays generic: it keys records on the standard `sub`, and the campus side (their realm or their adapter) makes that `sub` resolve to the student's record. The Gateway gains the admin API of `contracts.md` section 3: staff search over the issuance records it already writes, joined with Certify's ledger, plus the checklist listing and evaluation, behind a staff token from the Authorization Server. The `vdr` container becomes the mock VDR publisher of section 4: a small receiver that accepts `PUT` per artifact and serves what it received, so contexts, templates and the Bitstring status lists all reach the VDR through one HTTP API that Jo can build the real publisher against. The Gateway pushes each status list there when Certify re-signs it. The issuer stays `did:key` in v0.1 (decided 2026-10-28). VC Lab becomes files plus one publish step that sends contexts, templates and display metadata to the VDR and the credential configurations to Certify's configuration API, so a template change no longer needs a wipe. The Portal signs students and staff in through the installation's realm, loses the approval queue, and gives staff search, revoke and the checklist, and students their checklist result, a credential offer for any wallet, and a hard copy: the Portal redeems the credential at Certify as the student's wallet, encodes it with PixelPass into a QR on a PDF drawn from the VC Lab template, and keeps nothing. An end-to-end smoke proves request, claim, verify, revoke and verify-again for every credential type in both installations, and v0.1 is tagged.

## User Stories

1. As a registrar, I want to sign in to the Portal with my staff account, so that only staff can search and revoke.
2. As a registrar, I want to find a student's credentials by student ID, by part of a name, by school or by program, so that I do not need the exact registration number.
3. As a registrar, I want each found credential to show its type, when it was issued, whether it went to a wallet or into a hard copy, and whether it is revoked, so that I can answer a student or a verifier.
4. As a registrar, I want to revoke one credential from the search result, so that a wrongly issued or withdrawn credential stops verifying.
5. As a registrar, I want to see whether a revoked credential's status has reached verifiers yet, so that I can tell a caller when it takes effect.
6. As a registrar, I want to see the checks configured for a credential type and evaluate them for one student, so that I can tell a student what is blocking them.
7. As a hackathon organiser, I want the same staff side for my installation, so that I can revoke a participant's credential without asking a developer.
8. As a student, I want to sign in to the Portal with the account I use for the wallet, so that the Portal knows which record is mine without a picker.
9. As a student, I want to see, before I claim, whether I am eligible and, if not, which check failed and why, so that I know what to resolve.
10. As a student, I want a credential offer I can scan or open with any OpenID4VCI wallet, so that my wallet choice is mine.
11. As a student, I want to download a PDF of my credential with a QR code, so that I can hand my transcript to someone who has no wallet.
12. As a student who is not eligible, I want the PDF download refused with the same reasons the page shows, so that the paper never says more than the record allows.
13. As a verifier with only the paper, I want to scan the QR in the Verify UI and get the same verdict as for the wallet credential, so that the hard copy is as trustworthy as the wallet.
14. As a verifier, I want a revoked credential to fail verification within a few minutes, whether it is held in a wallet or printed on paper, so that revocation means something for both.
15. As a verifier, I want the issuer's key carried in its identifier (`did:key`) in v0.1, so that I can check a signature with no network call to the Issuer.
16. As a verifier, I want the status list fetched from the VDR, so that the Issuer's internal services are never on my verification path.
17. As Jo, building the real VDR publisher, I want a running mock that accepts exactly the `PUT` requests the Issuer sends, with the paths, headers and bodies of `contracts.md` section 4, so that my publisher is a drop-in replacement.
18. As the Issuer owner, I want a credential template, its display metadata or a context changed by editing a file and running the publish step, so that a change no longer needs a database wipe and a new signing key.
19. As the Issuer owner, I want the hackathon rows' context URLs set to the deployed hosts by the same publish step, so that the deploy-time rewrite gap is closed.
20. As the Issuer owner, I want the admin API in the Gateway and the Gateway's database access limited to what it reads and writes, so that it no longer connects as the superuser.
21. As the Issuer owner, I want the Portal to store no credential and no token beyond the signed-in session, so that a Portal breach exposes no credential.
22. As the Issuer owner, I want the Portal's Python PixelPass encoder proven against the reference decoder the Verify UI uses, so that a QR we print always scans.
23. As the Issuer owner, I want the largest transcript among the personas measured against the QR's capacity before the PDF is built around it, so that the second-highest risk in v0.1 is known early.
24. As the Issuer owner, I want one smoke script to run the whole journey for every credential type in both installations, so that v0.1 is accepted by observation, not assertion.
25. As a member of the infra team, I want the configuration contract updated in the same change as each new service, secret, mount or public path, so that the handover never lags the code.
26. As a member of the infra team, I want the publisher's write side internal and its read side public, stated in the allowlist, so that only the Issuer can publish.
27. As a reviewer, I want each piece accepted by a check I can run, so that "done" is observed.

## Implementation Decisions

### What already exists and is kept

- The Gateway's `POST /issuances`, its checklist registry in `gateway/credential_types.py` and the `gateway.issuances` table (identifiers only). Part 2 adds columns and endpoints; it does not change the plugin's contract (section 2a).
- The scripted issuance `vc-stack/issue_and_verify.py`: a token from the realm's `smoke` client, an ES256 `did:jwk` proof, Certify's `/issuance/credential`. The Portal's hard copy makes the same call with the student's token and the Portal's key.
- The `vdr` container (stock nginx, `vc-lab/contexts/` under `/contexts/`). It is replaced by the publisher below; its public read paths stay as they are.
- `portal/certify_client.py`'s ledger search, status-list decode and revoke call. The revoke call stays in the Portal (section 3: revoke goes from the Portal to Certify's status API directly); the search moves behind the admin API.

### Campus sign-in (AIT installation)

Decided 2026-10-28: the AIT installation's Authorization Server is the campus realm run by campus IT (`ait-dev` at `https://oauth-dev.ait-itserv.dpi.ait.ac.th/realms/ait-dev` for Dev, Keycloak over the AIT directory), as `contracts.md` section 1 already names campus IT as the provider. Certify trusts that one issuer directly (its single `issuer-uri` and `jwk-set-uri`); there is no brokering through a realm of ours and no user store of ours. Our realm `inji` stays the stand-in for local runs and CI, where the smoke's direct-access grant cannot run against directory accounts.

What the campus realm gives today, from the adapter team's collection and its discovery document: tokens signed RS256, `sub` an internal Keycloak id that consumers are asked not to store during the PoC, the AIT username (`st123456` form) in `preferred_username`, names and e-mail, a 5-minute access token and a 30-minute idle session; clients `demo-public` (PKCE) and `demo-rp` (client credentials); none of the Issuer's scopes or clients.

Behaviour:

- **The record key is `sub`, unchanged** (decided 2026-10-28). The Issuer is the generic side: it reads only the standard `sub`, which OIDC makes unique and never reassigned within an issuer, and never a provider-specific claim such as `preferred_username`, which OIDC says a client must not rely on being unique. The site adapts. Campus chooses one of two ways to make their `sub` resolve to a student record: **(a)** their realm writes the student ID into `sub` in tokens for the Issuer's clients (a mapper, as the stand-in realm's `sub-from-username` does), and they own testing that override on their Keycloak 26.8, including UserInfo and introspection; or **(b)** their adapter accepts their own `sub` and looks the student up, which keeps `sub`'s standard meaning but means the Issuer stores their `sub` in `gateway.issuances` unless that column is replaced (see Further Notes). The Gateway, the plugin, the stand-in realms and `contracts.md` sections 1 and 2b stay as they are; section 1's "`sub` is the student ID" is read as "`sub` is a key the adapter resolves".
- **Per-environment issuer.** The Authorization Server's issuer, JWKS URL, token endpoint and client ids are settings of the installation per environment, read by Certify, Mimoto's issuer entry and the Portal; no file names `/realms/inji` directly.
- **What the campus realm must provide** (the obligations of `contracts.md` section 1, asked of campus IT): the client scope `ait_transcript_vc_ldp` with an audience mapper naming Certify's credential endpoint; a hardcoded `client_id` claim on each client; a `c_nonce` claim in tokens of that scope, because Certify 0.14 refuses a proof whose token has none (a fixed value, as the stand-in realm writes, recorded as debt); their choice between (a) and (b) above; a confidential client for Mimoto authenticating with `private_key_jwt` against Mimoto's public key, with the Inji Web and mobile-wallet redirect URIs; a confidential client for the Portal; later, a realm role `registrar` held by OSA staff, which Keycloak's `roles` scope carries in `realm_access.roles`; and the pilot users on the consent list.
- **Multi-degree students.** A campus account is one per person, so "one identity per degree" ends for the AIT installation. How the Gateway picks a degree, or whether the pilot excludes multi-degree students, is an open decision for the Issuer, whichever way `sub` resolves; until it is taken, the mock adapter holds one degree per `sub`.
- The hackathon installation keeps its own realm.

Accepted when:

- Locally and on CI, both installations still pass `smoke.sh` once the Authorization Server is a per-environment setting.
- On Dev, once campus IT has provided the items above: the demo account signs in on the campus login page from Inji Web, claims a transcript served by a mock-adapter row keyed by the `sub` its token carries, and the credential verifies; Certify's logs show the campus issuer.

### Admin API (Gateway)

The three endpoints of `contracts.md` section 3, served by the Gateway under the same FastAPI app as `POST /issuances`, on the internal network only. The Portal is its only caller in v0.1.

Auth:

- Each request carries the signed-in user's access token from the installation's Authorization Server as a bearer token. The Gateway validates it against the server's JWKS (fetched on first use and cached, never at startup) and its issuer, and accepts only tokens whose `azp` is the Portal's client, so no audience mapper is needed on any realm.
- Staff: the token's `realm_access.roles` contains `registrar`, which Keycloak's default `roles` scope writes, so the only realm change is the role itself. Every stand-in realm gains the realm role `registrar`; on the campus realm the role is asked of campus IT. The AIT realm gets the mock registrars of `data/students.json` as users with the role; the hackathon realm gets one organiser user with it. One role name for both installations in v0.1.
- Student self-evaluation: open (see Further Notes). Until it is decided every endpoint is staff only, as section 3 says; the proposal was that evaluate also accepts a student's token for the student's own `sub`.
- No token, a bad signature, the wrong issuer, or an `azp` other than the Portal's client: 401. A valid token without the role on a staff endpoint: 403.

`GET /checklists/{credentialType}`: the type's checks from the registry, in order, with a one-line description each. 404 for a type the installation does not serve.

`POST /checklists/{credentialType}/evaluate` with `{ studentId, degreeId }`: runs the same code path as `POST /issuances` up to the checklist (adapter fetch, every check evaluated) and returns the checklist result object of section 2a (`credentialType`, `checks` with `passed` and `reason` on failures) with 200 whether it passes or not. It writes no issuance row. 404 `no_record` for an unknown subject. `degreeId` defaults to `studentId`, since v0.1 has one degree per `sub`.

`GET /credentials?studentId=&name=&school=&program=&credentialType=&clientId=&status=`: issued credentials, newest first, identifiers only.

- The search reads `gateway.issuances` joined with Certify's ledger in the same Postgres. The join key is an issuance reference: at 200 the Gateway writes the row with a fresh UUID `issuance_ref` and also returns it to Certify as one extra template variable `issuanceRef`; each installation's Certify properties index it (`mosip.certify.indexed-mappings.issuanceRef=$.issuanceRef`), and no template renders it, so it never appears in a credential. The plugin contract is unchanged: `issuanceRef` is a string and passes through.
- This rests on Certify 0.14 evaluating `indexed-mappings` over the data-provider's map, not over the rendered credential. The task opens by observing it: issue one transcript and read the ledger row's indexed attributes. If the mapping reads the rendered credential, the fallback is to join on each type's existing indexed claim and issue order (transcript `registrationNo`; hackathon `teamId`), which cannot tell two members of one team apart; the task then stops and the owner chooses between that and rendering `issuanceRef` into the credential.
- At 200 the row also stores the type's search fields copied from the record it just returned: the transcript's `fullName`, `faculty` (school) and `academicProgram` (program); the hackathon types' `teamId` and `teamName`. The registry names them per type. `name` matches case-insensitively as a substring; the other filters match exactly.
- Each result carries `sub`, `credentialType`, `clientId` (the Portal's client for a hard copy, the wallet's otherwise), `issuedAt`, the search fields, and from the ledger `credentialId`, `statusListCredentialUrl`, `statusListIndex`, `statusPurpose`. A row with no ledger match (Certify failed after the Gateway answered) is returned with status `unconfirmed`.
- `status` is `active`, `revoked` or `unconfirmed`. `revoked` means the bit is set in the status list as last signed by Certify, decoded as `certify_client._bitstring_bit` does today, so a revoke shows as revoked only once verifiers can see it.
- The Gateway's database access becomes a role limited to the `gateway` schema (read and write) and `SELECT` on Certify's ledger table; the superuser credentials leave `gateway.env`. The role is created by Certify's init SQL.

Accepted when:

- The ledger row of an issued transcript carries `issuanceRef`, observed, or the fallback has been chosen by the owner.
- Over HTTP against the stack: a registrar token finds a transcript by student ID, by a partial name in another case, by school and by program, and the hackathon organiser finds a Developer Passport by team; every result has the fields above; a revoked credential shows `revoked` after the next batch and `active` before it.
- 401 without a token, with a token from the other installation's realm, and with a token whose `azp` is not the Portal's client; 403 for a student token on every endpoint until the student path is decided.
- The Gateway connects with the limited role, and a write outside the `gateway` schema fails.
- Plain Python tests cover these cases, in the repository's style, against the stack and in-process with the adapter and a faked store.

### Mock VDR publisher

The `vdr` service becomes the mock publisher of `contracts.md` section 4 and the specification Jo builds against (decision "VDR publisher is an API"): a small Python receiver behind the same nginx. The directory `vdr/` holds it.

Behaviour:

- `PUT {vdr}/{path}` with `Authorization: Bearer <publisher token>` writes the body to that path in a volume and answers 201 on create, 204 on replace. The accepted paths are exactly the four families of section 4: `/.well-known/did.json`, `/status/{listId}`, `/contexts/{name}/{version}.json`, `/templates/{credentialType}/{file}`. Anything else is 404; a missing or wrong token is 401; a body that is not JSON where JSON is required is 400.
- `GET` on the same paths is served by nginx from the volume, publicly, with `Content-Type: application/json` (or `application/ld+json` for contexts, the type of the file for templates) and CORS open for `GET`, as verifiers in a browser need it. The `PUT` side is reachable only on the internal network: the public gateway forwards `GET` and `HEAD` and refuses other methods.
- No personal data is accepted by construction: nothing on the Issuer publishes credentials or records.
- The receiver keeps no state beyond the files; restarting it changes nothing. A `GET` of a path never published is 404.
- `vc-lab/contexts/` stops being bind-mounted; the contexts reach the VDR through the publish step (`vc-lab/publish.py`), which this task introduces with contexts only and the VC Lab task extends. Until that step has run after a wipe, the contexts are absent, so `bootstrap.sh` runs it before its validation.

Accepted when:

- `PUT` then `GET` round-trips for each path family, 401 without the token, 404 outside the families, and a `PUT` through the public gateway is refused.
- A short page `wiki/architecture/vdr-publisher.md` states the API as the specification for Jo: paths, methods, auth, status codes, content types, who publishes what and when. Handed to Jo with the end-to-end flows (contact C5).

### Issuer identifier: `did:key` in v0.1

Decided 2026-10-28: v0.1 issues under the `did:key` it has today, refreshed by `bootstrap.sh` after a wipe. A wipe therefore changes the issuer identifier as well as the key, which v0.1 accepts (no compatibility promise through v0.1). `did:web` on the VDR stays the conformance profile's target after v0.1 and is recorded as a deviation. The publisher keeps the `/.well-known/did.json` path family in its specification for Jo; v0.1 publishes nothing there. No task in this part changes the identifier.

### Status lists on the VDR

Certify keeps signing the Bitstring status list on its batch; the Gateway publishes each signed list to the VDR's `/status/{listId}`, and credentials point verifiers there.

Behaviour:

- A loop in the Gateway (started after startup, never blocking it) polls each status list Certify holds, every 10 seconds, and `PUT`s a list to the VDR when its signed body differs from the last one published. The list ids come from Certify's `status_list_credential` table through the Gateway's read access (the admin API's limited role gains `SELECT` on it; whichever of the two tasks lands second makes the grant). A failed `PUT` is retried on the next tick and logged.
- The credential's `statusListCredential` is built by Certify from `mosip.certify.domain.url`, which also names the OpenID4VCI issuer. The task opens by reading Certify 0.14's `StatusListCredentialService` for a property that sets the status-list base independently. If one exists, it names `{vdr}/status/`. If not, the fallback keeps the URL Certify writes and has the public gateway serve `/v1/certify/credentials/status-list/{id}` from the VDR's published copy instead of from Certify, so verifiers still never reach Certify for status; `contracts.md` section 4's path becomes an alias in that case.
- The smoke's `skipStatusChecks` goes: verification now includes the status check.

Accepted when:

- After a revoke, the list at the URL inside the credential shows the bit set within Certify's batch interval plus one poll, and `verify-service` reports the credential revoked; before the revoke it reports `SUCCESS` with status checks on.
- Stopping the Gateway stops publishing but not issuance or verification of what was already published.

### VC Lab: authored files and the publish step

VC Lab is files plus one publish step (`deviations.md` row 15). Today each credential configuration, its Velocity template and display metadata included, is an `INSERT` in the installation's `certify_seed.sql`, which runs only on a fresh database.

Behaviour:

- Per credential type, under `vc-lab/<type>/`: the JSON-LD credential template (the Velocity template now in the seed, as plain text), the display metadata (issuer name, logo URL, colours, claim labels), and the PDF template (see the hard copy). The contexts stay at `vc-lab/contexts/<name>/v1.json`. Each installation's directory lists which types it publishes and its public base URLs; nothing per installation lives under `vc-lab/`.
- `vc-lab/publish.py <installation>`, extended from the publisher task's contexts-only version: `PUT`s every context, every PDF template and the display metadata to the VDR; then creates or updates each credential configuration through Certify's credential-configuration API (internal), with the context and template URLs set to the installation's public base. It is idempotent: a second run with no file change changes nothing.
- `certify_seed.sql` keeps the schema and anything the configuration API cannot set; the credential configurations leave it. This closes the hackathon rows' deploy-time context rewrite gap, since the publish step writes the deployed URLs.
- `bootstrap.sh` runs the publish step after Certify answers and before validation; the configuration contract lists it as a deployment step with the publisher token and Certify's internal URL.
- The task opens by observing Certify 0.14's credential-configuration API against the local stack: creating the transcript configuration through it yields the same issuer metadata and the same issued `credentialSubject` as the seed row does today, and an update takes effect within `mosip.certify.common.cache-expire-seconds` without a restart. If the API cannot carry a field the seed sets, that field stays in the seed and the gap is recorded.

Accepted when:

- On a wiped stack, the publish step alone produces the issuer metadata both installations have today (compared field by field), and `smoke.sh` passes.
- Changing a display label in `vc-lab/` and re-running the publish step changes Certify's issuer metadata without a wipe or restart.

### Portal: sign-in, rename, queue removed

The Portal becomes an OpenID Connect confidential client of the installation's realm, for students and staff. The persona picker and the approval queue go.

Behaviour:

- Authorization-code flow with PKCE against the installation's Authorization Server for the environment (the campus realm on Dev for AIT, the stand-in realm locally; no hard-coded `inji`). One client, `portal`, in every realm, asked of campus IT for the campus realm: the credential scopes of the installation as optional client scopes, Certify's audience, the hardcoded `client_id` claim mapper (section 1), the `roles` scope for `realm_access.roles`, and redirect URIs limited to the Portal's own.
- One login page; after sign-in the Portal shows the staff side when the token carries `registrar`, the student side otherwise. Logout ends the Portal session and the realm session.
- Sessions are server-side: the access, refresh and ID tokens live in the Portal's SQLite keyed by an opaque cookie, never in the cookie. The Portal stores nothing else per user. One Portal replica per installation in v0.1, stated in the configuration contract.
- `portal/requests.py`, the request state machine, the approve, reject and reissue routes and their templates are removed; `db.py` keeps only sessions. The Compose service is renamed `portal`.

Accepted when:

- A mock student and a mock registrar each sign in through Keycloak and land on their side, in both installations; logout returns to the login page and a back-button visit is signed out.
- No route, template, table or test of the approval queue remains; the Portal's tests cover sign-in, side selection and logout.

### Portal: staff side

Behaviour:

- Search form over `GET /credentials` (student ID, name, school, program, type, wallet or hard copy, status), results as a table with the fields of the admin API.
- Revoke per result: the Portal calls Certify's status API as `certify_client.revoke_credential` does today, with the ledger fields the search returned, then shows "revoked; verifiers see it within about a minute" until a later search shows `revoked`. `unconfirmed` and already revoked rows offer no revoke.
- A student page: the checks of each type with the evaluation for that student, from the two checklist endpoints.

Accepted when:

- A registrar finds a credential by each filter, revokes it, and sees it `revoked` after the batch; `verify-service` then reports it revoked.
- The organiser does the same in the hackathon installation.

### Portal: student side

Behaviour:

- For each credential type the installation serves (read from Certify's issuer metadata), the student's checklist result from `POST /checklists/{type}/evaluate` with the student's own token: eligible, or the failed checks with reasons (decision "Student page shows reasons for now").
- When eligible: a credential offer for any OpenID4VCI wallet (section 5), by value, with `credential_issuer`, the type's configuration id and the `authorization_code` grant, shown as a QR and an `openid-credential-offer://` link; and the PDF download (the hard copy).
- The result reflects the record at the time of the page; the gate stays at issuance. A student who becomes ineligible between page and claim is refused by the plugin path as before.

Accepted when:

- Each failing persona sees exactly the failed checks and reasons `POST /issuances` refuses with; an eligible persona sees the offer and the download.
- The offer validates against the OpenID4VCI credential offer schema and its configuration id is in Certify's issuer metadata; a wallet claims from it once by hand (Inji Mobile, or the wallet team's), recorded.

### Hard copy: redemption and QR

The Portal is the hard copy's wallet (decision of 2026-10-20, `deviations.md` row 20).

Behaviour:

- On download, the Portal takes the session's access token (refreshing it if expired), signs a proof JWT with the installation's Portal key (ES256, `did:jwk`, `iss` the Portal's client id, Certify's `c_nonce` flow as `issue_and_verify.py` does), and calls Certify's `/issuance/credential` for the type's configuration. The plugin path runs the checklist and writes the issuance row with the Portal's `client_id`. A `checklist_failed` answer shows the student side's reasons page; any other error shows a retry page and is logged.
- PixelPass in Python inside the Portal: the credential JSON encoded as CBOR, compressed with zlib at level 9, Base45-encoded. The QR is drawn in alphanumeric mode at a module size of at least 4 px at the printed size, error correction level L unless capacity allows more.
- The credential is held in memory for the request and discarded after the PDF is built. The Portal key is one key pair per installation, a secret in the configuration contract.
- The task opens by measuring: the encoded length of the largest transcript among the personas (the most courses) against version 40's alphanumeric capacity at level L (4296 characters). If any persona's transcript does not fit, the task stops and the owner decides between a larger record limit, a second QR, or changes to the claim set; this is the second-highest risk in v0.1.

Accepted when:

- The encoder's output decodes back to the identical credential with the reference decoder the Verify UI uses (`@injistack/pixelpass`, run in a Node container in CI), for every persona's credential.
- The capacity measurement is recorded in the PR with the largest persona's length.
- A hard copy request writes one issuance row with the Portal's `client_id`, and the admin API shows it as a hard copy.

### Hard copy: PDF from the VC Lab template

Behaviour:

- The PDF template is an HTML file with CSS per credential type under `vc-lab/<type>/pdf/`, rendered by the Portal with Jinja2 and WeasyPrint. The transcript gets its own template (header, student and degree block, the course table drawn from `courses`, the totals, the QR, the issuer and issue date); the hackathon types share one generic template that draws the display metadata and the claims as a table.
- The Portal fetches the template from the VDR's `/templates/{credentialType}/...` (the only reader of templates, section 4) and caches it for the process lifetime; a missing template is an error page, not a PDF without one.
- The PDF is generated per request and streamed; nothing is written to disk.

Accepted when:

- The largest persona's transcript renders on as many pages as it needs without overflowing (the Mimoto `courseList` overflow does not recur).
- CI renders a hard copy per credential type, rasterises the page with the QR, decodes the QR with a QR decoder, PixelPass-decodes it with the reference decoder, and `verify-service` answers `SUCCESS`; after a revoke, the same printed QR verifies as revoked.
- The QR on one printed transcript scans in the Verify UI by hand, recorded with the date.

### End-to-end test and v0.1 close

Behaviour:

- `smoke.sh` runs the whole journey for every credential type in the installation's `smoke.json`: an eligible persona claims by the scripted wallet and by the Portal's hard copy; both verify; a registrar token finds both through the admin API and revokes one of each; after the batch and one publish both verify as revoked; a refused persona is refused on both paths with the same checks. The same script runs for both installations in CI.
- `wiki/project/issuer-v0.1/flows.md` (the `ISSUER_E2E_FLOWS.md` of `responsibilities.md` section 3) draws each flow as built: wallet claim, hard copy, staff search and revoke, publishing; with the VDR publisher page it goes to Jo (contact C5).
- `contracts.md`, `deviations.md` and `configuration-contract.md` are updated to what was built; `CONTEXT.md` gains any term the build introduced.
- v0.1 is tagged on `main`.

Accepted when the CI smoke passes for both installations on the tagged commit, the documents above match the code (the configuration-contract check passes), and the tag exists.

## Testing Decisions

The same three seams as part 1, highest first, each observing behaviour over HTTP and never reaching into a container:

- **The Compose stack, end to end** (`vc-stack/smoke.sh`). Every acceptance above that involves Certify, Keycloak, the VDR or `verify-service` runs here. New prior art in part 2: tokens for staff and students from the realms' `smoke` client with the direct-access grant, as `issue_and_verify.py` already does for students.
- **The Gateway's HTTP API**, including the admin API, as plain Python scripts in the repository's style (`test_*.py`, no pytest), in-process with the mock adapter and a faked store, and against the stack. Tokens are signed by a test key whose JWKS the test serves. Prior art: `gateway/tests/test_issuances.py`.
- **The Portal over HTTP**, with the Gateway and Certify faked at their HTTP boundary for the logic (side selection, revoke button states, reasons page), and against the stack for sign-in and the hard copy. Prior art: `portal/test_auth.py`, `portal/test_requests.py` (the latter removed with the queue).
- **The PixelPass encoder** against the reference decoder in a Node container, the one test that crosses a language boundary on purpose.
- **The publisher** over HTTP, `PUT` and `GET` per path family.

Browser sign-in itself (the Keycloak login page) is not automated in v0.1; the smoke uses the direct-access grant, and the browser flow is checked by hand once per installation and recorded, as the Inji Web claim was in part 1.

## Out of Scope

- The pilot: its date, environment, users and real data (the pilot decisions on the map). This page builds what the pilot needs.
- Staff-triggered printing and pre-authorized offers (a second hard-copy-only Certify, only if OSA asks).
- A Verify UI listing of the hackathon types, unless the owner decides it is wanted.
- `did:web`: v0.1 keeps `did:key` (decided 2026-10-28).
- The real VDR host and publisher (Jo), the real adapter (Jo and Boss), campus directory federation, deployment itself, a container registry choice.
- Contract tests for the three external contracts, unless their ownership lands with us.
- A checklist file format or editor, a card rendering template, SD-JWT, selective disclosure.
- Masking the student side's reasons, which is expected later.

## Further Notes

Points the decisions left to this spec, settled here and open to change when the build issues are reviewed:

- **Campus sign-in comes first** (2026-10-28): it is the pilot's sign-in and its asks to campus IT take the longest, so the campus sign-in tasks lead the order below.
- **The Issuer is the generic side** (2026-10-28): where a site's identity or data differs from the contracts, the site adapts (its realm or its adapter), and the Issuer gains no per-site claim, setting or code path. This is why the record key stays `sub`.
- **If campus picks (b)**, `gateway.issuances` would hold their internal `sub`, against their PoC request. Then either they accept it, or the column is replaced by an identifier taken from the record the adapter returns (for the transcript, `registrationNo`), a small change that is not site-specific.

- **Student self-evaluation would change `contracts.md` section 3.** Section 3 makes evaluate staff-only and the hard-copy decision says the Portal does not evaluate before a hard copy. But the plugin path gives the wallet and the Portal only the error code (`checklist_failed`), never the checks, so the student side cannot show reasons without evaluating. Open as map ticket 15 (options: the student's token on evaluate for their own `sub`, a separate student endpoint keyed only by the token, a Portal service credential, or no reasons in v0.1; and whether to evaluate up front or after a refusal). Whatever is chosen, the gate stays at issuance and nothing is evaluated as a precondition.
- **The `issuanceRef` join** adds one variable to the Gateway's 200 and one indexed mapping per installation. It changes no credential and no plugin code; it rests on the opening observation in the admin API task.
- **Status-list URL**: either a Certify property or the public-gateway alias; the admin API task does not depend on which.
- **`did:key` in v0.1** (decided 2026-10-28): `deviations.md` row 21 records it against the conformance profile's `did:web`.
- **Staff tokens** (revised 2026-10-28 to need nothing beyond Keycloak's defaults on the campus realm): the role `registrar` in `realm_access.roles`, and the Portal's client as `azp`, in both installations; the hackathon organiser holds `registrar`.
- **Which campus realm**: `ait` on the campus VM is NetBird-only over plain HTTP, which Certify on GCP and students' browsers cannot reach; `ait-dev` is public over HTTPS. Dev uses `ait-dev`; the pilot's realm is asked of campus IT.
- **PDF stack**: HTML templates with Jinja2 and WeasyPrint, chosen because the templates stay editable by non-developers and the Portal is already Jinja2; QR by a Python library with explicit alphanumeric mode.
- **The publish step** is a script run by `bootstrap.sh` and listed as a deployment step, not a service; it is the only writer of contexts, templates and credential configurations. The Gateway's status-list loop is the only other writer to the VDR.
- Each task updates `configuration-contract.md` in the same change as its Compose change, so `vc-stack/test_configuration_contract.py` keeps passing; new secrets: the publisher token, the Portal's client secret and proof key, the Gateway's limited database role.

Tech debt this part closes: smoke verifies with `skipStatusChecks`; the Compose service named `demo-app`; the Gateway connecting as the superuser; `portal/requests.py` hard-coding realm `inji`; the hackathon context URLs needing a deploy-time rewrite.

For `/to-tickets` (reordered 2026-10-28 toward the pilot): campus sign-in's per-environment settings first and its Dev switch as soon as campus IT delivers; the pilot path after it is the admin API's auth, Portal sign-in, the student side, the hard copy's redemption and PDF, then search and the staff side; the publisher, status lists and the VC Lab publish step follow off the pilot path. The original edges: the admin API's auth and checklist endpoints first, its search after them; the publisher (with the contexts-only publish step) first on its own branch of the graph, then status lists and the VC Lab publish step against it, in parallel; Portal sign-in after the admin API's auth (it needs the realm's role and client), then the staff side after the search and the student side after sign-in; the hard copy's redemption and QR after the student side, its PDF after that and the publish step; the end-to-end smoke last but one, after status lists, the staff side and the PDF; the v0.1 close last.
