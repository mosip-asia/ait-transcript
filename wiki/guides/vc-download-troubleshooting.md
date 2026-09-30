---
title: VC Download Troubleshooting
description: The four layered bugs that blocked Inji Web VC download (login page, JWT issuer, nginx path truncation, JSON escaping) — symptoms, root causes, fixes.
type: guide
tags:
  - wiki
  - guide
  - troubleshooting
  - keycloak
  - certify
  - mimoto
  - nginx
---
# VC Download Troubleshooting

Operator runbook for "student claims the AIT Transcript VC in Inji Web and it fails." Distilled from a 2026-09-18 debugging session that fixed **four independent bugs**, each one masking the next — fixing #1 revealed #2, fixing #2 revealed #3, fixing #3 revealed #4. If the download breaks again, work through these in order; each has its own reproduction and its own fix, and a partial fix can look identical to the *next* bug in the chain.

Confirmed working end-to-end (live browser claim, two students) after all four fixes.

## When to use this page

| Symptom | Bug | Start here |
|---|---|---|
| Browser tab dies / blank page right after clicking **Sign In** on the Keycloak login form | #1 | [Login page self-references an unreachable hostname](#1-login-page-self-references-an-unreachable-hostname) |
| Inji Web shows a generic **"Due to technical error, we were unable to download the card"**, Mimoto logs a 404 body `<problem>No static resource .</problem>` or `{"detail":"No static resource ."}` | #2 or #3 — same symptom, different cause, check Certify logs to tell them apart | [JWT issuer mismatch](#2-jwt-issuer-mismatch-garbled-404) and [nginx path truncation](#3-nginx-drops-the-path-suffix-same-404-different-cause) |
| Public deployment only: Mimoto logs `POST https://api…/v1/certify/issuance/credential` 404 `<instance>/v1/certify/</instance>` even though the config is fixed and deployed | #3 (`public-gateway-nginx.conf`), then #5 if the file is right | [nginx path truncation](#3-nginx-drops-the-path-suffix-same-404-different-cause) and [Deployed config never took effect](#5-deployed-proxy-config-never-took-effect) |
| Same "technical error" screen, Mimoto logs `<VCError><error>json_processing_error</error>...` from Certify | #4 | [Unescaped HTML breaks the VC template's JSON](#4-unescaped-html-breaks-the-vc-templates-json) |

**General debug loop** for any of these:

```sh
cd vc-stack
./smoke.sh                        # config + live checks — catches #2/#3/#4's config symptoms before a browser is involved
```

Then claim a VC through the real browser flow (`http://localhost:4004` → guest → AIT University Registrar → AIT Transcript → log in as `ait-2026-0001` / password `inji`) and tail logs from a **fresh** claim attempt (old log lines from a previous attempt will mislead you):

```sh
docker logs mimoto-service --since 1m 2>&1 | grep -A2 "postApi()::error\|Exception occurred\|Initiated"
docker logs vc-stack-certify-1 --since 1m 2>&1 | grep -iE "ERROR|json_processing|static resource"
```

A stale Keycloak SSO session (browser skips the login form and bounces straight through) occasionally produces an unrelated `Invalid code verifier` error — that's a client-side PKCE timing artifact, not one of the four bugs below. Force a real login by ending the session first (`POST /admin/realms/inji/users/{id}/logout` via the Keycloak admin API, or clear cookies for `localhost:9080` — note the session cookies are `HttpOnly`, so `document.cookie` alone won't clear them) and retry.

---

## #1: Login page self-references an unreachable hostname

**Symptom:** Browser navigates to `http://localhost:9080/realms/inji/protocol/openid-connect/auth?...` fine (login page loads), but the tab errors out or goes blank immediately after clicking **Sign In** — no redirect back to Inji Web ever happens.

**Root cause:** Keycloak's `--hostname-url=http://keycloak:8080` (needed for #2/#3 below) makes Keycloak self-reference that **internal Docker hostname** in every HTML page it serves — including the login form's `action` attribute:

```sh
curl -s "http://localhost:9080/realms/inji/protocol/openid-connect/auth?..." | grep -o 'action="[^"]*"'
# action="http://keycloak:8080/realms/inji/login-actions/authenticate?..."
```

The browser can't resolve `keycloak` (that's Docker-network-internal DNS), so the form POST fails silently.

`keycloak-nginx.conf`'s catch-all `location /` only ran `sub_filter` on `application/json` bodies — the JSON well-known document got its `authorization_endpoint` rewritten to `localhost:9080` correctly, but HTML responses (the login page, required-actions pages) passed through completely unrewritten.

**Fix ([vc-stack/keycloak-nginx.conf](../../vc-stack/keycloak-nginx.conf)):** split the JSON well-known route into its own `location` block (keeps the narrow, JSON-only `authorization_endpoint` rewrite), then add a broad `sub_filter 'http://keycloak:8080' 'http://localhost:9080';` with `sub_filter_types text/html;` to the catch-all. `token_endpoint` in the JSON path is deliberately **not** touched by the broad rule — Mimoto's JWT `aud` needs it to stay `keycloak:8080` (see #2).

**Verify:**

```sh
curl -s "http://localhost:9080/realms/inji/protocol/openid-connect/auth?..." | grep -o 'action="[^"]*"'
# should now show action="http://localhost:9080/realms/inji/login-actions/authenticate?..."
docker exec mimoto-service curl -s http://keycloak:8080/realms/inji/.well-known/openid-configuration | jq '{authorization_endpoint, token_endpoint}'
# authorization_endpoint should be localhost:9080, token_endpoint should stay keycloak:8080
```

---

## #2: JWT issuer mismatch (garbled 404)

**Symptom:** Login succeeds, Inji Web redirects back with an auth code, but the download fails. Mimoto logs an error POSTing to Certify's issuance endpoint with a response body that isn't a normal Certify error:

```
RestApiClient::postApi()::error uri: http://certify-nginx/v1/certify/issuance/credential 404 :
"<problem xmlns="urn:ietf:rfc:7807"><type>about:blank</type><title>Not Found</title>
<status>404</status><detail>No static resource .</detail><instance>/v1/certify/</instance></problem>"
```

Certify's own app log (`docker logs vc-stack-certify-1`) shows **nothing** for this request — meaning it never reached the VC-issuance controller. It's not a routing problem; it's Spring Security's OAuth2 resource server failing to authenticate the JWT and falling through to a generic static-resource 404 instead of a clean 401/403 (a known-ugly Spring Boot behavior, not a Certify bug).

**Root cause:** `MOSIP_CERTIFY_AUTHN_ISSUER_URI` was templated from `KEYCLOAK_PUBLIC_BASE_URL` (`${KEYCLOAK_PUBLIC_BASE_URL:-http://localhost:9080}/realms/inji`), but the JWT's real `iss` claim is `http://keycloak:8080/realms/inji` (Keycloak's `--hostname-url`, same value `MOSIP_CERTIFY_AUTHORIZATION_URL` already correctly used). Neither `http://localhost:9080/realms/inji` nor the malformed `.env` value `http://keycloak:9080/realms/inji` (a hybrid of internal hostname + public port that matches neither Docker DNS nor the host) ever matched — every JWT failed issuer validation.

**Fix ([vc-stack/docker-compose.yaml](../../vc-stack/docker-compose.yaml)):** `MOSIP_CERTIFY_AUTHN_ISSUER_URI` now uses `${KEYCLOAK_DOCKER_AUTH_SERVER:-http://keycloak:8080}/realms/inji` — the same variable `MOSIP_CERTIFY_AUTHORIZATION_URL` already used. Also fixed [vc-stack/.env](../../vc-stack/.env)'s `KEYCLOAK_PUBLIC_BASE_URL` from the malformed `http://keycloak:9080` to `http://localhost:9080` (it still feeds `--hostname-admin-url` for the admin console, which needs the real public URL).

**Verify:**

```sh
docker exec vc-stack-certify-1 env | grep -iE "issuer|authorization_url"
# MOSIP_CERTIFY_AUTHN_ISSUER_URI and MOSIP_CERTIFY_AUTHORIZATION_URL should both be http://keycloak:8080/realms/inji
```

Recreate `certify` (and `keycloak-server` if `.env` changed) after editing: `docker compose up -d certify keycloak-server`.

---

## #3: nginx drops the path suffix (same 404, different cause)

**Symptom:** Identical to #2's 404 body, but Certify's own app log now shows a `NoResourceFoundException` at `VelocityTemplatingEngineImpl`/`VCIssuanceController` level, or — if you test with `curl` directly — a request with a **valid, correctly-issued** JWT still gets the garbled 404 through `certify-nginx`, while the exact same request straight to the `certify` container (bypassing nginx) works.

**Root cause:** [vc-stack/certify-nginx.conf](../../vc-stack/certify-nginx.conf)'s `location /v1/certify/` used:

```nginx
set $certify_upstream certify:8090;
proxy_pass http://$certify_upstream/v1/certify/;
```

nginx's own docs are explicit that a **variable-based** `proxy_pass` target disables the normal "replace the location-matched prefix with the proxy_pass URI" substitution. In practice this meant nginx forwarded **only the literal `/v1/certify/`** upstream — `issuance/credential` was silently dropped. Certify's DispatcherServlet then saw a bare `/v1/certify/` request, found no matching route, and fell through to `NoResourceFoundException` with an **empty** resource name (`"No static resource ."`) — which is why the error message never mentioned the real path.

Unauthenticated requests hit Spring Security's default-deny rule first and got Certify's ordinary 403 (also on the same truncated path) — so the response code alone doesn't tell you which bug you're looking at; you have to check whether Certify's app log has an entry for the request at all (#2 = no entry; #3 = an entry, ending in `NoResourceFoundException`).

**Same bug, second place:** [vc-stack/public-gateway-nginx.conf](../../vc-stack/public-gateway-nginx.conf) (the public deployment's `api.` gateway) had it on *every* location — `/v1/mimoto/`, `/v1/certify/`, `/.well-known/`, `/realms/`, `/v1/verify/` — so anything through that gateway lost its path. Seen from the public site as Mimoto's `POST https://api.<host>/v1/certify/issuance/credential` → 404 `<instance>/v1/certify/</instance>`, and `curl -X POST https://api.<host>/v1/certify/issuance/credential` answering `path: /v1/certify/`. Any new nginx `location` that uses a variable `proxy_pass` must have no URI part.

**Fix:** drop the URI from `proxy_pass` entirely — `proxy_pass http://$certify_upstream;` — so nginx forwards the original request URI unchanged. This location's prefix and Certify's own path are identical (`/v1/certify/...` in, `/v1/certify/...` out), so no rewriting was ever needed here; the `set $certify_upstream` variable only exists to defer DNS resolution to request time (see the file's own top-of-file comment), not to rewrite paths.

**Verify:**

```sh
TOKEN="<a real bearer token from a fresh claim attempt — see certify-nginx access log>"
curl -s -X POST http://localhost:9091/v1/certify/issuance/credential \
  -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{}'
# should now return a real Certify validation error (e.g. {"error":"invalid_proof",...}),
# not the "No static resource ." 404
```

---

## #4: Unescaped HTML breaks the VC template's JSON

**Symptom:** Token exchange and JWT auth both succeed, Certify's issuance controller is reached, but it returns:

```
<VCError><error>json_processing_error</error>
<error_description>Invalid JSON data encountered during credential generation.
Please check the data provider response and template configurations.</error_description></VCError>
```

Certify's app log pinpoints it further: `org.json.JSONException: Expected a ',' or '}' at ... line 32` — line 32 of the decoded `vc_template` is the `"courseTableHtml": "${courseTableHtml}"` line.

**Root cause:** [data/generate_csv.py](../../data/generate_csv.py) wrote every claim — including `courseTableHtml`, the Python-rendered HTML `<table>` — straight into the CSV with **no JSON-string escaping**. Certify's `vc_template` does naive Velocity string substitution, not JSON-aware templating: `"courseTableHtml": "${courseTableHtml}"` just drops the raw value between the quotes. `courseTableHtml`'s own markup contains attribute quotes (`<table style="width:100%;...">`), and those unescaped `"` characters terminate the JSON string early, corrupting everything after them. This is exactly the gotcha [Transcript Credential Design](../concepts/transcript-credential.md#gotchas-already-hit-upstream--do-not-re-discover) already documented (and the same class of issue `~/Developer/inji/wiki/guides/credential-lab-pdf-csv-gotchas.md` calls out under "AIT Transcript preset") — it was written down as a rule but never actually implemented in this repo's CSV generator.

**Fix:** added `escape_vc_quoted_claim()` to `generate_csv.py` — `json.dumps(value)[1:-1]` (JSON-encode, then strip the surrounding quotes the template already supplies) — applied to every claim **except** `courses`, which is the one field deliberately embedded unquoted as raw JSON (`"courses": ${courses}`, no surrounding quotes to protect, and escaping it would corrupt the array itself).

**Verify:**

```sh
python3 data/generate_csv.py && python3 data/test_generate_csv.py && python3 data/test_ait_courses.py
```

Then reproduce Certify's substitution locally against the regenerated CSV (swap in the real `vc_template` from `vc-stack/certify_init.sql`, base64-decoded) and confirm `json.loads()` succeeds on the rendered document — this is how the bug was originally isolated to line 32 without needing a live claim attempt for every iteration.

**After a CSV fix, the running `certify` container must be restarted (not just have the bind-mounted file changed underneath it) if it already served requests since last start** — `MockCSVDataProviderPlugin` did not visibly pick up the on-disk change until `docker compose restart certify`, even though the file inside the container was already correct. If a CSV/template fix doesn't seem to take effect, restart `certify` before assuming the fix is wrong.

## #5: Deployed proxy config never took effect

**Symptom:** You fixed a bind-mounted nginx config (e.g. #3 in `public-gateway-nginx.conf`), the Deploy workflow was green, and the behaviour is unchanged. The container's `created` time in Dozzle predates the deploy.

**Root cause:** The config is a bind mount. `docker compose up -d` recreates a container only when its *compose* config changes, not when a mounted file's contents do, and nginx reads its config only at start. So the new file was on disk and the old one still served. `bootstrap.sh` restarted `keycloak certify-nginx mimoto-service inji-web` but not `public-gateway`.

**Fix:** `public-gateway` is now in the restart line in `compose_up()` in [vc-stack/bootstrap.sh](../../vc-stack/bootstrap.sh). Any new service that reads a mounted config must be added there too. The same goes for any nginx that proxies a service Compose may recreate: `verify-ui` resolves `verify-service` once at start, so recreating `verify-service` (e.g. after adding `extra_hosts`) left `/v1/verify` on `verify-ui` returning errors until it was restarted, and the deploy failed at bootstrap's `verify-ui proxy` check (`curl` exit 22).

**Verify:** after a deploy, the container's `created`/start time is recent, and a request that used to hit the old behaviour changes (for #3, the `path` in Certify's error is the full path).

---

## Related

- [Local stack](../architecture/vc-stack.md) — the Keycloak `keycloak:8080` vs `localhost:9080` split these bugs live in.
- [Transcript Credential Design](../concepts/transcript-credential.md) — claim shape and the escaping rule bug #4 was already documented against.
