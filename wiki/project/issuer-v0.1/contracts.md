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

Served in v0.1 by Keycloak (stock image, realm `inji`, our configuration) for the AIT installation, with directory federation on the campus side; by eSignet from Track 2 for the hackathon installation. Authentik is the prime candidate after v0.1.

- Flow: authorization code. Clients: wallets (through Certify's OpenID4VCI endpoints) and the Portal.
- Endpoints the server must expose: `/.well-known/openid-configuration`, `/authorize`, `/token`, `/userinfo`, `/jwks.json` (§3.1).
- ID token `sub`: the AIT student ID (`ait-2026-0001` in the test data). For staff, the employee ID.
- **Proposed:** a `roles` claim carrying `registrar` for OSA officers, so the admin API (section 3) can authorise staff.
- Certify accepts tokens from exactly one issuer (`issuer-uri` and `jwk-set-uri` are single-valued in 0.14), so swapping the Authorization Server is one configuration change per installation, never two servers at once.

## 2. Record data

Two hops. Certify's REST data-provider plugin calls the **Gateway**; the Gateway evaluates the **Checklist** and fetches from the **data adapter**. Decisions are instant: there is no approval queue (Q23 stands: the gate is in the Gateway, the plugin stays generic).

### 2a. Plugin → Gateway (ours)

`GET {gateway}/students/{sub}/transcript` (**proposed** path)

- `sub` is the ID token subject Certify received.
- Auth: a shared secret header on the private network (**proposed** for v0.1; a service credential per source later, see responsibilities.md section 9).
- `200`: every check passed; a JSON object whose keys are the transcript's `credentialSubject` fields.
- `403`: a check failed; body lists the failed checks with reasons. Certify returns an error to the wallet and nothing is issued. The Portal's student side shows the reasons for now (responsibilities.md section 5).
- `404`: no record for this subject.
- **Open:** which degree a wallet-initiated request is for when a student holds more than one. The demo gives each degree its own sign-in identity; whether the real Authorization Server can do the same is undecided.

Plugin configuration (**proposed** keys): URL template, auth header name and value, timeout, and an optional field mapping from response JSON paths to credential fields.

### 2b. Gateway → data adapter (Jo and Boss)

The proposal names `GET /students/:id/transcript` (§5.1(3)). A student can hold more than one degree, and the Checklist needs eligibility attributes, so v0.1 extends it (all **proposed**):

- `GET /students/{id}/degrees` → list of `{ degreeId, level, degreeAwarded, dateGraduation }`.
- `GET /students/{id}/transcript?degreeId={degreeId}` → one degree's full record.
- `GET /students/{id}/eligibility?degreeId={degreeId}` → the attributes the Checklist reads: `holds[]`, `conferralStatus`, `balance`.

Record fields, taken from the test data in `data/students.json`:

| Group | Fields |
|---|---|
| Student | `fullName`, `dateOfBirth`, `country` |
| Degree | `degreeId`, `level`, `registrationNo`, `previousDegree`, `yearAwarded`, `dateAdmitted`, `option`, `degreeAwarded`, `dateGraduation`, `faculty`, `academicProgram`, `areaOfSpecialization`, `notes`, `issueDate` |
| Thesis | `thesisTitle`, `thesisGrade`, `thesisExamination`, `programCommittee` |
| Credits | `courseworkCredits`, `thesisCredits`, `totalCredits` |
| Courses | `courses[]`: `{ term, courses[]: { no, title, ... } }`; ordered arrays, numbers as strings |

Read-only, fetched once per request, not stored by the Issuer (§3.2). Which fields may leave the SIS is OSA's decision; this list is the demo's, not an agreed one. Until the real adapter exists, our CSV-backed mock implements this contract and its eligibility attributes are editable so the Checklist can be exercised.

## 3. Issuer admin API (ours)

The line the Portal and the Track 4 successor integrate against (Q24). **Proposed** in full; the proposal describes the functions (§3.3) but not an API.

Auth: staff ID token from section 1 with the `registrar` role.

| Method and path | Does |
|---|---|
| `GET /credentials?studentId=&name=&school=&program=&status=` | Search issued credentials (a search table joined with Certify's ledger; identifiers only, no credential bodies) |
| `GET /checklists/{credentialType}` | The checks configured for a credential type |
| `POST /checklists/{credentialType}/evaluate` | With `{ studentId, degreeId }`: the result per check, used by the Portal before a hard copy and for debugging |

Two Portal flows go to Certify directly over the internal network rather than through this API, as drawn in responsibilities.md section 2: **revoke** (Certify's status API; the bit flips at the next status-list batch, then the list is published, section 4) and the **hard copy** (after a passing evaluation, the Portal obtains a pre-authorized credential offer, redeems it as an OpenID4VCI client, embeds the credential in the PDF's QR and discards it). Certify's management, ledger-search, status and credential-configuration APIs stay internal (section 6).

## 4. Publishing to the VDR (Jo)

What the Issuer pushes, where, and how often. Our mock publisher implements this and is the specification Jo builds the final publisher against (**proposed** in full).

| Artifact | Published | Path on the VDR |
|---|---|---|
| DID document for `did:web:<host>` | At setup and on key rotation | `/.well-known/did.json` |
| Bitstring Status List (signed by Certify) | On change, within Certify's 60-second batch | `/status/{listId}` |
| JSON-LD contexts (transcript, Student ID) | On publish from the VC Lab | `/contexts/{name}/{version}.json` |
| PDF template and display metadata | On publish from the VC Lab | `/templates/{credentialType}/...` |

Verifiers fetch the DID document, status lists and contexts; only the Portal fetches templates. No personal data is published. Stable public hostnames for these URLs from the first real issuance are the infra team's to provide; Dev and UAT credentials are throwaway because their URLs encode the environment. Registering the Issuer, its DID and its schemas in the trusted-issuer list is a checklist item before the first UAT issuance.

## 5. Credential offer (any wallet)

The Issuer promises a valid OpenID4VCI credential offer and nothing more about the wallet. Credentials follow the verifier conformance profile in responsibilities.md section 6 (VCDM 2.0, JSON-LD, Ed25519Signature2020, Bitstring Status List, `did:web`). Issuance is proven in CI with stock Inji Web and Mimoto, which run only in the local Compose.

## 6. Deployment configuration (infra team)

The handover: two images (Gateway, Portal), the configuration of every stock image (environment variables, mounted files, per-installation settings), and the ingress allowlist. Any change goes to the infra team before it is applied.

| Exposure | Endpoints |
|---|---|
| Public | Certify's OpenID4VCI endpoints, the Authorization Server, the Portal, the Verify UI |
| Internal only | Certify's management, ledger-search, status and credential-configuration APIs (unauthenticated in stock Certify), called by the Gateway and Portal |

Signing-key custody is the infra team's; Certify supports PKCS12 or PKCS#11.
