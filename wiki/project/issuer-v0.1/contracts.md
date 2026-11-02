# Issuer platform v0.1 — interface contracts

Status: accepted by the team on 2026-10-20; first written 2026-10-11, rewritten 2026-10-19 to match the ownership in [`responsibilities.md`](responsibilities.md); section 2 rewritten 2026-11-02 for the Approval gate beside the data path, not yet put to the team. Terms follow [`CONTEXT.md`](../../../CONTEXT.md). "Q" numbers refer to the owner's 2026-10-11 scoping plan, kept outside this repository. Every interface the Issuer platform depends on is served by a mock or stand-in in v0.1; its real owner implements the same contract later.

Paths and field names follow `proposal-issuer.md` (PR 4) where it gives them. Anything the proposal does not give is marked **proposed**.

| # | Contract | Provider | Consumer | v0.1 stand-in |
|---|---|---|---|---|
| 1 | Sign-in (OpenID Connect) | Authorization Server (campus IT; Track 2 for the hackathon) | Certify, Portal, wallets | Keycloak, Thas's realm configuration |
| 2a | Record path and Approval gate | Certify's Data-provider plugin and the Gateway (Thas's) | Certify; the Portal (section 3) | — |
| 2b | Data adapter | Jo and Boss | Data-provider plugin (records), Gateway (eligibility) | CSV-backed mock (Thas's); the temporary SIS bridge |
| 3 | Issuer admin API | Gateway (Thas's) | Portal; Track 4 successor | — |
| 4 | Publishing | VDR (Jo) | Issuer platform (Gateway, VC Lab) | Mock VDR publisher (Thas's), which is also the specification |
| 5 | Credential offer | Certify (Thas's to configure) | Any OpenID4VCI wallet | Inji Web and Mimoto, in local Compose only |
| 6 | Deployment configuration | Issuer platform (Thas's) | Infra team | — |

## 1. Sign-in (OpenID Connect)

Served in v0.1 by Keycloak (stock image, Thas's configuration): realm `inji` for the AIT installation, with directory federation on the campus side; realm `hackathon` for the hackathon installation by default, with eSignet from Track 2 as the swap below if it is delivered in time (decided 2026-10-20). Authentik is the prime candidate after v0.1.

- Flow: authorization code. Clients: wallets (through Certify's OpenID4VCI endpoints) and the Portal, which obtains tokens for Certify too: its student login requests the credential scopes with Certify's audience, because the Portal redeems the hard copy's credential in the student's own session (section 3).
- Every client that obtains tokens for Certify carries a `client_id` claim equal to its client id, because Certify's token filter requires it and the Data-provider plugin records the issuing client in Certify's ledger (`tokenClientId`, section 2a). Keycloak: a hardcoded-claim protocol mapper per client, as the demo realm already does for the wallet client; eSignet or Authentik must do the same (2026-10-20).
- Endpoints the server must expose: `/.well-known/openid-configuration`, `/authorize`, `/token`, `/userinfo`, `/jwks.json` (§3.1).
- ID token `sub`: the AIT student ID (`ait-2026-0001` in the test data). For staff, the employee ID.
- **Proposed:** a `roles` claim carrying `registrar` for OSA officers, so the admin API (section 3) can authorise staff.
- Certify accepts tokens from exactly one issuer (`issuer-uri` and `jwk-set-uri` are single-valued in 0.14), so swapping the Authorization Server is one configuration change per installation, never two servers at once.

## 2. Record data

Rewritten 2026-11-02 ([ADR 0001](../../../docs/adr/0001-approval-gate-beside-the-data-path.md)): it replaces the Gateway's `POST /issuances` and the Adapter's `/students/{id}/...` paths of 2026-10-20. Two hops, both started by Certify's **Data-provider plugin**. It reads the record from the **Adapter** itself. When the installation runs the **Gateway**, the plugin first asks it whether to issue, and the Gateway evaluates the **Checklist** on the Adapter's eligibility attributes. Decisions are instant: there is no approval queue (Q23 stands).

```
Data-provider plugin --GET /records, GET /records/{recordId}--------------------> Adapter
Data-provider plugin --POST /evaluations--> Gateway --GET /records/{recordId}/eligibility--> Adapter
```

### 2a. The Data-provider plugin and the Gateway (Thas's)

The plugin's sequence, `fetchData(claims)`, in order:

1. No `sub`, or an empty one: `invalid_access_token`, before any call.
2. `GET {adapter}/records?sub={sub}&scope={scope}`. A `404` or an empty list is `no_record`. Otherwise the plugin takes the first entry's `recordId`, without choosing.
3. Only with the gate on: `POST {gateway}/evaluations` (below) with `{ sub, scope, recordId }` and the shared bearer secret. Any `2xx` passes. Any other answer throws the body's `error`; no JSON `error`, an unreachable Gateway or one slower than the read timeout is `gateway_error`. The gate fails closed.
4. `GET {adapter}/records/{recordId}?scope={scope}`. A `404` is `no_record`.
5. The record becomes Certify's claims. It must be a JSON object holding none of Certify's reserved keys (`id`, `_holderId`, `_issuer`, `validFrom`, `validUntil`, `credentialStatus`) and neither trace key below. Every top-level string is escaped for Certify's quoted Velocity template (JSON string escaping without the surrounding quotes); every top-level object or array becomes its JSON text, unescaped, which the template's unquoted `${courses}` needs; other values pass unchanged. Then the plugin adds the token's `sub` as `tokenSub` and its `client_id` as `tokenClientId` (left out when the token has none). Each installation indexes both in Certify's ledger, which is the issuance record; no template renders them, so no credential carries them.

`scope` is the token's `scope` claim, passed through unchanged: the plugin maps nothing and knows no claim name. It calls nothing at startup. Which record: closed by "one identity per degree" in v0.1. A student with two degrees has two sign-in identities, so `sub` names the degree and the Adapter lists one record for it.

`POST {gateway}/evaluations`, read-only, with no side effect:

- Request: `Authorization: Bearer <token>`, a shared secret per installation on the private network (a service credential per source later, see responsibilities.md section 9). The body is `{ "sub", "scope", "recordId" }`, three non-empty strings and nothing else. `scope` may hold several space-separated scopes; the first one the Gateway serves picks the credential type. `sub` stays in the body, so it appears in no access log.
- The Gateway calls only `GET {adapter}/records/{recordId}/eligibility?scope={scope}` and evaluates every check of the type, in order.
- `200`: every check passed, `{ "credentialType", "checks": [ { "check", "passed" } ] }`.
- `403`: a check failed. The same object plus `"error": "checklist_failed"`, `reason` only on a failed check:

  ```json
  { "error": "checklist_failed",
    "credentialType": "AitTranscriptCredential",
    "checks": [
      { "check": "no_holds",     "passed": true },
      { "check": "conferred",    "passed": false, "reason": "Degree not yet conferred" },
      { "check": "zero_balance", "passed": true } ] }
  ```

- `400` `{ "error": "invalid_request" }`: the body is not an object of exactly those three keys. `400` `{ "error": "unknown_scope" }`: no scope the Gateway serves. `401`: a wrong secret, with no `error`. `404` `{ "error": "no_record" }`: the eligibility path answered `404`. `502` `{ "error": "gateway_error" }`: the Adapter is unreachable, slower than 3 s, answers another status, or answers eligibility that does not parse. `500` with no body: a check raised, which is a bug.
- The Portal calls the same endpoint (section 3).

**The error vocabulary, by owner.** On a refusal the plugin throws Certify's `DataProviderExchangeException` with the code below. Certify answers the credential request with the OpenID4VCI error body `{ "error": "<code>", "error_description": "<code>" }`, which Inji Web and Mimoto show as a generic failure. Reasons reach the student only through the Portal's student side (responsibilities.md section 5), never through the wallet.

| Code | Owner | When |
|---|---|---|
| `invalid_access_token` | Data-provider plugin | The token has no `sub` |
| `no_record` | Data-provider plugin; the Gateway, forwarded | The Adapter's list is `404` or empty, or the record is `404`; the Gateway's eligibility path is `404` |
| `adapter_error` | Data-provider plugin | The Adapter is unreachable, slower than the read timeout, answers a status other than `200` or `404`, a body that is not the expected JSON shape, or a record holding a reserved or trace key |
| `checklist_failed` | Gateway | A check failed |
| `unknown_scope`, `invalid_request` | Gateway | The scope or the body, as above |
| `gateway_error` | Gateway; the Data-provider plugin | The Adapter failed the Gateway; the Gateway is unreachable, slow, or answers without an `error` |

Plugin configuration, per installation, the same jar everywhere (ten keys):

| Key | Value |
|---|---|
| `mosip.certify.integration.data-provider-plugin` | `IssuerDataProviderPlugin` |
| `mosip.certify.integration.scan-base-package` | `asia.mosip.issuer.plugin` |
| `mosip.certify.adapter.url` | Base URL of the Adapter; each installation reads `CERTIFY_ADAPTER_URL`, falling back to the mock, `http://adapter:8000` |
| `mosip.certify.adapter.connect-timeout-ms` | Default `2000` |
| `mosip.certify.adapter.read-timeout-ms` | Default `10000` |
| `mosip.certify.gateway.enabled` | Required, `true` or `false`, no default: the gate's switch |
| `mosip.certify.gateway.url` | Required. With the gate on, the Gateway's `http(s)` base URL, for example `http://gateway:8000`; with it off, the literal `NO GATEWAY` |
| `mosip.certify.gateway.auth-token` | The shared secret above; read with the gate on only |
| `mosip.certify.gateway.connect-timeout-ms` | Default `2000`; read with the gate on only |
| `mosip.certify.gateway.read-timeout-ms` | Default `10000`; read with the gate on only |

A missing, non-boolean or contradictory switch stops Certify at startup, and Certify's log names the setting: `IssuerDataProviderPlugin selected: gateway.enabled=<true|false>, Gateway <URL or NO GATEWAY>, Adapter <URL>`. Both installations commit the gate on; a run without the Gateway sets `MOSIP_CERTIFY_GATEWAY_ENABLED=false` and `MOSIP_CERTIFY_GATEWAY_URL=NO GATEWAY` in Certify's environment, as the no-Gateway stack forms of [`configuration-contract.md`](configuration-contract.md) do.

The jar is one generic artifact built from `plugin/` against `certify-integration-api:0.14.0` (Java 21, no shaded dependencies) and mounted as a single file into Certify's `additional_jars/`; its delivery to the infra team is part of section 6.

### 2b. The data adapter (Jo and Boss)

The Adapter is where an organisation's records enter the Issuer platform: the Data-provider plugin lists and reads a student's record from it, and the Gateway reads the record's eligibility attributes. Read-only, fetched once per request, never stored by the Issuer (§3.2). The contract is [`adapter/openapi.yaml`](../../../adapter/openapi.yaml), OpenAPI 3.1, which a test holds the mock to: paths, schemas, the values the real Adapter must keep, and what the Issuer does with each answer. Which fields may leave the SIS is OSA's decision. Until the real Adapter exists, Thas's CSV-backed mock implements it for both installations.

```
GET /records?sub={sub}&scope={scope}               [ { recordId, ...summary } ]   read by the plugin
GET /records/{recordId}?scope={scope}              the record                     read by the plugin
GET /records/{recordId}/eligibility?scope={scope}  what the Checklist reads       read by the Gateway
```

- `scope` is the token's `scope` claim, unchanged; the Adapter (or its configuration) decides what a scope means, and each answer follows the schema whose `x-scope` the scope names. `recordId` is in the Adapter's own format and comes back unchanged.
- **The record schemas**, one per scope: `TranscriptRecord` (`ait_transcript_vc_ldp`), `PassportRecord` (`developer_passport_vc_ldp`), `AchievementRecord` (`achievement_certificate_vc_ldp`). Each requires exactly the claims its Certify template substitutes, the transcript's `courseList` included as a plain string. Every claim is a string, numbers included, except `courses`: terms of `{ term, courses: [ { no, title, credits, grade } ] }`. A record may carry more fields, which the plugin passes on unrendered. `RecordKey` names the keys no record may carry: Certify's reserved keys and the plugin's trace keys (section 2a).
- **The eligibility schemas**, one per scope: `TranscriptEligibility` (`holds`, `conferralStatus`, `balance`), `PassportEligibility` (`teamId`), `AchievementEligibility` (`teamId`, `winner`). The Gateway's eligibility models must keep matching them; `adapter/test_adapter.py` checks it.
- A `404` means no such student or record; its body is not read. Any other answer that is not as the contract types it is `adapter_error` from the plugin and `gateway_error` from the Gateway, never an empty claim.
- No secret on either hop: NetBird membership is the boundary to the SIS Adapter. The Adapter keeps `sub` out of its storage and access logs.
- `python3 adapter/test_adapter.py --contract URL SUB SCOPE` checks any Adapter against the contract: the list, its first record against the scope's record schema, and a `404` or an empty list for an unknown `sub`. Thas runs it by hand against the SIS Adapter over NetBird; it is not in CI.

**The SIS bridge is temporary.** Until the SIS Adapter serves these paths, `sis-bridge/` (Compose folder `vc-stack/sis-bridge/`, in no stack file) serves `GET /records` and `GET /records/{recordId}` for the transcript over the SIS Adapter's current transcript route, with every mapping rule in `sis-bridge/sis_mapping.py`. It serves no eligibility, so the plugin's `CERTIFY_ADAPTER_URL` may name it while the Gateway's `GATEWAY_ADAPTER_URL` stays on the mock. It is deleted once the SIS Adapter serves the contract.

#### The student key under campus sign-in

Proposed on 2026-10-29. The AIT installation signs students in through the campus realm `ait-dev`, as "Campus sign-in" in [`spec-part-2.md`](spec-part-2.md) describes. The plugin sends the token's `sub` to the Adapter as the `sub` query parameter of `GET /records`. It URL-encodes `sub`, changes nothing else, and reads no other claim. Campus IT decides what `sub` holds, and the Adapter must handle either choice.

- **(a) The username in `sub`.** Campus writes the AIT username into `sub` for the Issuer platform's clients. The username is the student's registration number, so the Adapter looks the student up by registration number. Keycloak lowercases usernames, so `sub` arrives as `st123456`. Match it without regard to case.
- **(b) Campus's own `sub`.** Campus keeps `sub` as its Keycloak user id. The Adapter reads that user from the campus realm, takes the username, which is the registration number, and looks the student up. Campus IT will say how the Adapter may read users, for example through a service account. Campus asks consumers not to store its `sub` during the PoC, so the Adapter keeps `sub` out of its storage and its access logs.

Either way:

- For a `sub` it cannot resolve, the Adapter answers `404` or an empty list. The plugin turns both into `no_record`, and the wallet shows a failure.
- The plugin takes the first entry of the list and passes its `recordId` back unchanged, so the Adapter chooses the `recordId` format.
- A campus account belongs to one person, not one degree. How the Issuer chooses between two degrees is still open, under "Multi-degree students" in `spec-part-2.md`. Until that is decided, list one record per `sub`.

## 3. Issuer admin API (Thas's)

The line the Portal and the Track 4 successor integrate against (Q24). **Proposed** in full; the proposal describes the functions (§3.3) but not an API.

Auth: staff ID token from section 1 with the `registrar` role.

| Method and path | Does |
|---|---|
| `GET /credentials?studentId=&name=&school=&program=&status=` | Search issued credentials (a search table joined with Certify's ledger; identifiers only, no credential bodies) |
| `GET /checklists/{credentialType}` | The checks configured for a credential type |
| `POST /evaluations` | Section 2a's evaluation, the same endpoint the plugin calls, with `{ sub, scope, recordId }`: the result per check, used by the Portal and for debugging. It replaces `POST /checklists/{credentialType}/evaluate` (2026-11-02); how staff are authorised on it is part 2's ([`spec-part-2.md`](spec-part-2.md)) |

Two Portal flows go to Certify directly over the internal network rather than through this API, as drawn in responsibilities.md section 2: **revoke** (Certify's status API; the bit flips at the next status-list batch, then the list is published, section 4) and the **hard copy** (decided 2026-10-20: the Portal, as an OpenID4VCI client in the student's own session, calls Certify's `/issuance/credential` with that session's access token and a proof JWT signed with one Portal-held key per installation; Certify takes the plugin path, so the Gateway runs the checklist (with the gate on) and Certify's ledger records the Portal's `client_id` as `tokenClientId`, as for any wallet claim; the Portal embeds the credential in the PDF's QR and discards it. No pre-authorized offer, and no evaluate call before it: a `403` checklist result is the student's result page). Certify's management, ledger-search, status and credential-configuration APIs stay internal (section 6).

## 4. Publishing to the VDR (Jo)

What the Issuer platform pushes, where, and how often. Thas's mock publisher implements this and is the specification Jo builds the final publisher against (**proposed** in full).

| Artifact | Published | Path on the VDR |
|---|---|---|
| DID document for `did:web:<host>` | At setup and on key rotation | `/.well-known/did.json` |
| Bitstring Status List (signed by Certify) | On change, within Certify's 60-second batch | `/status/{listId}` |
| JSON-LD context (transcript; `/contexts/transcript/v1.json` in v0.1, no Student ID) | On publish from the VC Lab | `/contexts/{name}/{version}.json` |
| PDF template and display metadata | On publish from the VC Lab | `/templates/{credentialType}/...` |

Verifiers fetch the DID document, status lists and contexts; only the Portal fetches templates. No personal data is published. Stable public hostnames for these URLs from the first real issuance are the infra team's to provide; Dev and UAT credentials are throwaway because their URLs encode the environment. Registering the Issuer, its DID and its schemas in the trusted-issuer list is a checklist item before the first UAT issuance.

## 5. Credential offer (any wallet)

The Issuer platform promises a valid OpenID4VCI credential offer and nothing more about the wallet. Credentials follow the verifier conformance profile in responsibilities.md section 6 (VCDM 2.0, JSON-LD, Ed25519Signature2020, Bitstring Status List, `did:web`). Issuance is proven in CI with stock Inji Web and Mimoto, which run only in the local Compose.

## 6. Deployment configuration (infra team)

The handover to the infra team (images, plugin jar, the configuration of every stock image, the ingress allowlist, key custody) is [`configuration-contract.md`](configuration-contract.md). Any change to it goes to the infra team before it is applied.
