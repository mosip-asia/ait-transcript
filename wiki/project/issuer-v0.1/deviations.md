# Issuer v0.1 — deviations from the proposal

Status: accepted by the team on 2026-10-20; first written 2026-10-11, extended 2026-10-19. "Q" numbers refer to the owner's 2026-10-11 scoping plan, kept outside this repository. Each row is a place where v0.1 does something other than `proposal-issuer.md` (PR 4) says, why, and when it is revisited. The team's acceptance of this list cleared the build to start on 2026-11-02.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 1 | Certify re-signs the status list and pushes it to the CDN about every 60 s (§3.3, §5.1(6)); batched in Appendix A.5 | The registry host caches Certify's live list; Certify re-signs every 10 s | Certify 0.14 has no push; a cache gives verifiers the same isolation from the VM with configuration only | If the team needs the VM to be unreachable from the internet |
| 2 | A neutral shared PostgreSQL ledger belonging to neither Certify nor the portal (§3.3, §5.4) | Certify's own ledger, plus a search table beside it | Certify already records credential ID and status-list index; its search is exact-match only, so name search needs the extra table | When the portal owner is known |
| 3 | Keys in Inji Certify / HSM / Cloud KMS (§3.4) | A PKCS12 key file | Certify 0.14 supports PKCS12 or PKCS#11 HSM only; Cloud KMS via PKCS#11 is unverified | At the move to the AIT domain |
| 4 | The verifier gives "instant tamper detection" (verifier-scope §2.2) | The transcript context's claims are not covered by the signature (research 07); not fixed | Out of scope for v0.1 by decision | Listed as a known limitation; owner to be decided |
| 5 | Walletless PDFs expire after 90 days via `validUntil`; wallet credentials do not (§2.1) | One credential configuration, no expiry | Certify cannot tell the two claims apart; two configurations would be needed | If the team insists (about 2 days) |
| 6 | `did:web:credentials.ait.ac.th` on AIT domains (§5.2) | `did:web` on a temporary hostname | AIT domains need ITserv; a DID cannot move, so credentials are re-issued at the move | When ITserv delegates the domain |
| 7 | JSON-LD or SD-JWT (§2.1) | JSON-LD (W3C VC 2.0) only | One format for v0.1 by decision; more later | Next release |
| 8 | Admin portal, walletless catalog and Cloud Run verifier are Milestone 1 deliverables (§7) | Stand-ins: the existing FastAPI app, stock Inji Web guest mode, stock Inji Verify | Not Thas's responsibility in v0.1; Thas's work stops at the issuer admin API | When owners are named |
| 9 | `GET /students/:id/transcript` (§5.1(3)) | Adds `degreeId` and a degrees list | A student can hold more than one degree, each its own credential (§5.1(3)) | With ITserv when the SIS adapter is built |
| 10 | Not mentioned | Mimoto runs beside Inji Web and renders the PDF | Inji Web cannot run without it | Add to the proposal's component list |

## Changes on 2026-10-19

Source: [`responsibilities.md`](responsibilities.md). Rows 4, 8 and 10 above are superseded by rows 11, 13 and 14.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 11 | Instant tamper detection (verifier-scope §2.2) | The transcript context is fixed (research 07, option 1a: claim terms at the top level, `courses` as a JSON literal, every other claim an untyped string) and every claim is covered by the signature; the context is served at a versioned URL (`/contexts/transcript/v1.json`) from the start; no Student ID credential in v0.1; replaces row 4 | The Issuer promises that any verifier on a JSON-LD 1.1 processor can verify its credentials; v0.1 verifies whole credentials only, so one JSON literal covers the course data | Option 1b (defined course terms) as a v2 context when selective disclosure is scheduled; the promise that every published context version stays published starts once credentials must survive a change (after v0.1); the hashing method is a placeholder until an official design exists |
| 12 | Approval queue reviewed by officers, released by Pre-Authorized Code after approval (§3.3); Milestone 2 adds an authorization-server gate and deferred issuance (§7) | Decisions are instant: the Gateway evaluates a checklist of predicates and presentations at request time (plan Q23). No pre-authorized code in v0.1 (row 20). No approval queue in v0.1; no Milestone 2 gate or deferred issuance | Human judgement lives in the organisation's data (holds, flags), not in the Issuer | If an organisation needs a human step with no data source |
| 13 | Admin portal, walletless catalog and Cloud Run verifier are Milestone 1 deliverables (§7) | The Portal (staff and student sides) is Thas's; the verifier is stock Inji Verify co-deployed and configured by Thas; there is no catalog, any OpenID4VCI wallet claims the offer; replaces row 8 | Ownership settled on 2026-10-19 | |
| 14 | Inji Web in walletless mode produces the PDF (§2.1, §5.1) | The Portal renders the PDF from the VC Lab template and embeds the credential in the QR with the PixelPass pipeline; Inji Web and Mimoto run only in the local Compose for integration tests; replaces row 10 | The web wallet is out of scope as a deliverable | |
| 15 | VC Lab and Card Display Lab, a template designer publishing to the VDR (§3.3) | Files and a publish step: PDF template, display metadata, JSON-LD template through Certify's credential-configuration API. No card template | Wallets draw their own card from display metadata and claims | An SVG rendering template if a wallet spike shows Inji Web or Inji Mobile honours it |
| 16 | `courseTableHtml` display claim in the credential (PRD §7) | Removed with the context fix; structured `courses` plus the derived `courseList` line for wallet cards, numeric claims as strings; the credential schema becomes v2 | Templates come from the VDR; the QR carries data; a stock wallet card cannot render the nested array | |
| 17 | VDR and `did.json` operated as part of the issuer (§2.2, §5.2) | The VDR is Jo's; the Issuer publishes through a mock publisher that is also the specification Jo builds against | Ownership settled on 2026-10-19 | When Jo's publisher exists |
| 18 | Deployment on one GCE VM run by the project (§5) | The infra team owns deployment end to end; Thas hands over two images (Gateway, Portal), the stock-image configuration contract, the ingress allowlist and a local Compose | Ownership settled on 2026-10-19 | |
| 19 | One installation for AIT | The same codebase also serves the hackathon installation; all credential configurations are VCDM 2.0 | "Same code for two projects" | Before the 31 December dry run |

## Changes on 2026-10-20

Source: [`responsibilities.md`](responsibilities.md) section 5 and the research note [`certify-preauth-flow.md`](../../reference/certify-preauth-flow.md). Added after the team's acceptance; not yet put to the team.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 20 | Hard copies released by Pre-Authorized Code (§3.3); walletless PDF from a catalog (§2.1) | The Portal is the hard copy's wallet: a hard copy is made from the student side, inside the student's own sign-in, the Portal redeeming the credential at Certify's issuance endpoint through the ordinary authorization-code flow and the plugin path, then embedding it in the QR and discarding it. No pre-authorized code in v0.1; no staff-triggered printing | Certify 0.14 serves pre-authorized offers and wallet-initiated issuance only from separate instances (one data-provider plugin and one token issuer each); the student side already has the sign-in, so the wallet path costs no second instance, no offer cache and no second place that runs the checklist | If OSA asks for counter printing by staff: a second hard-copy-only Certify instance sharing DB, keystore and DID, serving pre-authorized offers |

## Changes on 2026-10-28

Source: [`spec-part-2.md`](spec-part-2.md). Not yet put to the team.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 21 | `did:web:credentials.ait.ac.th` on AIT domains (§5.2); the conformance profile's `did:web` with the DID document on the VDR (responsibilities.md section 6) | v0.1 issues under Certify's `did:key`, refreshed after a wipe, so a wipe changes the issuer identifier; nothing is published at the VDR's `/.well-known/did.json`; supersedes the `did:web` part of row 6 for v0.1 | Removes the DID publishing step and the question of `did:web` over plain HTTP from v0.1; credentials through v0.1 carry no compatibility promise anyway | After v0.1, with a stable public VDR hostname |
