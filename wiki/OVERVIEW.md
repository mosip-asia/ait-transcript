---
title: AIT Transcript VC Demo Wiki
description: Navigation hub for the AIT Transcript VC journey demo.
tags:
  - wiki
  - overview
---
# AIT Transcript VC Demo Wiki

This repo is a local, Docker-only demo for internal AIT stakeholders: a student requests a transcript Verifiable Credential, a registrar approves it, the student claims it into Inji Web Wallet, and a verifier checks it with Inji Verify. Full scope and requirements are in [PRD.md](../PRD.md); the agent playbook is [AGENTS.md](../AGENTS.md).

This repo is standalone — it does not run against or modify the upstream `inji` sandbox repo (not included here). It borrows patterns and credential design from that repo's `vc-stack/` and Credential Lab, documented in the pages below.

## Navigation

### Architecture

- [Local stack](./architecture/vc-stack.md) — the vendored Docker Compose topology (Certify, Mimoto, Keycloak, Inji Web, Inji Verify, Postgres) and how it differs from `inji/vc-stack`.
- [Inji mobile wallet](./architecture/inji-mobile-wallet.md) — which URLs the phone app needs, why the stack's internal hostnames break it, how the `api.` gateway serves it separate copies without touching Inji Web, and what is still open.

### Concepts

- [Approval gate](./concepts/approval-gate.md) — why the registrar approval step is enforced in the demo app UI only, not at Certify/Keycloak, and the upgrade path if that ever needs to change.
- [Credential request](./concepts/credential-request.md) — what a wallet sends to request a credential, what the access token carries (`sub`, `scope`), how Keycloak signs it and Certify checks it, and how the Gateway turns it into a record lookup.
- [Transcript credential design](./concepts/transcript-credential.md) — the AIT Transcript VC claim shape, where it was borrowed from, and the PDF-rendering gotchas to avoid re-discovering.
- [Transcript JSON-LD context](./concepts/transcript-context.md) — context v1 on the static mock VDR (`vc-lab/contexts/transcript/v1.json`), its URL, the rules that get every claim signed (top-level terms, no datatypes, `courses` as `@json`), the jsonld-java caveat and the versioning promise.
- [VC revocation](./concepts/vc-revocation.md) — registrar revoke/reissue/history, the VCDM 1.1 → 2.0 migration it required, and the schema/networking/caching gotchas hit building it.

### Guides

- [VC download troubleshooting](./guides/vc-download-troubleshooting.md) — the four layered bugs (Keycloak login page, JWT issuer, nginx path truncation, JSON escaping) that block Inji Web VC download, how to tell them apart, and how each was fixed.
- [Wallet developer URLs](./guides/wallet-developer-urls.md) — the endpoints, settings and flow for building your own wallet on Inji Wallet against the GCP demo.
- [Connecting a non-Inji OpenID4VCI wallet](./guides/other-openid4vci-wallets.md) — what the platform exposes to a generic wallet, what blocks one today, the workaround and the changes needed.

### Issuer v0.1 (planned product, not the running demo)

Vocabulary for the Issuer product is in [CONTEXT.md](../CONTEXT.md).

- [Responsibilities](./project/issuer-v0.1/responsibilities.md) — who owns which component of the Issuer, the external contracts, the design decisions that bound v0.1, and the verifier conformance profile.
- [Interface contracts](./project/issuer-v0.1/contracts.md) — sign-in, record data, admin API, VDR publishing, credential offer and deployment configuration, and who provides each.
- [Deviations from the proposal](./project/issuer-v0.1/deviations.md) — every place v0.1 departs from the issuer proposal (PR 4), why, and when it is revisited.
- [Hackathon chain spec](./project/issuer-v0.1/spec-hackathon-chain.md) — the buildable spec for the part of v0.1 deployed before the holidays: directory layout, Compose changes, mock adapter, Gateway checklist runner, Certify data-provider plugin, context fix, hackathon configurations, and what the configuration contract to infra must list, each with its acceptance check.
- [Part 2 spec](./project/issuer-v0.1/spec-part-2.md) — the buildable spec for the rest of v0.1: admin API with staff search and checklist evaluation, mock VDR publisher with published status lists (the issuer stays `did:key`), VC Lab publish step through Certify's configuration API, the Portal's sign-in, staff and student sides, the hard copy (PixelPass QR on a PDF), and the end-to-end close, each with its opening check and acceptance.
- [Configuration contract to infra](./project/issuer-v0.1/configuration-contract.md) — what the infra team deploys for each installation: the service set and images, the plugin jar, every service's environment variables, mounted files and ports, the per-installation settings, the secrets, the URLs that need stable hostnames, the ingress allowlist, start order, and the two dated asks (hostnames, signing-key custody).
- [Signing coverage](./research/signing-coverage.md) — why the transcript claims were not covered by the issuer signature, and the context fix chosen for v0.1.
- [Certify data-provider plugin](./research/certify-data-provider-plugin.md) — the one-method SPI, how a plugin jar loads into the 0.14 image, what the CSV plugin does, the shipped REST example, and the loading risks with a sub-day test plan.
- [JSON literals in Certify and Verify](./research/certify-json-literal.md) — Titanium JSON-LD 1.1 on both the signing and verifying paths accepts `@json`; versions, determinism caveats, and the Compose check that makes it observed.
- [Pre-authorized flow and the data-provider plugin](./research/certify-preauth-flow.md) — why one Certify 0.14 cannot serve pre-authorized offers and wallet-initiated issuance together, the flow traced, and the costed alternatives for the hard copy.
- [Hackathon credential configurations](./research/hackathon-configurations.md) — what VPID, Developer Passport and Achievement consist of in `ait-vc` today, and what a VCDM 2.0 migration into the Issuer changes; the Issuer carries the Developer Passport and the Achievement on roster predicates (a top note says so).
- [Diagrams](./diagrams/) — the issuer proposal overview and its ITserv view, in draw.io format.
- [Schemas](./schemas/) — the transcript credential JSON Schema and example v2 (VCDM 2.0, for transcript context v1); the VCDM 1.1 variant was removed with the context fix.
