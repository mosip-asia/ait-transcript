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

### Concepts

- [Approval gate](./concepts/approval-gate.md) — why the registrar approval step is enforced in the demo app UI only, not at Certify/Keycloak, and the upgrade path if that ever needs to change.
- [Transcript credential design](./concepts/transcript-credential.md) — the AIT Transcript VC claim shape, where it was borrowed from, and the PDF-rendering gotchas to avoid re-discovering.
- [VC revocation](./concepts/vc-revocation.md) — registrar revoke/reissue/history, the VCDM 1.1 → 2.0 migration it required, and the schema/networking/caching gotchas hit building it.

### Guides

- [VC download troubleshooting](./guides/vc-download-troubleshooting.md) — the four layered bugs (Keycloak login page, JWT issuer, nginx path truncation, JSON escaping) that block Inji Web VC download, how to tell them apart, and how each was fixed.
