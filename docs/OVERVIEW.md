---
title: Documentation Index
description: What to read in this repo, in order, and where the rest is.
tags:
  - docs
  - overview
---
# Documentation Index

This repository houses the **Institutional Verifiable Credential Platform (Issuer)**: Inji Certify with its Data-provider plugin, an Adapter behind it, an optional Gateway clearance engine beside it, and a complete demo stack running the issuance journey (sign-in, credential claim into mobile/web wallets, verification, and revocation).

---

## 1. Start here, in this order

1. [README](../README.md): Quick start, architecture, local execution, and testing.
2. [CONTEXT.md](../CONTEXT.md): Common terminology, entities, and invariant rules.
3. [Institutional VC Issuer Proposal](./project/proposal-issuer.md): The architectural foundation of the complete university issuer.
4. [Verifier Scope & Architecture](./project/verifier-scope.md): Verification workflows from paper PDFs to digital OpenID4VP presentations.
5. [Responsibilities](./project/issuer-v0.1/responsibilities.md): Ownership boundaries across the Issuer platform components.
6. [Local stack](./architecture/vc-stack.md): Container services, networking, and deployment topology.
7. [Credential request](./concepts/credential-request.md): Token flow, claims mapping, and Data-provider plugin resolution.
8. [Interface contracts](./project/issuer-v0.1/contracts.md) (with [Adapter OpenAPI](./contracts/adapter-openapi.yaml)): External and internal service boundaries.
9. [Part 2 spec](./project/issuer-v0.1/spec-part-2.md): Planned deliverables for full v0.1.0 close.
10. [Configuration contract](./project/issuer-v0.1/configuration-contract.md): Infrastructure settings and configuration baseline.
11. [CI/CD & Deployment Architecture](./deployment.md): Multi-environment promotion, NetBird VPN mesh, and automated rollback.

---

## 2. Deep Dives & Architectural Decisions

- [ADR 0001: Approval gate sits beside the data path](./adr/0001-approval-gate-beside-the-data-path.md): Why the plugin reads records directly and the Gateway is optional.
- [Deviations from the proposal](./project/issuer-v0.1/deviations.md): Documented differences between proposal and current implementation.
- [SIS Adapter handover](./project/issuer-v0.1/sis-adapter-handover.md): Field mapping and expectations for the real SIS Adapter.
- [Transcript JSON-LD context](./concepts/transcript-context.md): Signing rules, `@json` course representations, and context hashing.
- [Transcript credential](./concepts/transcript-credential.md): Schema structure, subject claims, and gotchas.
- [VC revocation](./concepts/vc-revocation.md): Bitstring Status List v1.0, revocation batches, and status verification.
- [Wallet developer URLs](./guides/wallet-developer-urls.md) & [Non-Inji OpenID4VCI wallets](./guides/other-openid4vci-wallets.md): Guidelines for external wallet integration.
- [Schemas](./schemas/): Master JSON schemas and sample credential payloads.

---

## 3. Operational Reference

Lookup guides for operators, developers, and agents:

- [CI/CD & Deployment Architecture](./deployment.md): Branch promotions (`dev` -> `uat` -> `main`), secrets, and SSH deployment over NetBird.
- [VC download troubleshooting](./reference/vc-download-troubleshooting.md): Diagnosing issuer lists, session failures, and token errors.
- [Inji mobile wallet](./reference/inji-mobile-wallet.md): Mobile-specific issuer lists and metadata routing.
- [Pre-authorized flow](./reference/certify-preauth-flow.md): Constraints on multi-mode issuance in Inji Certify 0.14.
- [Issue Tracker Guidelines](./agents/issue-tracker.md): Local Markdown-based ticketing guidelines.

---

## 4. Historical & Stale Content

Historical design and legacy exploratory documents:

- [Approval gate (stale)](./concepts/approval-gate.stale.md): Early exploratory notes prior to ADR 0001.
- Historical commits for retired specifications: Recoverable via `git show 1d68d74:<path>`.
