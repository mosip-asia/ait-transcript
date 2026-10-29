# Issuer v0.1 — interface contracts

Status: accepted by the team on 2026-10-20; first written 2026-10-11, rewritten 2026-10-19 to match the ownership in [`responsibilities.md`](responsibilities.md). Terms follow [`CONTEXT.md`](../../../CONTEXT.md). "Q" numbers refer to the owner's 2026-10-11 scoping plan, kept outside this repository. Every interface the Issuer depends on is served by a mock or stand-in in v0.1; its real owner implements the same contract later.

Paths and field names follow `proposal-issuer.md` (PR 4) where it gives them. Anything the proposal does not give is marked **proposed**.

| # | Contract | Provider | Consumer | v0.1 stand-in |
|---|---|---|---|---|
| 1 | Sign-in (OpenID Connect) | Authorization Server (campus IT; Track 2 for the hackathon) | Certify, Portal, wallets | Keycloak, our realm configuration |
| 2a | Record lookup | Gateway (ours) | Certify's data-provider plugin | — |
| 2b | Data adapter | Jo and Boss | Gateway | CSV-backed mock (ours) |
| 3 | Issuer admin API | Gateway (ours) | Portal; Track 4 successor | — |
| 4 | Publishing | VDR (Jo) | Issuer (Gateway, VC Lab) | Mock VDR publisher (ours), which is also the specification |
| 5 | Credential offer | Certify (ours to configure) | Any OpenID4VCI wallet | Inji Web and Mimoto, in local Compose only |
| 6 | Deployment configuration | Issuer (ours) | Infra team | — |

## 1. Sign-in (OpenID Connect)

Served in v0.1 by Keycloak (stock image, our configuration): realm `inji` for the AIT installation, with directory federation on the campus side; realm `hackathon` for the hackathon installation by default, with eSignet from Track 2 as the swap below if it is delivered in time (decided 2026-10-20). Authentik is the prime candidate after v0.1.

- Flow: authorization code. Clients: wallets (through Certify's OpenID4VCI endpoints) and the Portal, which obtains tokens for Certify too: its student login requests the credential scopes with Certify's audience, because the Portal redeems the hard copy's credential in the student's own session (section 3).
- Every client that obtains tokens for Certify carries a `client_id` claim equal to its client id, because Certify's token filter requires it and the Gateway records the issuing client. Keycloak: a hardcoded-claim protocol mapper per client, as the demo realm already does for the wallet client; eSignet or Authentik must do the same (2026-10-20).
- Endpoints the server must expose: `/.well-known/openid-configuration`, `/authorize`, `/token`, `/userinfo`, `/jwks.json` (§3.1).
- ID token `sub`: the AIT student ID (`ait-2026-0001` in the test data). For staff, the employee ID.
- **Proposed:** a `roles` claim carrying `registrar` for OSA officers, so the admin API (section 3) can authorise staff.
- Certify accepts tokens from exactly one issuer (`issuer-uri` and `jwk-set-uri` are single-valued in 0.14), so swapping the Authorization Server is one configuration change per installation, never two servers at once.

## 2. Record data

Two hops. Certify's REST data-provider plugin calls the **Gateway**; the Gateway evaluates the **Checklist** and fetches from the **data adapter**. Decisions are instant: there is no approval queue (Q23 stands: the gate is in the Gateway, the plugin stays generic).

### 2a. Plugin → Gateway (ours)

Decided 2026-10-20. The plugin is a generic REST client: it knows one URL, one secret, two timeouts and no claim or field names. The Gateway owns the credential-type selection, the checklist and the error vocabulary.

`POST {gateway}/issuances`

- Request body: the access-token claims Certify hands the plugin, as a JSON object, minus `accessTokenHash`. The Gateway requires `sub` (the sign-in subject, one per degree) and `scope` (the credential's scope, for example `ait_transcript_vc_ldp`; the claim may be space-separated and the Gateway matches the scopes it serves inside it) and ignores the rest. `sub` never travels in the path or a header, so it appears in no access log. POST because a `200` writes the search table.
- Auth: `Authorization: Bearer <token>`, a shared secret per installation on the private network (a service credential per source later, see responsibilities.md section 9).
- `200`: every check passed. A flat JSON object whose top-level keys are the credential template's variable names; scalars as strings (numbers as strings), nested JSON allowed, so `courses` is an array. The plugin turns every top-level object or array into its JSON text before handing the object to Certify, which is what the template's unquoted `${courses}` needs; nothing else is mapped. The Gateway never returns Certify's reserved keys `_holderId`, `_issuer`, `id`, `validFrom`, `validUntil`, `credentialStatus`.
- `403`: a check failed. The body is the checklist result, the same object section 3's evaluate endpoint returns: every check listed, `reason` only on a failed one.

  ```json
  { "error": "checklist_failed",
    "credentialType": "AitTranscriptCredential",
    "checks": [
      { "check": "no_holds",     "passed": true },
      { "check": "conferred",    "passed": false, "reason": "Degree not yet conferred" },
      { "check": "zero_balance", "passed": true } ] }
  ```

- `404`: `{ "error": "no_record" }`, no record for this subject.
- `400`: `{ "error": "unknown_scope" }`, no credential type matches the token's scope.
- What the wallet sees: on any non-2xx the plugin throws Certify's `DataProviderExchangeException` with the body's `error` as the code (`gateway_error` when there is no body, on a timeout or a refused connection; `invalid_access_token` when the token has no `sub`). Certify answers the credential request with the OpenID4VCI error body `{ "error": "<code>", "error_description": "<code>" }`, which Inji Web and Mimoto show as a generic failure. Reasons reach the student only through the Portal's student side (responsibilities.md section 5), never through the wallet.
- Which degree: closed by "one identity per degree" in v0.1. A student with two degrees has two sign-in identities, so `sub` names the degree.

Plugin configuration, per installation, the same jar everywhere:

| Key | Value |
|---|---|
| `mosip.certify.integration.data-provider-plugin` | `GatewayDataProviderPlugin` |
| `mosip.certify.integration.scan-base-package` | `asia.mosip.issuer.gateway.plugin` |
| `mosip.certify.gateway.url` | Base URL of the Gateway, for example `http://gateway:8000` |
| `mosip.certify.gateway.auth-token` | The shared secret above |
| `mosip.certify.gateway.connect-timeout-ms` | Default `2000` |
| `mosip.certify.gateway.read-timeout-ms` | Default `10000` |

The jar is one generic artifact built from `gateway/plugin/` against `certify-integration-api:0.14.0` (Java 21, no shaded dependencies) and mounted as a single file into Certify's `additional_jars/`; its delivery to the infra team is part of section 6.

### 2b. Gateway → data adapter (Jo and Boss)

The proposal names `GET /students/:id/transcript` (§5.1(3)). A student can hold more than one degree, and the Checklist needs eligibility attributes, so v0.1 extends it (all **proposed**):

- `GET /students/{id}/degrees` → list of `{ degreeId, level, degreeAwarded, dateGraduation }`.
- `GET /students/{id}/transcript?degreeId={degreeId}` → one degree's full record.
- `GET /students/{id}/eligibility?degreeId={degreeId}` → the attributes the Checklist reads: `holds[]`, `conferralStatus`, `balance` for the transcript; `teamId`, `winner` on the hackathon roster.

Record fields, taken from the test data in `data/students.json`:

| Group | Fields |
|---|---|
| Student | `fullName`, `dateOfBirth`, `country` |
| Degree | `degreeId`, `level`, `registrationNo`, `previousDegree`, `yearAwarded`, `dateAdmitted`, `option`, `degreeAwarded`, `dateGraduation`, `faculty`, `academicProgram`, `areaOfSpecialization`, `notes`, `issueDate` |
| Thesis | `thesisTitle`, `thesisGrade`, `thesisExamination`, `programCommittee` |
| Credits | `courseworkCredits`, `thesisCredits`, `totalCredits` |
| Courses | `courses[]`: `{ term, courses[]: { no, title, ... } }`; ordered arrays, numbers as strings |

The hackathon installation's roster (`installations/hackathon/adapter/student_identity_data.csv`, one row per participant) serves the same three paths: `degrees` returns `{ degreeId }` only, and the record and the eligibility paths both serve the whole row.

| Group | Fields |
|---|---|
| Eligibility | `teamId`, `winner` |
| Developer Passport | `teamId`, `teamName`, `oidcClientId`, `authEndpoint`, `issuerEndpoint`, `verifierEndpoint` |
| Achievement | `teamId`, `award` |

Values the implementation fixed, which the real adapter must keep:

- `conferralStatus` is `Conferred` or `Pending`.
- `balance` is a decimal string such as `"1250.00"` (`"0.00"` when nothing is owed), never a number.
- `teamId` is empty for a participant on the roster without a team.
- `winner` is `true` for a member of a winning team (read case-insensitively); anything else, empty included, is not.
- `degreeId` equals the row's `id`. v0.1 holds one degree per `sub`, so `degrees` returns one entry and a `degreeId` that differs from the `sub` finds no record.

Read-only, fetched once per request, not stored by the Issuer (§3.2). Which fields may leave the SIS is OSA's decision; this list is the demo's, not an agreed one. Until the real adapter exists, our CSV-backed mock implements this contract and its eligibility attributes are editable so the Checklist can be exercised.

#### The student key under campus sign-in

Proposed on 2026-10-29. The AIT installation signs students in through the campus realm `ait-dev`, as "Campus sign-in" in [`spec-part-2.md`](spec-part-2.md) describes. The Gateway sends the token's `sub` to the adapter as `{id}`. It URL-encodes `sub`, changes nothing else, and reads no other claim. Campus IT decides what `sub` holds, and the adapter must handle either choice.

- **(a) The username in `sub`.** Campus writes the AIT username into `sub` for the Issuer's clients. The username is the student's registration number, so the adapter looks the student up by registration number. Keycloak lowercases usernames, so `{id}` arrives as `st123456`. Match it without regard to case.
- **(b) Campus's own `sub`.** Campus keeps `sub` as its Keycloak user id. The adapter reads that user from the campus realm, takes the username, which is the registration number, and looks the student up. Campus IT will say how the adapter may read users, for example through a service account. Campus asks consumers not to store its `sub` during the PoC, so the adapter keeps `{id}` out of its storage and its access logs.

Either way:

- For an `{id}` it cannot resolve, the adapter answers `404` or returns an empty `degrees` list. The Gateway turns both into `no_record`, and the wallet shows a failure.
- The Gateway takes the first entry of `degrees` and passes its `degreeId` back unchanged, so the adapter chooses the `degreeId` format.
- A campus account belongs to one person, not one degree. How the Gateway chooses between two degrees is still open, under "Multi-degree students" in `spec-part-2.md`. Until that is decided, return one degree per `{id}`.

## 3. Issuer admin API (ours)

The line the Portal and the Track 4 successor integrate against (Q24). **Proposed** in full; the proposal describes the functions (§3.3) but not an API.

Auth: staff ID token from section 1 with the `registrar` role.

| Method and path | Does |
|---|---|
| `GET /credentials?studentId=&name=&school=&program=&status=` | Search issued credentials (a search table joined with Certify's ledger; identifiers only, no credential bodies) |
| `GET /checklists/{credentialType}` | The checks configured for a credential type |
| `POST /checklists/{credentialType}/evaluate` | With `{ studentId, degreeId }`: the result per check, used by the Portal before a hard copy and for debugging |

Two Portal flows go to Certify directly over the internal network rather than through this API, as drawn in responsibilities.md section 2: **revoke** (Certify's status API; the bit flips at the next status-list batch, then the list is published, section 4) and the **hard copy** (decided 2026-10-20: the Portal, as an OpenID4VCI client in the student's own session, calls Certify's `/issuance/credential` with that session's access token and a proof JWT signed with one Portal-held key per installation; Certify takes the plugin path, so the Gateway runs the checklist and writes the search row as for any wallet claim; the Portal embeds the credential in the PDF's QR and discards it. No pre-authorized offer, and no evaluate call before it: a `403` checklist result is the student's result page). Certify's management, ledger-search, status and credential-configuration APIs stay internal (section 6).

## 4. Publishing to the VDR (Jo)

What the Issuer pushes, where, and how often. Our mock publisher implements this and is the specification Jo builds the final publisher against (**proposed** in full).

| Artifact | Published | Path on the VDR |
|---|---|---|
| DID document for `did:web:<host>` | At setup and on key rotation | `/.well-known/did.json` |
| Bitstring Status List (signed by Certify) | On change, within Certify's 60-second batch | `/status/{listId}` |
| JSON-LD context (transcript; `/contexts/transcript/v1.json` in v0.1, no Student ID) | On publish from the VC Lab | `/contexts/{name}/{version}.json` |
| PDF template and display metadata | On publish from the VC Lab | `/templates/{credentialType}/...` |

Verifiers fetch the DID document, status lists and contexts; only the Portal fetches templates. No personal data is published. Stable public hostnames for these URLs from the first real issuance are the infra team's to provide; Dev and UAT credentials are throwaway because their URLs encode the environment. Registering the Issuer, its DID and its schemas in the trusted-issuer list is a checklist item before the first UAT issuance.

## 5. Credential offer (any wallet)

The Issuer promises a valid OpenID4VCI credential offer and nothing more about the wallet. Credentials follow the verifier conformance profile in responsibilities.md section 6 (VCDM 2.0, JSON-LD, Ed25519Signature2020, Bitstring Status List, `did:web`). Issuance is proven in CI with stock Inji Web and Mimoto, which run only in the local Compose.

## 6. Deployment configuration (infra team)

The handover: the images we build (Gateway, mock adapter, Portal), the plugin jar, the configuration of every stock image (environment variables, mounted files, per-installation settings), and the ingress allowlist. The full contract, with both installations' values, is [`configuration-contract.md`](configuration-contract.md). An installation is a self-contained stack described by one directory, `installations/<name>/`; Certify is listed once per instance, since a 0.14 instance serves one token issuer and one data-provider plugin and an installation may need more than one (2026-10-20). Any change goes to the infra team before it is applied.

| Exposure | Endpoints |
|---|---|
| Public | Certify's OpenID4VCI endpoints, the Authorization Server, the Portal, the Verify UI, the `vdr` container's `/contexts/` path |
| Internal only | Certify's management, ledger-search, status and credential-configuration APIs (unauthenticated in stock Certify), called by the Gateway and Portal; the Gateway, the adapter, Postgres |

Signing-key custody is the infra team's; Certify supports PKCS12 or PKCS#11. One pod per Certify instance with `spring.cache.type=simple`, or Redis if infra scales it (2026-10-20).
