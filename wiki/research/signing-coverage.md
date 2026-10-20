# The issuer signature does not cover the transcript and Student ID claims

Known issue, recorded 2026-10-01. **Decided 2026-10-19: fixed in v0.1 with option 1 below (claim terms at the top level, `courses` as a JSON literal), with defined inner terms as the fallback; see [`responsibilities.md`](../project/issuer-v0.1/responsibilities.md) section 5.** The body below is the original 2026-10-01 finding; only its links were adjusted for this repository. It was written against the earlier `ait-vc` demo stack, so the `local-stack/` and `deployment/` paths below refer to that repository, and the ticket and research note it cites are kept outside this repository.

It corrected one line of an earlier local research note on student data and the transcript QR (research 04).

## Short answer

On an `AitTranscriptCredential` and on a `StudentIDCredential`, the issuer signature covers the credential's envelope and none of the claims inside `credentialSubject`. A holder can change a grade, a name or a degree in the issued JSON and the proof still verifies.

The cause is in two JSON-LD context files, not in Certify, the key or the proof suite. The three hackathon contexts had the same defect and were fixed in ticket 03; these two were left as they were.

## Sources and method

- `mosip-asia/ait-vc`, branch `playground/transcript-demo`, read on 2026-10-01:
  - `local-stack/config/academic-transcript-context.json` and `local-stack/config/student-context.json`, the two affected contexts.
  - `local-stack/config/vpid-context.json`, `passport-context.json` and `achievement-context.json`, the three that are not affected.
  - `local-stack/config/contexts/w3-2018-credentials-v1.jsonld` and `w3-ns-credentials-v2.jsonld`, the vendored base contexts.
  - `deployment/helm/charts/inji-certify/config/student-context.json`, the deployment copy.
- `mosip-asia/ait-transcript-demo` (since renamed `ait-transcript`), branch `feature/ait-vc-integration`: `vc-stack/config/academic-transcript-context.json`, the file ours was copied from.
- Hackathon ticket 03, "Developer Passport and anchor data path" (local tracker), section "The Passport context, and the signed-claims fix", for what was observed on the running stack.
- A measurement made earlier on 2026-10-01 with jsonld.js 8 against the v1 example credential `ait-transcript-credential.example.json` (superseded by [the v1.1 example](../schemas/ait-transcript-credential.v1_1.example.json)), signed locally with a throwaway key. It was not repeated for this note.
- **No live run for these two credentials.** Docker was down when the finding was made, and the reproduction was not carried out afterwards because the issue is already known. See "What is and is not confirmed".

## The mechanism

Both files put every claim term inside a context scoped to the credential's type:

```json
"AitTranscriptCredential": {
  "@id": "ait:AitTranscriptCredential",
  "@context": { "fullName": "ait:fullName", "courses": "ait:courses", "…": "…" }
}
```

In JSON-LD 1.1 a type-scoped context applies to the node that carries the type and, by default, does not propagate into nested nodes (`@propagate` is `false` for type-scoped contexts). The type sits on the credential. The claims sit one node down, in `credentialSubject`. So by the time the processor reaches `fullName`, the term definitions have been reverted.

Nothing else catches the terms. Neither vendored base context has a top-level `@vocab` (the only `@vocab` occurrences in them are `"@type": "@vocab"` on individual terms), so an undefined term has no fallback IRI.

What happens next depends on the processor:

- A lenient processor drops undefined terms during expansion. The claims never reach URDNA2015 canonicalization, so they are not in the bytes that are hashed and signed. Issuance and verification both succeed, on a document that does not contain the claims.
- A safe-mode processor (the digitalbazaar default) refuses to drop terms and rejects the credential outright.

## What the signature covers

| Part of the credential | Covered |
| --- | --- |
| `id`, `type`, `issuer`, `validFrom` / `validUntil` (or `issuanceDate` / `expirationDate`) | Yes |
| `credentialStatus` | Yes |
| `credentialSubject.id` | Yes, `id` is defined by the base context and survives the revert |
| Every other `credentialSubject` claim on the transcript: `fullName`, `registrationNo`, `degreeAwarded`, `courses` and everything in it, `thesisGrade`, the credit totals, and the rest | **No** |
| Every other `credentialSubject` claim on the Student ID: `studentID`, `fullName`, `faculty`, `expiryDate`, `face` | **No** |

Two consequences follow from the table.

- **Revocation is unaffected.** `credentialStatus` is signed, so a tampered transcript still points at its own status-list entry and a revoked one still reads as revoked.
- **The subject binding is intact, the content is not.** The credential still proves that this issuer issued a transcript credential to this subject id and has not revoked it. It does not prove what the transcript says.

## What is and is not confirmed

- **Measured with jsonld.js 8 (2026-10-01):** the VCDM 2.0 transcript canonicalizes to 11 quads with the current context and to 36 with a corrected one. A copy with a changed grade and a changed name still verifies. In safe mode the credential is rejected.
- **Observed on the running stack, for the same defect in another context:** before ticket 03 fixed `vpid-context.json`, which had exactly this shape, tampering `credentialSubject.id` on a VPID credential was caught by Inji Verify and tampering `vpid` was not. After the terms were lifted to the top level, every `credentialSubject` field failed with `ERR_SIGNATURE_VERIFICATION_FAILED` when tampered. That run went through Certify 0.14 and Inji Verify 0.17, so it shows that Titanium JSON-LD (used through Danubetech `ld-signatures-java`) behaves as the lenient case here.
- **Not run:** the tamper test on a transcript or a Student ID issued by the running stack. The expectation from the two points above is that a tampered transcript verifies in Inji Verify. Until someone runs it, treat that as expected, not observed.

The reproduction, when wanted: bring the stack up with `./bootstrap-mock.sh` in `local-stack`, issue a transcript, change `credentialSubject.fullName` or one grade, and submit the JSON to Inji Verify. Scenario 4 of `local-stack/tools/passport-claim.js` is the pattern to copy.

## Where the defect exists

| File | State |
| --- | --- |
| `ait-vc/local-stack/config/academic-transcript-context.json` | Affected |
| `ait-vc/local-stack/config/student-context.json` | Affected. Flagged as out of scope in hackathon tickets 03, 05 and 07 |
| `ait-vc/deployment/helm/charts/inji-certify/config/student-context.json` | Affected. Same shape, and it also carries a `StudentTranscriptCredential` type with the same defect |
| `ait-transcript-demo/vc-stack/config/academic-transcript-context.json` | Affected. Ours was copied from it unchanged |
| `ait-vc/local-stack/config/vpid-context.json`, `passport-context.json`, `achievement-context.json` | Not affected. Terms are at the top level |

## Options under discussion

Nothing below has been applied.

1. **Lift the terms to the top level of each context**, as `vpid-context.json` does. This is the fix ticket 03 chose for the hackathon contexts: it removes a nesting level, and a top-level term is part of the base active context, so it survives the revert. A corrected transcript context, tested with jsonld.js, is at [`academic-transcript-context.proposed.json`](../schemas/academic-transcript-context.proposed.json).
2. **Add a property-scoped context on `credentialSubject`** instead. Considered and passed over in ticket 03 as the larger change.

Points that any fix has to settle:

- **The nested course objects.** `courses` holds semester objects (`term`, `courses`, `credits`, `gpa`, `cumGpa`) that hold course objects (`no`, `title`, `lec`, `lab`, `grade`). None of those inner terms is defined anywhere today. The proposed context types `courses` as `"@type": "@json"`, which signs the whole structure as one ordered JSON literal. Whether Titanium in the Certify 0.14 image accepts `@json` is unchecked. The fallback is to define the ten inner terms individually.
- **Credentials already issued stop verifying.** The context is fetched by URL at verification time, so correcting it changes the canonical form of every credential that references it. Each one has to be re-issued after the change.
- **The copies have to move together**: `local-stack`, the Helm chart, and the pattern repo if it is still in use.
- **A safe-mode verifier rejects today's credentials.** An outside verifier built on the digitalbazaar stack would refuse the current transcript regardless of tampering, which matters if the VCDM 1.1 and JWS question from 2026-10-01 comes from such a verifier.

## Correction to research 04

The last "Open points" item but one in research 04 said the nested course fields "expand through [the v2 context's] `@vocab`, so they are still signed". The vendored v2 context has no top-level `@vocab`, and the problem is wider than the nested fields: no transcript claim is signed. That item now points here.
