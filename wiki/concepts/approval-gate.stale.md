---
title: Approval Gate (stale)
description: Why registrar approval is enforced in the demo app UI only, not at Certify/Keycloak.
type: concept
tags:
  - wiki
  - concept
  - approval
---
# Approval Gate (stale)

> **Stale since 2026-10-31.** The demo app still shows the claim link only after approval, but the reasons below describe Certify's CSV data provider, which the Gateway replaced. The Gateway refuses at issuance on each credential type's checklist, not on approval ([Credential request](./credential-request.md)), and part 2 removes the request queue ([`spec-part-2.md`](../project/issuer-v0.1/spec-part-2.md)).

## The decision

Registrar approval of a transcript VC request is enforced **only in the demo app's own UI/state machine** (SQLite `pending` → `approved`/`rejected`). It is **not** enforced at the Inji Certify / Keycloak layer. See [PRD.stale.md §6.3](../../PRD.stale.md) for the full rationale.

## Why

Stock Certify's `MockCSVDataProviderPlugin` issues a VC to any OIDC-authenticated identity with a matching CSV row — there is no built-in "pending" concept. Real enforcement would require an Apply-job-style adapter (approval action → write/patch the Certify CSV row + flip a Keycloak account's enabled flag), modeled on `inji/credential-lab/src/credential_lab/apply/`. That's real engineering effort for a demo whose audience is internal stakeholders, not a security review.

## What this means in practice

- All mock students are pre-seeded and always issuable in Certify/Keycloak, exactly like `inji/vc-stack`'s existing pilot.
- Before approval, the demo app simply does not show the Inji Web deep link or the mock Keycloak credentials needed to claim the VC.
- A student who already knew the mock Keycloak username/password for another persona could technically claim a transcript VC without going through the demo app's approval flow. This is a known, accepted gap — call it out proactively if a stakeholder asks "what stops someone from skipping approval?"

## Upgrade path (not built, not planned unless requested)

If real enforcement is ever needed: on approval, write the student's row into `installations/ait/adapter/student_identity_data.csv` (or flip a "disabled" flag Certify's CSV provider respects) and enable/create the corresponding Keycloak user, then restart Certify/Keycloak per `inji/wiki/guides/credential-lab-pdf-csv-gotchas.md` (ConfigMap/file changes don't hot-reload). Do not build this speculatively — see [AGENTS.md](../../AGENTS.md) "Core scope decisions."

## Related

- [PRD (stale)](../../PRD.stale.md)
- [Transcript credential design](./transcript-credential.md)
- `inji/wiki/guides/credential-lab-how-it-works.md` (Apply Job pattern this would mirror)
