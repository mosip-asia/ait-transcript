# Issuer v0.1 — deviations from the proposal

Status: draft for team review, 2026-10-11, extended 2026-10-19. "Q" numbers refer to the owner's 2026-10-11 scoping plan, kept outside this repository. Each row is a place where v0.1 does something other than `proposal-issuer.md` (PR 4) says, why, and when it is revisited. The team accepting this list is the prerequisite for starting the build on 2026-11-02.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 1 | Certify re-signs the status list and pushes it to the CDN about every 60 s (§3.3, §5.1(6)); batched in Appendix A.5 | The registry host caches Certify's live list; Certify re-signs every 10 s | Certify 0.14 has no push; a cache gives verifiers the same isolation from the VM with configuration only | If the team needs the VM to be unreachable from the internet |
| 2 | A neutral shared PostgreSQL ledger belonging to neither Certify nor the portal (§3.3, §5.4) | Certify's own ledger, plus a search table beside it | Certify already records credential ID and status-list index; its search is exact-match only, so name search needs the extra table | When the portal owner is known |
| 3 | Keys in Inji Certify / HSM / Cloud KMS (§3.4) | A PKCS12 key file | Certify 0.14 supports PKCS12 or PKCS#11 HSM only; Cloud KMS via PKCS#11 is unverified | At the move to the AIT domain |
| 4 | The verifier gives "instant tamper detection" (verifier-scope §2.2) | The transcript context's claims are not covered by the signature (research 07); not fixed | Out of scope for v0.1 by decision | Listed as a known limitation; owner to be decided |
| 5 | Walletless PDFs expire after 90 days via `validUntil`; wallet credentials do not (§2.1) | One credential configuration, no expiry | Certify cannot tell the two claims apart; two configurations would be needed | If the team insists (about 2 days) |
| 6 | `did:web:credentials.ait.ac.th` on AIT domains (§5.2) | `did:web` on a temporary hostname | AIT domains need ITserv; a DID cannot move, so credentials are re-issued at the move | When ITserv delegates the domain |
| 7 | JSON-LD or SD-JWT (§2.1) | JSON-LD (W3C VC 2.0) only | One format for v0.1 by decision; more later | Next release |
| 8 | Admin portal, walletless catalog and Cloud Run verifier are Milestone 1 deliverables (§7) | Stand-ins: the existing FastAPI app, stock Inji Web guest mode, stock Inji Verify | Not our responsibility in v0.1; our work stops at the issuer admin API | When owners are named |
| 9 | `GET /students/:id/transcript` (§5.1(3)) | Adds `degreeId` and a degrees list | A student can hold more than one degree, each its own credential (§5.1(3)) | With ITserv when the SIS adapter is built |
| 10 | Not mentioned | Mimoto runs beside Inji Web and renders the PDF | Inji Web cannot run without it | Add to the proposal's component list |

## Changes on 2026-10-19

Source: [`responsibilities.md`](responsibilities.md). Rows 4, 8 and 10 above are superseded by rows 11, 13 and 14.

| # | Proposal says | v0.1 does | Why | Revisit |
|---|---|---|---|---|
| 11 | Instant tamper detection (verifier-scope §2.2) | The transcript and Student ID contexts are fixed (research 07, option 1a) and every claim is covered by the signature; replaces row 4 | The Issuer promises that any standards-conformant verifier can verify its credentials | Option 1b (defined course terms) as a v2 context when selective disclosure is scheduled; the context URL is versioned once credentials must survive a change (after v0.1); the hashing method is a placeholder until an official design exists |
| 12 | Approval queue reviewed by officers, released by Pre-Authorized Code after approval (§3.3); Milestone 2 adds an authorization-server gate and deferred issuance (§7) | Decisions are instant: the Gateway evaluates a checklist of predicates and presentations at request time (plan Q23). The pre-authorized offer is used only for the Portal's hard-copy path. No approval queue in v0.1; no Milestone 2 gate or deferred issuance | Human judgement lives in the organisation's data (holds, flags), not in the Issuer | If an organisation needs a human step with no data source |
| 13 | Admin portal, walletless catalog and Cloud Run verifier are Milestone 1 deliverables (§7) | The Portal (staff and student sides) is ours; the verifier is stock Inji Verify co-deployed and configured by us; there is no catalog, any OpenID4VCI wallet claims the offer; replaces row 8 | Ownership settled on 2026-10-19 | |
| 14 | Inji Web in walletless mode produces the PDF (§2.1, §5.1) | The Portal renders the PDF from the VC Lab template and embeds the credential in the QR with the PixelPass pipeline; Inji Web and Mimoto run only in the local Compose for integration tests; replaces row 10 | The web wallet is out of scope as a deliverable | |
| 15 | VC Lab and Card Display Lab, a template designer publishing to the VDR (§3.3) | Files and a publish step: PDF template, display metadata, JSON-LD template through Certify's credential-configuration API. No card template | Wallets draw their own card from display metadata and claims | An SVG rendering template if a wallet spike shows Inji Web or Inji Mobile honours it |
| 16 | `courseTableHtml` display claim in the credential (PRD §7) | Removed with the context fix; structured `courses` only, numeric claims as strings | Templates come from the VDR; the QR carries data | |
| 17 | VDR and `did.json` operated as part of the issuer (§2.2, §5.2) | The VDR is Jo's; the Issuer publishes through a mock publisher that is also the specification Jo builds against | Ownership settled on 2026-10-19 | When Jo's publisher exists |
| 18 | Deployment on one GCE VM run by the project (§5) | The infra team owns deployment end to end; we hand over two images (Gateway, Portal), the stock-image configuration contract, the ingress allowlist and a local Compose | Ownership settled on 2026-10-19 | |
| 19 | One installation for AIT | The same codebase also serves the hackathon installation; all credential configurations are VCDM 2.0 | "Same code for two projects" | Before the 31 December dry run |
