#!/usr/bin/env bash
# Inji local stack — idempotent bootstrap
#
# Brings the stack from "fresh git clone" (or post-wipe) to a verified-healthy
# state. Codifies docs/INJI_LOCAL_QUICKSTART.md §11.
#
# Usage:
#   ./bootstrap.sh                  # Mode B (default), idempotent — safe to re-run
#   ./bootstrap.sh --wipe           # tear down volumes + remove ephemeral files first
#   ./bootstrap.sh --mode=a         # Mode A (esignet-mock); writes a compose override
#   ./bootstrap.sh --validate       # only run end-to-end health checks
#   ./bootstrap.sh --did-refresh    # only run the post-wipe did:key dance (§11.3)
#   ./bootstrap.sh --help
#
# Exit codes: 0 ok, 1 prerequisite missing, 2 health check failed, 3 user input needed.

set -euo pipefail

# -------- config --------
STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"

MODE="b"
DO_WIPE=0
ONLY_VALIDATE=0
ONLY_DID=0
P12_PASS_DEFAULT="xy4gh6swa2i"
NETWORK_NAME="vc_stack_network"
OVERRIDE_FILE="docker-compose.override.yaml"
ESIGNET_TOKEN_URL="https://esignet-mock.collab.mosip.net/v1/esignet/oauth/v2/token"
KEYCLOAK_TOKEN_URL="http://host.docker.internal:9080/realms/inji/protocol/openid-connect/token"
KEYCLOAK_DOCKER_AUTH_SERVER="http://keycloak:8080"
KEYCLOAK_REALM_PATH="/realms/inji"
LOCAL_KEYCLOAK_PUBLIC_BASE_URL="http://localhost:9080"
LOCAL_KEYCLOAK_INTERNAL_BASE_URL="http://host.docker.internal:9080"
LOCAL_CERTIFY_PUBLIC_BASE_URL="http://localhost:9091"
LOCAL_MIMOTO_PUBLIC_BASE_URL="http://localhost:4004"
LOCAL_INJI_WEB_OAUTH_REDIRECT_URI="http://localhost:4004/redirect"
LOCAL_CERTIFY_INTERNAL_BASE_URL="http://certify-nginx"
LOCAL_STUDENT_CONTEXT_URL="http://host.docker.internal:9091/academic-transcript-context.json"

# -------- styling --------
if [[ -t 1 ]]; then BOLD=$'\e[1m'; DIM=$'\e[2m'; RED=$'\e[31m'; GRN=$'\e[32m'; YLW=$'\e[33m'; CYN=$'\e[36m'; RST=$'\e[0m'
else BOLD=""; DIM=""; RED=""; GRN=""; YLW=""; CYN=""; RST=""; fi
say()  { printf "%s\n" "$*"; }
step() { printf "\n%s==>%s %s%s%s\n" "$CYN" "$RST" "$BOLD" "$*" "$RST"; }
ok()   { printf "  %s✓%s %s\n" "$GRN" "$RST" "$*"; }
warn() { printf "  %s!%s %s\n" "$YLW" "$RST" "$*"; }
die()  { printf "  %sx%s %s\n" "$RED" "$RST" "$*" >&2; exit "${2:-1}"; }
skip() { printf "  %s·%s %s\n" "$DIM" "$RST" "$*"; }

keycloak_expected_issuer() {
  local pub
  pub="$(env_value KEYCLOAK_PUBLIC_BASE_URL)"
  [[ -n "$pub" ]] || pub="$LOCAL_KEYCLOAK_PUBLIC_BASE_URL"
  pub="${pub%/}"
  printf "%s%s" "$pub" "$KEYCLOAK_REALM_PATH"
}

env_value() {
  local key="$1"
  [[ -f .env ]] || return 0
  awk -F= -v key="$key" '$1 == key { value=$2 } END { print value }' .env \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

# -------- args --------
for a in "$@"; do
  case "$a" in
    --mode=a|--mode=A) MODE="a" ;;
    --mode=b|--mode=B) MODE="b" ;;
    --wipe)            DO_WIPE=1 ;;
    --validate)        ONLY_VALIDATE=1 ;;
    --did-refresh)     ONLY_DID=1 ;;
    -h|--help)
      sed -n '2,16p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *) die "unknown arg: $a (use --help)" 3 ;;
  esac
done

# -------- preflight --------
preflight() {
  step "Preflight"
  for bin in docker jq curl awk; do
    command -v "$bin" >/dev/null || die "missing prerequisite: $bin"
  done
  docker compose version >/dev/null 2>&1 || die "docker compose v2 plugin required"
  ok "docker, compose v2, jq, curl, awk present"

  if [[ "$MODE" == "b" ]]; then
    ok "Keycloak browser URL: $LOCAL_KEYCLOAK_PUBLIC_BASE_URL (no /etc/hosts required)"
  fi
}

# -------- wipe --------
do_wipe() {
  step "Ephemeral wipe"
  if docker compose ps -q >/dev/null 2>&1; then
    docker compose down -v --remove-orphans 2>/dev/null || true
    ok "docker compose down -v"
  fi
  rm -rf certs data .env "$OVERRIDE_FILE"
  ok "removed certs/, data/, .env, $OVERRIDE_FILE"
  # Clean sed leftovers from prior runs but never touch the user's tracked config
  # edits — those are deliberate and persist across wipes.
  find . -maxdepth 2 -name '*.bak' -delete 2>/dev/null || true
  ok "removed *.bak"
}

# -------- .env --------
gen_env() {
  step ".env"
  if [[ -f .env ]]; then
    ok ".env already present"
    return
  fi
  cat > .env <<'EOF'
# Inji local stack — pinned versions
CERTIFY_VERSION=0.14.0
MIMOTO_VERSION=0.21.0
INJI_WEB_VERSION=0.16.0
INJI_VERIFY_SERVICE_VERSION=0.17.0
INJI_VERIFY_UI_VERSION=0.17.0
POSTGRES_VERSION=15
KEYCLOAK_VERSION=24.0

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Must match keytool -storepass AND oidc_p12_password in docker-compose.yaml
OIDC_P12_PASSWORD=xy4gh6swa2i

# Optional single HTTPS gateway/tunnel URL. Leave blank to use localhost for
# browser flows and Docker DNS for container-to-container traffic.
PUBLIC_BASE_URL=

# Local defaults. Certify's issuer metadata must be reachable from Mimoto, so
# the local default is Docker DNS. Use PUBLIC_BASE_URL or override this for HTTPS.
CERTIFY_PUBLIC_BASE_URL=http://certify-nginx
KEYCLOAK_PUBLIC_BASE_URL=http://localhost:9080
KEYCLOAK_INTERNAL_BASE_URL=http://host.docker.internal:9080
MIMOTO_PUBLIC_BASE_URL=http://localhost:4004

# Optional public verifier URL for phone-to-verifier VP sharing.
# Leave blank for browser-only local testing. For a physical phone, expose
# the public gateway with `ngrok http 8098`, then set:
INJI_VERIFY_PUBLIC_BASE_URL=http://localhost:9095
INJI_VERIFY_DID_URI=
INJI_VERIFY_DID_PUBLIC_KEY_URI=
INJI_VERIFY_REDIRECT_URI=http://localhost:4007
EOF
  ok "wrote .env"
}

# -------- migrate legacy Keycloak URLs in .env --------
ensure_keycloak_env() {
  step "Keycloak URL env"
  [[ -f .env ]] || return 0
  local tmp changed=0
  tmp=$(mktemp)
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      KEYCLOAK_PUBLIC_BASE_URL=http://keycloak:8080*)
        printf 'KEYCLOAK_PUBLIC_BASE_URL=%s\n' "$LOCAL_KEYCLOAK_PUBLIC_BASE_URL" >> "$tmp"
        changed=1
        ;;
      KEYCLOAK_PUBLIC_BASE_URL=http://localhost:9080*)
        printf 'KEYCLOAK_PUBLIC_BASE_URL=%s\n' "$LOCAL_KEYCLOAK_PUBLIC_BASE_URL" >> "$tmp"
        changed=1
        ;;
      KEYCLOAK_PUBLIC_BASE_URL=*)
        printf '%s\n' "$line" >> "$tmp"
        ;;
      KEYCLOAK_INTERNAL_BASE_URL=*)
        printf '%s\n' "$line" >> "$tmp"
        ;;
      *)
        printf '%s\n' "$line" >> "$tmp"
        ;;
    esac
  done < .env
  if ! grep -q '^KEYCLOAK_PUBLIC_BASE_URL=' "$tmp"; then
    printf 'KEYCLOAK_PUBLIC_BASE_URL=%s\n' "$LOCAL_KEYCLOAK_PUBLIC_BASE_URL" >> "$tmp"
    changed=1
  fi
  if ! grep -q '^KEYCLOAK_INTERNAL_BASE_URL=' "$tmp"; then
    printf 'KEYCLOAK_INTERNAL_BASE_URL=%s\n' "$LOCAL_KEYCLOAK_INTERNAL_BASE_URL" >> "$tmp"
    changed=1
  fi
  if (( changed )); then
    mv "$tmp" .env
    ok "updated .env Keycloak URLs (localhost:9080 + host.docker.internal)"
  else
    rm -f "$tmp"
    ok "Keycloak URL env already current"
  fi
}

# -------- network --------
gen_network() {
  step "Docker network: $NETWORK_NAME"
  if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    ok "$NETWORK_NAME already exists"
  else
    docker network create "$NETWORK_NAME" >/dev/null
    ok "created $NETWORK_NAME"
  fi
}

# -------- keystore (oidckeystore.p12 + client-cert.pem) --------
gen_keystore() {
  step "Mimoto OIDC keystore (certs/oidckeystore.p12)"
  mkdir -p certs
  if [[ -f certs/oidckeystore.p12 && ! -d certs/oidckeystore.p12 ]]; then
    ok "oidckeystore.p12 already present"
  else
    if [[ -d certs/oidckeystore.p12 ]]; then
      warn "certs/oidckeystore.p12 is a directory (mount-bug). Removing."
      rmdir certs/oidckeystore.p12
    fi
    docker run --rm -v "$PWD/certs:/certs" eclipse-temurin:21-jdk keytool -genkeypair \
      -alias wallet-demo-client -keyalg RSA -keysize 2048 -validity 3650 \
      -keystore /certs/oidckeystore.p12 -storetype PKCS12 \
      -storepass "$P12_PASS_DEFAULT" -keypass "$P12_PASS_DEFAULT" \
      -dname "CN=wallet-demo-client, OU=inji, O=local, L=local, ST=local, C=US" >/dev/null
    ok "generated oidckeystore.p12"
  fi
}

gen_client_cert() {
  [[ "$MODE" == "b" ]] || return 0
  step "Client cert (certs/client-cert.pem + .b64)"
  if [[ -f certs/client-cert.pem && -f certs/client-cert-b64.txt ]]; then
    ok "client-cert.pem + .b64 already present"
  else
    docker run --rm -v "$PWD/certs:/certs" eclipse-temurin:21-jdk keytool -exportcert \
      -alias wallet-demo-client -keystore /certs/oidckeystore.p12 -storetype PKCS12 \
      -storepass "$P12_PASS_DEFAULT" -rfc -file /certs/client-cert.pem >/dev/null
    awk '!/^-----/' certs/client-cert.pem | tr -d '\n' > certs/client-cert-b64.txt
    ok "exported client-cert.pem and client-cert-b64.txt"
  fi
}

# -------- realm cert sync --------
sync_realm_cert() {
  [[ "$MODE" == "b" ]] || return 0
  step "Sync wallet-demo cert into keycloak-realm.json"
  local new_b64 cur_b64 tmp
  new_b64=$(cat certs/client-cert-b64.txt)
  cur_b64=$(jq -r '.clients[] | select(.clientId=="wallet-demo") | .attributes."jwt.credential.certificate" // ""' config/keycloak-realm.json)
  if [[ "$new_b64" == "$cur_b64" ]]; then
    ok "realm cert already matches keystore"
    return
  fi
  tmp=$(mktemp)
  jq --arg b64 "$new_b64" \
    '(.clients[] | select(.clientId=="wallet-demo") | .attributes."jwt.credential.certificate") = $b64' \
    config/keycloak-realm.json > "$tmp"
  # mktemp creates the file 0600; Keycloak (uid 1000 in its container) must read the mounted realm.
  chmod 0644 "$tmp"
  mv "$tmp" config/keycloak-realm.json
  ok "patched keycloak-realm.json with new cert"
  warn "Keycloak re-imports the realm on boot — restart keycloak-server if it was already up"
}

# -------- mode-specific config (issuers, compose override) --------
configure_mode() {
  step "Issuer config for mode=$MODE"
  if [[ "$MODE" == "a" ]]; then
    # Mode A: issuers point at esignet-mock; remove Mode B compose env via override
    local current_target
    current_target=$(jq -r '.issuers[0].authorization_audience' config/mimoto-issuers-config.json)
    if [[ "$current_target" == *"esignet-mock"* ]]; then
      ok "mimoto-issuers-config.json already targets esignet-mock"
    else
      # B → A
      sed -i.bak "s|$KEYCLOAK_TOKEN_URL|$ESIGNET_TOKEN_URL|g" config/mimoto-issuers-config.json
      rm -f config/mimoto-issuers-config.json.bak
      ok "rewrote issuers config: keycloak → esignet-mock"
    fi
    # Override file: blank out Mode B-specific Certify env so it falls back to certify-default.properties
    cat > "$OVERRIDE_FILE" <<EOF
# Auto-generated by bootstrap.sh --mode=a. Do not edit; rerun the script.
# Overrides the Mode-B Keycloak URLs in docker-compose.yaml to point at esignet-mock.
services:
  certify:
    environment:
      - MOSIP_CERTIFY_AUTHORIZATION_URL=https://esignet-mock.collab.mosip.net/v1/esignet
      - MOSIP_CERTIFY_AUTHN_ISSUER_URI=https://esignet-mock.collab.mosip.net/v1/esignet
      - MOSIP_CERTIFY_AUTHN_JWK_SET_URI=https://esignet-mock.collab.mosip.net/v1/esignet/oauth/.well-known/jwks.json
      - MOSIP_CERTIFY_AUTHN_ALLOWED_AUDIENCES={ '$ESIGNET_TOKEN_URL', 'http://certify-nginx:80/v1/certify/issuance/credential' }
EOF
    ok "wrote $OVERRIDE_FILE"
  else
    # Mode B: issuers must point at keycloak; remove any override file from a prior Mode A run
    local tmp public_base_url token_endpoint authorization_audience proxy_token_endpoint credential_issuer_host wellknown_endpoint redirect_uri
    public_base_url="$(env_value PUBLIC_BASE_URL)"
    if [[ -n "$public_base_url" ]]; then
      public_base_url="${public_base_url%/}"
      token_endpoint="$public_base_url/v1/mimoto/get-token/AITUniversity"
      authorization_audience="$public_base_url/realms/inji/protocol/openid-connect/token"
      proxy_token_endpoint="$authorization_audience"
      credential_issuer_host="$public_base_url"
      wellknown_endpoint="$public_base_url/.well-known/openid-credential-issuer"
      redirect_uri="$LOCAL_INJI_WEB_OAUTH_REDIRECT_URI"
    else
      token_endpoint="$LOCAL_MIMOTO_PUBLIC_BASE_URL/v1/mimoto/get-token/AITUniversity"
      # Mimoto 0.21.x uses auth-server well-known token_endpoint for JWT aud (must match Keycloak :9080), not these fields alone.
      authorization_audience="$KEYCLOAK_DOCKER_AUTH_SERVER/realms/inji/protocol/openid-connect/token"
      proxy_token_endpoint="$KEYCLOAK_DOCKER_AUTH_SERVER/realms/inji/protocol/openid-connect/token"
      redirect_uri="$LOCAL_INJI_WEB_OAUTH_REDIRECT_URI"
      # Mimoto (in Docker) reaches host-published Certify via host.docker.internal.
      credential_issuer_host="http://host.docker.internal:9091"
      wellknown_endpoint="http://host.docker.internal:9091/.well-known/openid-credential-issuer"
    fi

    tmp=$(mktemp)
    jq \
      --arg token_endpoint "$token_endpoint" \
      --arg authorization_audience "$authorization_audience" \
      --arg proxy_token_endpoint "$proxy_token_endpoint" \
      --arg redirect_uri "$redirect_uri" \
      --arg credential_issuer_host "$credential_issuer_host" \
      --arg wellknown_endpoint "$wellknown_endpoint" \
      '(.issuers[0].token_endpoint) = $token_endpoint
       | (.issuers[0].authorization_audience) = $authorization_audience
       | (.issuers[0].proxy_token_endpoint) = $proxy_token_endpoint
       | (.issuers[0].redirect_uri) = $redirect_uri
       | (.issuers[0].credential_issuer_host) = $credential_issuer_host
       | (.issuers[0].wellknown_endpoint) = $wellknown_endpoint' \
      config/mimoto-issuers-config.json > "$tmp"
    chmod 0644 "$tmp"
    mv "$tmp" config/mimoto-issuers-config.json
    if [[ -n "$public_base_url" ]]; then
      ok "mimoto-issuers-config.json targets $public_base_url"
    else
      ok "mimoto-issuers-config.json targets local Keycloak and Certify"
    fi
    if [[ -f "$OVERRIDE_FILE" ]]; then
      rm "$OVERRIDE_FILE"
      ok "removed stale $OVERRIDE_FILE from prior Mode A run"
    fi
  fi
}

# -------- bring stack up --------
compose_up() {
  step "docker compose up -d (mode=$MODE)"
  if [[ "$MODE" == "a" ]]; then
    docker compose up -d database certify certify-nginx mimoto-service inji-web verify-service verify-ui
    ensure_certify_nginx_up
    docker compose restart mimoto-service inji-web
    ok "started Mode A services (keycloak-* skipped)"
  else
    docker compose up -d
    ok "started full Mode B stack"
    ensure_certify_nginx_up
    # nginx resolves upstream hostnames at start; recreating keycloak-server/certify
    # changes container IPs and leaves stale upstreams until these proxies restart.
    docker compose restart keycloak certify-nginx mimoto-service inji-web public-gateway
    ok "refreshed Keycloak/Certify nginx upstreams, public gateway, Mimoto and Inji Web"
  fi
}

# Wait until Certify is reachable via nginx (:9091). nginx configs use runtime DNS, but Mimoto
# still loads issuer metadata from http://certify-nginx/ at startup — restart mimoto after this.
ensure_certify_nginx_up() {
  step "Certify nginx (depends on Docker DNS for upstream certify)"
  docker compose up -d certify
  local deadline=$(( $(date +%s) + 120 ))
  while ! curl -sf -o /dev/null http://localhost:9091/.well-known/did.json; do
    if (( $(date +%s) > deadline )); then
      die "certify .well-known not reachable on :9091 — is certify healthy?" 2
    fi
    docker compose up -d certify-nginx 2>/dev/null || true
    sleep 2
  done
  docker compose up -d certify-nginx
  ok "certify-nginx serving :9091"
}

# -------- wait for health --------
wait_healthy() {
  step "Waiting for services"
  local deadline=$(( $(date +%s) + 180 ))
  # Functional probes (not actuator/health — Certify is auth-protected and Mimoto
  # reports DOWN due to HSM/Redis components that aren't needed for this stack).
  local urls=(
    "http://localhost:9091/.well-known/did.json"                       # certify via nginx
    "http://localhost:9099/v1/mimoto/issuers"                          # mimoto BFF
    "http://localhost:4004/v1/mimoto/issuers"                          # inji-web → mimoto (issuer list UI)
    "http://localhost:9095/v1/verify/actuator/health"                  # verify-service
  )
  [[ "$MODE" == "b" ]] && urls+=("http://localhost:9080/realms/inji/.well-known/openid-configuration")

  for url in "${urls[@]}"; do
    printf "  waiting on %s " "$url"
    while ! curl -sf -o /dev/null "$url"; do
      if (( $(date +%s) > deadline )); then
        printf "%sTIMEOUT%s\n" "$RED" "$RST"
        die "service not healthy in 180s: $url" 2
      fi
      printf "."
      sleep 2
    done
    printf " %sok%s\n" "$GRN" "$RST"
  done

  if [[ "$MODE" == "b" ]]; then
    printf "  waiting on Mimoto issuer configuration (Keycloak well-known) "
    while true; do
      local cfg_http cfg_errs
      cfg_http=$(curl -sS -o /tmp/mimoto_cfg.json -w '%{http_code}' \
        http://localhost:4004/v1/mimoto/issuers/AITUniversity/configuration || echo 000)
      cfg_errs=$(jq -r '.errors | length' /tmp/mimoto_cfg.json 2>/dev/null || echo 1)
      if [[ "$cfg_http" == "200" && "$cfg_errs" == "0" ]]; then
        printf " %sok%s\n" "$GRN" "$RST"
        break
      fi
      if (( $(date +%s) > deadline )); then
        printf "%sTIMEOUT%s\n" "$RED" "$RST"
        die "Mimoto /configuration not healthy (HTTP $cfg_http) — RESIDENT-APP-042 usually means Mimoto cannot reach auth-server well-known (check keycloak nginx + certify authorization_servers URL)" 2
      fi
      printf "."
      sleep 2
    done
  fi
}

# -------- DID refresh (§11.3) --------
# All credential_config rows share one signing key (the keystore), so every row's
# did_url must match the live did:key derived from certify-nginx's /.well-known/did.json.
# This iterates every row and every csvdp-*.properties file so the script stays
# credential-type-agnostic as new VC types are added.
did_refresh() {
  step "did:key refresh (§11.3)"
  local new_pk new_did
  new_pk=$(curl -sf http://localhost:9091/.well-known/did.json | jq -r '.verificationMethod[0].publicKeyMultibase')
  [[ -n "$new_pk" && "$new_pk" != "null" ]] || die "could not read publicKeyMultibase from certify-nginx" 2
  new_did="did:key:$new_pk"

  # Pull every (key_id, did_url) pair so we know which rows need updating.
  local rows stale_rows=0
  rows=$(docker compose exec -T database 2>/dev/null psql -U postgres -d inji_certify -tAF $'\t' -c \
    "select credential_config_key_id, did_url from certify.credential_config;" | sed '/^$/d')

  if [[ -z "$rows" ]]; then
    warn "no rows in certify.credential_config — fresh init may not have run yet"
    return
  fi

  local restart_needed=0
  while IFS=$'\t' read -r key_id current_did; do
    current_did="${current_did// /}"
    if [[ "$current_did" == "$new_did" ]]; then
      skip "$key_id already matches ($new_did)"
    else
      say "  $key_id:  ${current_did:-<empty>}  →  $new_did"
      # </dev/null prevents docker exec from consuming the while-loop's here-string stdin.
      docker compose exec -T database 2>/dev/null psql -U postgres -d inji_certify -c \
        "update certify.credential_config set did_url='${new_did}' where credential_config_key_id='${key_id}';" </dev/null >/dev/null
      ok "updated $key_id.did_url in DB"
      stale_rows=$((stale_rows + 1))
      restart_needed=1
    fi
  done <<< "$rows"

  # Patch every csvdp-*.properties file so a future wipe seeds with the correct DID.
  for prop in config/certify-csvdp-*.properties; do
    [[ -f "$prop" ]] || continue
    if grep -q "^mosip.certify.data-provider-plugin.did-url=" "$prop"; then
      local cur_prop_did
      cur_prop_did=$(grep "^mosip.certify.data-provider-plugin.did-url=" "$prop" | head -1 | cut -d= -f2-)
      if [[ "$cur_prop_did" != "$new_did" ]]; then
        sed -i.bak "s|^mosip.certify.data-provider-plugin.did-url=.*$|mosip.certify.data-provider-plugin.did-url=${new_did}|" "$prop"
        rm -f "${prop}.bak"
        ok "patched $(basename "$prop")"
      fi
    fi
  done

  if (( restart_needed == 0 )); then
    ok "all rows already current — no restart needed"
    return
  fi

  docker compose restart certify >/dev/null
  ok "restarted certify ($stale_rows row(s) updated)"

  local recheck deadline
  deadline=$(( $(date +%s) + 60 ))
  until recheck=$(curl -sf http://localhost:9091/.well-known/did.json | jq -r '.verificationMethod[0].publicKeyMultibase'); do
    (( $(date +%s) <= deadline )) || die "certify did.json not available after restart" 2
    sleep 2
  done
  [[ "did:key:$recheck" == "$new_did" ]] || die "post-restart DID drifted: $recheck" 2
  ok "post-restart DID confirmed: $new_did"
}

# -------- validate --------
validate() {
  step "End-to-end validation"

  # Certify is auth-protected on /actuator/health — probe via certify-nginx's .well-known
  local certify_issuer verify_status mimoto_issuers
  certify_issuer=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer | jq -r '.credential_issuer // empty')
  [[ -n "$certify_issuer" ]] && ok "certify issuer metadata: $certify_issuer" || die "certify .well-known not serving" 2

  verify_status=$(curl -sf http://localhost:9095/v1/verify/actuator/health | jq -r '.status')
  [[ "$verify_status" == "UP" ]] && ok "verify-service: UP" || die "verify health: $verify_status" 2

  local verify_ui_api_url verify_ui_proxy_status
  verify_ui_api_url=$(curl -sf http://localhost:4007/env.config.js | awk -F'"' '/VERIFY_SERVICE_API_URL:/ {print $2; exit}')
  [[ "$verify_ui_api_url" == "/v1/verify" ]] \
    && ok "verify-ui API path: $verify_ui_api_url" \
    || die "verify-ui VERIFY_SERVICE_API_URL must be /v1/verify (got: ${verify_ui_api_url:-<empty>})" 2

  verify_ui_proxy_status=$(curl -sf http://localhost:4007/v1/verify/actuator/health | jq -r '.status')
  [[ "$verify_ui_proxy_status" == "UP" ]] \
    && ok "verify-ui proxy: /v1/verify -> verify-service" \
    || die "verify-ui /v1/verify proxy unhealthy: $verify_ui_proxy_status" 2

  mimoto_issuers=$(curl -sf http://localhost:9099/v1/mimoto/issuers | jq -r '.response.issuers[].issuer_id' | paste -sd, -)
  [[ -n "$mimoto_issuers" ]] && ok "mimoto issuers: $mimoto_issuers" || die "mimoto issuers empty" 2

  local expected_student_context student_context student_metadata_context
  expected_student_context="$LOCAL_STUDENT_CONTEXT_URL,https://www.w3.org/ns/credentials/v2"
  student_context=$(docker compose exec -T database 2>/dev/null psql -U postgres -d inji_certify -tAc \
    "select context from certify.credential_config where credential_config_key_id='ait-transcript';" \
    | tr -d '[:space:]')
  [[ "$student_context" == "$expected_student_context" ]] \
    && ok "ait-transcript DB context order matches QR signing lookup" \
    || die "ait-transcript context must be '$expected_student_context' (got: ${student_context:-<empty>})" 2

  student_metadata_context=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer | jq -r \
    '.credential_configurations_supported["ait-transcript"].credential_definition["@context"] | join(",")')
  [[ "$student_metadata_context" == "$expected_student_context" ]] \
    && ok "ait-transcript issuer metadata context order aligned" \
    || die "ait-transcript issuer metadata context mismatch: ${student_metadata_context:-<empty>}" 2

  if [[ "$MODE" == "b" ]]; then
    local kc_iss expected_kc_iss auth_endpoint expected_auth_prefix
    kc_iss=$(curl -sf http://localhost:9080/realms/inji/.well-known/openid-configuration | jq -r '.issuer')
    expected_kc_iss="http://keycloak:8080/realms/inji"
    [[ "$kc_iss" == "$expected_kc_iss" ]] && ok "keycloak realm: $kc_iss (browser :9080, token aud via keycloak:8080)" || die "keycloak issuer wrong: $kc_iss (expected $expected_kc_iss)" 2
    # The browser-facing Keycloak base: KEYCLOAK_PUBLIC_BASE_URL from .env on a
    # public deploy, http://localhost:9080 locally (keycloak_expected_issuer).
    expected_auth_prefix="$(keycloak_expected_issuer)/"
    auth_endpoint=$(curl -sS http://localhost:4004/v1/mimoto/issuers/AITUniversity/configuration | jq -r '.response.authorization_endpoint // empty')
    [[ -n "$auth_endpoint" ]] \
      && [[ "$auth_endpoint" == "$expected_auth_prefix"* ]] \
      && ok "mimoto issuer configuration auth URL is browser-reachable ($auth_endpoint)" \
      || die "mimoto authorization_endpoint must start with $expected_auth_prefix (got: ${auth_endpoint:-<empty>})" 2
  fi

  # Final DID consistency check — every row in credential_config must match the live key.
  local live_did mismatches
  live_did="did:key:$(curl -sf http://localhost:9091/.well-known/did.json | jq -r '.verificationMethod[0].publicKeyMultibase')"
  mismatches=$(docker compose exec -T database 2>/dev/null psql -U postgres -d inji_certify -tAc \
    "select credential_config_key_id || '=' || coalesce(did_url,'<null>') from certify.credential_config where did_url is distinct from '${live_did}';" \
    | sed '/^$/d')
  if [[ -z "$mismatches" ]]; then
    ok "DID consistency: $live_did (all rows aligned)"
  else
    say "  live signing key: $live_did"
    while IFS= read -r row; do say "    drift: $row"; done <<< "$mismatches"
    die "DID mismatch — run with --did-refresh" 2
  fi

  printf "\n%sStack is healthy.%s\n" "$BOLD$GRN" "$RST"
  say "  Inji Web (holder wallet):  http://localhost:4004"
  say "  Inji Verify UI:            http://localhost:4007"
  say "  Demo app (student/registrar): http://localhost:4100"
  [[ "$MODE" == "b" ]] && say "  Keycloak (admin/admin):    http://localhost:9080"
  say "  Login (Mode B):            user ait-2026-0001 / password inji"
}

# -------- main --------
main() {
  if (( ONLY_VALIDATE )); then validate; exit 0; fi
  if (( ONLY_DID ));      then did_refresh; validate; exit 0; fi

  preflight
  (( DO_WIPE )) && do_wipe
  gen_env
  ensure_keycloak_env
  gen_network
  gen_keystore
  gen_client_cert
  sync_realm_cert
  configure_mode
  compose_up
  wait_healthy
  did_refresh
  validate
}

main "$@"
