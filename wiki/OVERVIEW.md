---
title: Wiki
description: What to read in this repo, in order, and where the rest is.
tags:
  - wiki
  - overview
---
# Wiki

This repo is the Issuer (Inji Certify with the Gateway and an Adapter behind it) and the demo stack that runs the whole journey around it: sign in, claim a credential into a wallet, verify it, revoke it.

## Start here, in this order

1. [README](../README.md): run it, test it, deploy it.
2. [CONTEXT.md](../CONTEXT.md): the terms every other page uses.
3. [Responsibilities](./project/issuer-v0.1/responsibilities.md): who owns which part of the Issuer.
4. [Local stack](./architecture/vc-stack.md): the four deployments and their containers.
5. [Credential request](./concepts/credential-request.md): what a wallet sends, what the token carries, how the Gateway turns it into a record.
6. [Interface contracts](./project/issuer-v0.1/contracts.md), with [`adapter/openapi.yaml`](../adapter/openapi.yaml): what each side provides.
7. [Part 2 spec](./project/issuer-v0.1/spec-part-2.md): what is being built next.
8. [Configuration contract](./project/issuer-v0.1/configuration-contract.md): what infra deploys. For infra, or anyone changing a `compose.yaml`.

## When you need it

- [Deviations from the proposal](./project/issuer-v0.1/deviations.md): where v0.1 departs from the issuer proposal (PR 4), and why.
- [Transcript JSON-LD context](./concepts/transcript-context.md): the rules that get every claim signed.
- [Transcript credential](./concepts/transcript-credential.md): the claim shape and its gotchas.
- [VC revocation](./concepts/vc-revocation.md): revoke and reissue, and their gotchas.
- [Wallet developer URLs](./guides/wallet-developer-urls.md) and [non-Inji OpenID4VCI wallets](./guides/other-openid4vci-wallets.md): for people building a wallet.
- [Schemas](./schemas/): the transcript credential's JSON Schema and an example.

## Reference

Lookup pages for agents and operators, not reading material:

- [VC download troubleshooting](./reference/vc-download-troubleshooting.md): four layered failures and how to tell them apart.
- [Inji mobile wallet](./reference/inji-mobile-wallet.md): why the phone gets its own issuer list and metadata.
- [Pre-authorized flow](./reference/certify-preauth-flow.md): why one Certify 0.14 cannot serve pre-authorized offers and wallet-initiated issuance together.

## Stale

Written by someone else and no longer accurate; kept, marked in the file name and title:

- [PRD (stale)](../PRD.stale.md) · [Approval gate (stale)](./concepts/approval-gate.stale.md)

Retired pages (the hackathon chain spec, the research notes on signing coverage, JSON literals, the data-provider plugin and the hackathon configurations, the PR 4 diagrams) are in git: `git show 1d68d74:<path>`.
