# The Approval gate sits beside the data path, not in it

Decided by Thas on 2026-11-02.

Certify's Data-provider plugin fetches the record from the Adapter itself and asks the Gateway only whether to issue (a read-only evaluation, `POST /evaluations`, called first; the plugin then fetches). Part 1 of v0.1 put the Gateway between the plugin and the data, so the plugin knew one URL and no claim names. Thas moved the data path into the Issuer's core so the Gateway can be switched off by configuration (`mosip.certify.gateway.enabled`), and later replaced by checks at the Authorization Server (Keycloak or Authentik), without touching how records reach Certify. The cost: the plugin now owns the record path, a generic escaping rule and the data errors (`no_record`, `adapter_error`), and the issuance record is Certify's ledger rather than a Gateway table.

This reverses stories 21 and 22 of the hackathon chain spec (part 1 of v0.1, retired: `git show 1d68d74:wiki/project/issuer-v0.1/spec-hackathon-chain.md`): the plugin no longer knows only one URL, one secret and two timeouts, and the Gateway no longer owns the whole error vocabulary. [`deviations.md`](../../wiki/project/issuer-v0.1/deviations.md) row 22 records it.

**Considered Options:** calling the Gateway and the Adapter concurrently (rejected: saves milliseconds, adds a join and fetches a refused student's record); keeping the Gateway in the data path (rejected: the Gateway could not be removed without rewriting the core).
