---
title: Transcript JSON-LD Context
description: Transcript context v1 on the static mock VDR, the rules it follows so every claim is signed, and the versioning promise.
type: concept
tags:
  - wiki
  - concept
  - credential
  - transcript
  - json-ld
---
# Transcript JSON-LD Context

The transcript credential's JSON-LD context is versioned and served from the static mock VDR. Version 1 is `vc-lab/contexts/transcript/v1.json`. The `vdr` container (stock nginx) serves `vc-lab/contexts/` read-only under `/contexts/`, and the public gateway routes `/contexts/` to it, so the context is at `{gateway}/contexts/transcript/v1.json`.

It replaces `vc-stack/config/academic-transcript-context.json`, which scoped every claim term to the credential type, so the issuer signature covered none of the claims ([signing coverage](../research/signing-coverage.md)). The fix is option 1a of the [hackathon chain spec](../project/issuer-v0.1/spec-hackathon-chain.md) ("Context fix"), and why both processors handle it is in [JSON literals in Certify and Verify](../research/certify-json-literal.md).

## The URL

- Locally the credential names `http://host.docker.internal:9098/contexts/transcript/v1.json`: port 9098 is the public gateway, and `host.docker.internal` is a name Certify (signing), verify-service and Mimoto (verifying) all resolve from inside Docker through their `extra_hosts`.
- On a public deployment `bootstrap.sh` `context_refresh()` moves the `ait-transcript` row to `https://api.<host>/contexts/transcript/v1.json` through `vc-stack/context_refresh.sql`, so a phone can fetch it.
- The URL lives in two places that must agree exactly: the `@context` of the Certify template and the `context` column of the `credential_config` row, both in `installations/ait/certify_seed.sql`. Mimoto builds the credential request's `@context` from the column (via Certify's issuer metadata) and Certify matches it against its configuration. `data/test_generate_csv.py` checks the two agree, and that the context defines exactly the claims the CSV carries.

## The rules

- **Every claim term sits at the top level of the context.** A top-level term survives the revert of a type-scoped context, so it is still defined at `credentialSubject` and its value reaches canonicalisation and the signature.
- **No datatype on anything.** Every claim is an untyped string, dates included; the `xsd:date` typings of the old context are gone. Numbers are strings too, in the three credit totals and inside `courses` (`lec`, `lab`, `credits`, `gpa`, `cumGpa`), which `data/ait_courses.py` enforces.
- **`courses` is the one exception: it is typed `@json`.** The whole course record is signed as one `rdf:JSON` literal (its JCS form), so a change to any grade, title or GPA inside it changes the literal and fails verification. The ten inner keys need no term definitions.
- **No inner `id` and `type` mappings.** The old context redefined `id` and `type` inside its type-scoped block; with the terms lifted, they come from the VCDM 2.0 base context, which protects them.
- **No presentation claims.** The pre-rendered HTML course table is gone from the credential; `courseList` stays, as the one-line-per-course summary a wallet card shows.
- The vocabulary IRI stays the placeholder `https://ait.example/transcript#` until the context moves onto the real VDR host.

## Who can verify it

A JSON-LD 1.1 processor: Titanium (Certify and Inji Verify), jsonld.js and other 1.1 implementations. A verifier built on **jsonld-java** cannot: it implements JSON-LD 1.0 only and rejects the context outright with `invalid type mapping` because of `"@type": "@json"`. That is a hard failure, not a silent drop of the claim, and it is the accepted trade-off of option 1a. The fallback, option 1b, defines the ten inner course terms individually instead, which every processor accepts; it would be published at the same URL if the Compose check fails.

## Versioning

- The series starts at v1. A credential names the version it was signed with in its `@context`, and the context is fetched by URL at verification time, so changing a published version changes the meaning of every credential that names it.
- **In v0.1, v1 may be edited in place**: no credential has to survive a context change yet, and every credential issued against an edited v1 must be re-issued.
- **After v0.1, every published version stays published and unchanged.** A change to the claims is a new file (`v2.json`) and a new template URL; older credentials keep verifying against the version they name.
- The credential schema that goes with context v1 is [`ait-transcript-credential.v2.schema.json`](../schemas/ait-transcript-credential.v2.schema.json), with [an example](../schemas/ait-transcript-credential.v2.example.json).

## How it is checked

`vc-stack/smoke.sh` runs the Compose check of the research note's section 4: it prints the JSON-LD library versions in the Certify and Verify images, checks the gateway serves `vc-lab/contexts/transcript/v1.json` at the URL the issuer metadata names, issues one transcript, and has `vc-stack/issue_and_verify.py` verify it (`SUCCESS`) and three tampered copies (the holder id, `fullName`, one grade inside `courses`), each of which must fail with `ERR_SIGNATURE_VERIFICATION_FAILED`. It then fails on any `Cannot load context` or `Datatype … is not an absolute IRI nor @json` line in the Certify or Verify logs. This check has passed in CI (run 39539975939 at commit 506969a, 2026-10-21), so the behaviour above is observed.

## Related

- [Transcript credential design](./transcript-credential.md)
- [Local stack](../architecture/vc-stack.md)
