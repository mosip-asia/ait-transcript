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
- [Transcript credential design](./concepts/transcript-credential.md) — the AIT Transcript VC claim shape, where it was borrowed from, and the PDF-rendering gotchas to avoid re-discovering.
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
- [Signing coverage](./research/signing-coverage.md) — why the transcript claims were not covered by the issuer signature, and the context fix chosen for v0.1.
- [Diagrams](./diagrams/) — the issuer proposal overview and its ITserv view, in draw.io format.
- [Schemas](./schemas/) — the transcript credential JSON Schema and examples (VCDM 1.1 variant), and the proposed corrected JSON-LD context.
