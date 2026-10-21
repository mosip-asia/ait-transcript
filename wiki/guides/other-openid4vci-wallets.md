---
title: Connecting a non-Inji OpenID4VCI wallet
description: What the AIT transcript platform exposes to an OpenID4VCI wallet, what a wallet must support, what blocks a generic wallet today, and the changes needed to let one connect.
tags:
  - guide
  - openid4vci
  - wallets
---
# Connecting a non-Inji OpenID4VCI wallet

**Status: not tested with any non-Inji wallet.** This page comes from the live responses and the Inji source (Certify 0.14.0, Mimoto 0.21.0), and it separates what works from what does not. The platform issues credentials with OpenID4VCI, but it was configured around Inji Wallet's behaviour. A generic wallet cannot complete the flow today without the platform changes in [What has to change](#what-has-to-change). Developers building on Inji Wallet should use [wallet-developer-urls.md](./wallet-developer-urls.md) instead.

## What the platform exposes

All values below are from the live deployment.

| Piece | Value |
|---|---|
| Credential issuer | `https://api.transcript-demo.ait-vc.dpi.ait.ac.th` |
| Issuer metadata | `GET <issuer>/.well-known/openid-credential-issuer` |
| Credential endpoint | `POST <issuer>/v1/certify/issuance/credential` |
| Authorization server | `https://keycloak.transcript-demo.ait-vc.dpi.ait.ac.th/realms/inji` (listed in the issuer metadata) |
| AS discovery | `<AS>/.well-known/oauth-authorization-server` (also serves `openid-configuration`) |
| Credential configuration id | `ait-transcript` (scope `ait_transcript_vc_ldp`) |
| Grant | authorization code with PKCE `S256`; no pre-authorized code, **no credential offer** |
| Format | `ldp_vc`, signed `Ed25519Signature2020` (algorithm `EdDSA`), VCDM 2.0 |
| Key binding | `did:jwk`; proof type `jwt`, signing algorithms `RS256` or `ES256` |
| Credential `@context` | `["https://api.transcript-demo.ait-vc.dpi.ait.ac.th/contexts/transcript/v1.json", "https://www.w3.org/ns/credentials/v2"]`; the request's `@context` must match this list |
| Not in the issuer metadata | `nonce_endpoint`, credential offer, batch or deferred endpoints, SD-JWT VC or mdoc configurations |

## What the wallet itself must support

Whatever stack the wallet uses, it must:

1. Handle `ldp_vc` with the `Ed25519Signature2020` suite and the `credentials/v2` context, both to receive and to verify it. Many wallets only do SD-JWT VC, mdoc or `jwt_vc_json`.
2. Read the older credential-definition style in the issuer metadata (`format`, `scope`, `credential_definition.@context` and `type`), rather than only the final-1.0 shape.
3. Send a `jwt` proof signed with an RS256 or ES256 key, identified as a `did:jwk`.
4. Open the login in a browser or WebView with PKCE and capture the redirect. For `wallet-demo` the realm allows `*` and, explicitly, `io.mosip.residentapp.inji://oauthredirect` and `http://localhost:4004/redirect`; a new client defines its own redirect URIs (below).
5. Send a credential request whose `credential_definition.@context` and `type` have the same number of entries as the configured lists and every entry present in them (Certify's `isValidLdpVCRequest`). A stale cached metadata list fails with "No matching ldp_vc credential configuration found for scope".

## What blocks a generic wallet today

| # | Blocker | Today's behaviour |
|---|---|---|
| 1 | **No usable OAuth client.** | The only client, `wallet-demo`, is confidential. Mimoto holds its key and authenticates for the wallet, so a wallet exchanging the code directly with Keycloak has no credentials. |
| 2 | **Advertised token endpoint is not public.** | The discovery document gives `token_endpoint`, `jwks_uri` and `pushed_authorization_request_endpoint` as `http://keycloak.<host>:8080/...`. Keycloak builds these from the request Host; port 8080 is not exposed. |
| 3 | **Issuer mismatch on one discovery path.** | `oauth-authorization-server` returns an issuer equal to the AS URL. `openid-configuration` still returns `http://keycloak:8080/realms/inji`, so a strict wallet that uses OIDC discovery rejects it. |
| 4 | **Token audience.** | Certify is configured to accept tokens with audience `wallet-demo` (`MOSIP_CERTIFY_AUTHN_ALLOWED_AUDIENCES`, and an audience mapper on that client). A token from another client is expected to be rejected unless it carries that audience; not tested. |
| 5 | **No nonce or offer.** | A wallet that insists on a nonce endpoint or starts from a credential offer cannot use this issuer. |
| 6 | **Format support.** | See the wallet list above; this is on the wallet side. |

## A workaround that exists now

A wallet with custom code can still complete the flow, using the path Inji Wallet uses:

1. Read the issuer metadata and the AS discovery document; take `authorization_endpoint` from the latter.
2. Open `authorization_endpoint` with `client_id=wallet-demo`, `scope=ait_transcript_vc_ldp`, `response_type=code`, `code_challenge_method=S256`, a redirect URI the realm allows for that client, and a PKCE challenge.
3. After login, post the code **to Mimoto, not to Keycloak**: `POST https://api.transcript-demo.ait-vc.dpi.ait.ac.th/v1/mimoto/get-token/AITUniversity` as `application/x-www-form-urlencoded` with `grant_type=authorization_code`, `code`, `redirect_uri` (the same value used in step 2) and `code_verifier`. Mimoto signs the client assertion and returns Keycloak's token response.
4. Build the `jwt` proof, `POST` the credential request with `Authorization: Bearer <access_token>`, and store the returned credential.
5. Check it: `POST https://api.transcript-demo.ait-vc.dpi.ait.ac.th/v1/verify/vc-verification` with the credential JSON and `Content-Type: application/vc+ld+json` returns `{"verificationStatus":"SUCCESS"}`, or use the browser at the verify host.

This fits wallets that let you plug in your own token step, such as an Inji-based wallet or a wallet SDK with a custom token provider. It does not fit one that requires a standard token endpoint.

## What has to change

These are changes to the platform, not yet made. Items 1 to 3 together let a standards-based wallet get a token itself.

1. **Add a public Keycloak client** (for example `wallet-public`): public, PKCE `S256` required, the other wallet's redirect URI registered, scope `ait_transcript_vc_ldp` available. Give it an audience mapper for `wallet-demo` (as `wallet-demo` has) or add the new client id to `MOSIP_CERTIFY_AUTHN_ALLOWED_AUDIENCES` in `vc-stack/docker-compose.yaml`. Keycloak's admin paths are blocked on the public hostnames, so a running realm is changed through the admin API over an IAP or SSH tunnel; `keycloak-realm.json` only seeds a new realm.
2. **Make the public token endpoint real.** In `vc-stack/keycloak-nginx.conf.template`, for requests under a public hostname only, rewrite `http://<host>:8080` to the public base URL for `token_endpoint`, `jwks_uri`, `introspection_endpoint`, `userinfo_endpoint` and the PAR endpoint. The existing `map $host` that keeps Mimoto (`Host: keycloak`) untouched is the model. The path `/realms/inji/protocol/openid-connect/*` is already served on the public host.
3. **Apply the issuer rewrite to `openid-configuration`** too, with the same `map`.
4. Optional: `nonce_endpoint` and credential-offer support depend on the Certify version; 0.14.0 has neither, so wallets that need them wait for an upgrade.

After 1 to 3, test with one chosen wallet and fix what it reports. Tokens issued through the public endpoint should carry the same pinned `iss` (`http://keycloak:8080/realms/inji`) that Certify validates, since Keycloak's hostname is fixed; confirm that with the first test. A regression check on Inji Web and Mimoto is just the earlier curl comparison of the internal discovery document, which must stay byte-identical.

## Why it is shaped like this

Keycloak's issuer is pinned to the Docker-internal `http://keycloak:8080` because Mimoto's JWT `aud` and Certify's `issuer-uri` must equal the token's `iss`. Public hostnames therefore need rewritten views of the discovery documents; see [architecture/inji-mobile-wallet.md](../architecture/inji-mobile-wallet.md) for the details and the Inji-specific findings.
