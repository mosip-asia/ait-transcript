---
title: Wallet developer URLs
description: The endpoints and settings a developer needs to point their own wallet (built on Inji Wallet) at the AIT transcript demo on GCP.
tags:
  - guide
  - mobile
  - developers
---
# Wallet developer URLs

For people building their own wallet, based on [inji/inji-wallet](https://github.com/inji/inji-wallet) v0.22.1, against the public demo. How the stack serves a phone and why is in [architecture/inji-mobile-wallet.md](../architecture/inji-mobile-wallet.md).

## The one setting that matters

| Setting (`.env`) | Value |
|---|---|
| `MIMOTO_HOST` | `https://api.transcript-demo.ait-vc.dpi.ait.ac.th` |

No trailing slash and **no `/v1/mimoto`**: the app appends `/v1/mimoto/...` itself, and a path in the host gives `/v1/mimoto/v1/mimoto/issuers`. It is read at build time (`react-native-dotenv` caches it, so clear Metro's cache after changing it). `ESIGNET_HOST` and `OBSRV_HOST` are not used by this flow; point them at the same host so the app does not call MOSIP's servers. Keep `CREDENTIAL_REGISTRY_EDIT=true` in dev builds if you want to change the Mimoto host from the in-app Settings screen.

## Endpoints

| Hostname | Role | What a wallet calls |
|---|---|---|
| `api.transcript-demo.ait-vc.dpi.ait.ac.th` | Mimoto + Certify gateway | `/v1/mimoto/issuers`, `/v1/mimoto/allProperties`, `/v1/mimoto/verifiers`, `POST /v1/mimoto/get-token/AITUniversity`, `/.well-known/openid-credential-issuer`, `POST /v1/certify/issuance/credential` |
| `keycloak.transcript-demo.ait-vc.dpi.ait.ac.th` | Login (realm `inji`) | `/realms/inji/protocol/openid-connect/auth` in a WebView; `/realms/inji/.well-known/oauth-authorization-server` for discovery |
| `verify.transcript-demo.ait-vc.dpi.ait.ac.th` | Inji Verify (browser) | Scan or upload a credential QR here to check it |
| `wallet.transcript-demo.ait-vc.dpi.ait.ac.th` | Inji Web (browser wallet) | Not needed by a mobile wallet; useful to compare behaviour |

Nothing else is exposed or needed. Do not use the Docker names that may appear in some responses (`keycloak:8080`, `certify-nginx`, `host.docker.internal`): they are for Mimoto inside the stack.

## Issuer and credential

| | |
|---|---|
| Issuer id | `AITUniversity` |
| Credential configuration id | `ait-transcript` |
| Scope | `ait_transcript_vc_ldp` |
| Format | `ldp_vc`, proof `Ed25519Signature2020`, issuer DID `did:key` |
| OAuth client | `wallet-demo` (confidential; Mimoto holds the key) |
| Redirect URI | `io.mosip.residentapp.inji://oauthredirect` (register this URL scheme in your app) |
| Key binding | `did:jwk`; proof JWT `RS256` or `ES256` |

## Flow the wallet follows

1. `GET /v1/mimoto/issuers` on `api.` returns `AITUniversity` with a public `credential_issuer_host`, the redirect URI above and a public `token_endpoint`.
2. Fetch `<credential_issuer_host>/.well-known/openid-credential-issuer`. `authorization_servers` is the public Keycloak.
3. Discover the login URL from `<authorization_server>/.well-known/oauth-authorization-server` (`authorization_endpoint`).
4. Open it in a WebView (PKCE S256, `client_id=wallet-demo`, `scope=ait_transcript_vc_ldp`). The student logs in; Keycloak redirects to the custom scheme with a `code`.
5. **Do not post the code to Keycloak's `token_endpoint`.** Keycloak's own discovery advertises `http://<host>:8080/...` for it, which is not reachable. POST the code (form: `grant_type`, `code`, `client_id`, `redirect_uri`, `code_verifier`) to the issuer list's `token_endpoint`, Mimoto's `get-token/AITUniversity`, which authenticates to Keycloak for the wallet. Inji Wallet already does this for trusted issuers.
6. Build the proof JWT and `POST` to `credential_endpoint` with the bearer token.

## Things that will surprise you

- Mimoto serves two different issuer lists. `api.` `/v1/mimoto/issuers` and `/.well-known/openid-credential-issuer` are the **phone views**; the same paths through `wallet.` return the Docker-internal values Inji Web needs. Always use the `api.` host.
- Mimoto and the app both cache issuer metadata. After the issuer config changes, restart the app (or clear its cache); a stale cache can send a credential request whose `@context` Certify no longer matches.
- Credentials issued before 2026-10-15 carry a `host.docker.internal` JSON-LD context, which an app cannot load when it verifies a credential after download. Reissue them.
- Presenting a credential from the app to Inji Verify (OpenID4VP) is not enabled; verify by QR in the browser.
- The VM runs Mon-Fri 08:30-18:30 Asia/Bangkok only.

## Test students

Mock students are defined in [data/students.json](../../data/students.json). Ask the demo owner for the shared test password rather than copying one into a wallet repo.

## Quick check

```sh
A=https://api.transcript-demo.ait-vc.dpi.ait.ac.th
curl -s $A/v1/mimoto/issuers | jq '.response.issuers[0] | {credential_issuer_host, redirect_uri, token_endpoint}'
curl -s $A/.well-known/openid-credential-issuer | jq '{credential_issuer, authorization_servers, credential_endpoint}'
curl -s https://keycloak.transcript-demo.ait-vc.dpi.ait.ac.th/realms/inji/.well-known/oauth-authorization-server | jq .authorization_endpoint
```
