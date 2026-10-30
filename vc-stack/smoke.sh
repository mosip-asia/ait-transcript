#!/usr/bin/env bash
# Automated smoke checks for Phase 1 (curl/jq). Run from vc-stack/ after bootstrap.
# The same script for every installation: what differs comes from installations/$INSTALLATION (the stand-in realm and
# the Mimoto issuer id, set by installation.sh, the Authorization Server settings, which must name the stand-in, and smoke.json: a list with one entry per credential type, each with the
# credential configuration, its scope, the eligible persona (or a list of them), each refused persona with the check it fails, the claims
# to tamper and, optionally, the Mimoto PDF template). Every issued, refused and tampered case runs for every type.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"
source "$STACK_DIR/installation.sh"
load_auth_server_settings

FIXTURES="$INSTALLATION_DIR/smoke.json"
fixture() { jq -r "$1" "$FIXTURES"; }
TYPE_COUNT=$(fixture length)
ALL_CONFIGS=$(fixture '[.[].credentialConfig] | sort | join(" ")')
# Sets the variables the per-type checks read from the i-th entry of smoke.json.
load_type() {
  local entry=".[$1]"
  CONFIG=$(fixture "$entry.credentialConfig")
  SCOPE=$(fixture "$entry.scope")
  # One eligible persona, or a list of them; ${ELIGIBLE[0]} is the first.
  mapfile -t ELIGIBLE < <(fixture "$entry.eligible | if type == \"array\" then .[] else . end")
  mapfile -t REFUSED < <(fixture "$entry.refused | keys_unsorted[]")
  mapfile -t TAMPER < <(fixture "$entry.tamper[]")
  MIMOTO_TEMPLATE=$(fixture "$entry.mimotoTemplate // empty")
  # The claims the Gateway answers for the scope, which Certify's metadata must list: the record model's fields and the
  # derived claims (gateway/credential_types.py), read in the gateway image, which carries pydantic.
  CLAIMS=$(docker compose run --rm --no-deps -T gateway python -c "import sys, credential_types as ct
t = ct.REGISTRY[sys.argv[1]]; print('\n'.join([*t.record.model_fields, *t.derived]))" "$SCOPE")
  # The context on the VDR's /contexts/ that the configuration names (the research note's Compose check, step 2).
  ctx_url=$(jq -r --arg c "$CONFIG" '[.credential_configurations_supported[$c].credential_definition["@context"][] | select(contains("/contexts/"))][0] // empty' <<<"$issuer_json")
}

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

sorted_lines() {
  sort | awk 'NF'
}

python3 "$REPO_ROOT/data/generate_csv.py" >/dev/null

issuer_json=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer) \
  || fail "certify issuer metadata not reachable on :9091"

configs=$(echo "$issuer_json" | jq -r '.credential_configurations_supported | keys | sort | join(" ")')
[[ "$configs" == "$ALL_CONFIGS" ]] || fail "expected exactly the credential configs $ALL_CONFIGS, got: $configs"

for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  got_claims=$(echo "$issuer_json" | jq -r --arg c "$CONFIG" '.credential_configurations_supported[$c].credential_definition.credentialSubject | keys[]' | sorted_lines)
  want_claims=$(sorted_lines <<<"$CLAIMS")
  [[ "$got_claims" == "$want_claims" ]] || fail "issuer metadata claim names for $CONFIG differ from the Gateway's for $SCOPE"
  ok "issuer lists $CONFIG with the Gateway's claims for $SCOPE"
done

auth_srv=$(echo "$issuer_json" | jq -r '.authorization_servers[0] // empty')
[[ "$auth_srv" == "$AUTH_SERVER_ISSUER" ]] \
  || fail "Certify authorization_servers must be AUTH_SERVER_ISSUER, $AUTH_SERVER_ISSUER (got: ${auth_srv:-<empty>})"
ok "Certify OID4VCI authorization_servers name the configured issuer $AUTH_SERVER_ISSUER"

# The Compose check of wiki/research/certify-json-literal.md section 4 runs below: step 2 here, steps 3 to 5
# after issuance, step 1 (library versions) printed for the record.
for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  [[ -n "$ctx_url" ]] || fail "$CONFIG @context names no context on the VDR's /contexts/"
  ctx_path="${ctx_url#*/contexts/}"
  served_ctx=$(curl -sf "http://localhost:9098/contexts/$ctx_path") \
    || fail "public gateway does not serve /contexts/$ctx_path (vdr container)"
  [[ "$(jq -S . <<<"$served_ctx")" == "$(jq -S . "$REPO_ROOT/vc-lab/contexts/$ctx_path")" ]] \
    || fail "served context differs from vc-lab/contexts/$ctx_path"
  ok "context $ctx_path served by the VDR through the public gateway"
done

csv_file="$INSTALLATION_DIR/adapter/student_identity_data.csv"
kc_users=$(jq -r '.users[].username' "$INSTALLATION_DIR/keycloak-realm.json" | sorted_lines)
csv_ids=$(python3 -c "import csv, sys; from pathlib import Path
p=Path(sys.argv[1])
with p.open(newline='', encoding='utf-8') as f:
  print('\n'.join(sorted(r['id'] for r in csv.DictReader(f))))" "$csv_file")
[[ "$kc_users" == "$csv_ids" ]] || fail "Keycloak usernames must match CSV id column row-for-row"
ok "Keycloak users align with CSV ids"

# Certify's data provider is the Gateway plugin, configured by the six keys of contracts.md section 2a and nothing else.
certify_props=$(tr -d '\r' <"$INSTALLATION_DIR/certify-csvdp-student.properties")
plugin_keys=$( (grep -oE '^mosip\.certify\.(gateway\.[a-z-]+|integration\.(data-provider-plugin|scan-base-package))=' <<<"$certify_props" || true) \
  | tr -d = | LC_ALL=C sort)
want_keys=$(printf '%s\n' mosip.certify.gateway.{auth-token,connect-timeout-ms,read-timeout-ms,url} \
  mosip.certify.integration.{data-provider-plugin,scan-base-package} | LC_ALL=C sort)
[[ "$plugin_keys" == "$want_keys" ]] || fail "Certify's plugin keys must be the six of contracts.md section 2a (got: $plugin_keys)"
! grep -q '^mosip\.certify\.mock\.data-provider\.' <<<"$certify_props" || fail "the CSV plugin's keys are still in Certify's properties"
[[ "$(grep '^mosip.certify.gateway.auth-token=' <<<"$certify_props")" == \
   "mosip.certify.gateway.auth-token=$(tr -d '\r' <"$INSTALLATION_DIR/gateway.env" | grep '^GATEWAY_AUTH_TOKEN=' | cut -d= -f2-)" ]] \
  || fail "mosip.certify.gateway.auth-token must equal GATEWAY_AUTH_TOKEN in gateway.env"
ok "Certify's plugin configuration is the six keys; its token is the Gateway's"

for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  if [[ -n "$MIMOTO_TEMPLATE" ]]; then
    [[ -f "config/$MIMOTO_TEMPLATE" ]] || fail "missing Mimoto PDF template config/$MIMOTO_TEMPLATE"
    ok "Mimoto template filename $MIMOTO_TEMPLATE present"
  fi
done

before=$(docker compose ps -q | wc -l | tr -d ' ')
docker compose up -d >/dev/null
after=$(docker compose ps -q | wc -l | tr -d ' ')
[[ "$after" -ge "$before" ]] || fail "bootstrap re-run reduced container count"
ok "bootstrap idempotent re-run"

# The plugin jar joins the four bundled ones (a single-file mount), and Certify started with it selected.
certify_jars=$(docker compose exec -T certify ls /home/inji/additional_jars/ | tr -d '\r') \
  || fail "cannot list Certify's additional_jars/"
for jar in gateway-data-provider-plugin mock-certify-plugin sunbird-rc-certify-integration-impl \
  postgres-dataprovider-plugin mosip-identity-certify-plugin; do
  grep -qE "^$jar.*\.jar$" <<<"$certify_jars" || fail "additional_jars/ lacks $jar (has: $(tr '\n' ' ' <<<"$certify_jars"))"
done
certify_log=$(docker compose logs --no-color certify 2>&1) || fail "cannot read the certify log"
! grep -qE 'NoSuchBeanDefinitionException|NoUniqueBeanDefinitionException' <<<"$certify_log" \
  || fail "missing-bean or duplicate-bean error in the certify log"
grep -q 'GatewayDataProviderPlugin selected' <<<"$certify_log" || fail "the certify log does not name GatewayDataProviderPlugin"
ok "Certify loads the Gateway plugin beside the four bundled jars"

issuer=$(curl -sf "http://localhost:9080/realms/$REALM/.well-known/openid-configuration" | jq -r '.issuer')
[[ "$issuer" == "$AUTH_SERVER_ISSUER" ]] || fail "the stand-in realm $REALM must be the configured issuer $AUTH_SERVER_ISSUER (got: ${issuer:-<empty>})"
ok "Keycloak OIDC issuer aligned for Mimoto token aud"

auth_endpoint=$(curl -sf "http://localhost:4004/v1/mimoto/issuers/$ISSUER_ID/configuration" | jq -r '.response.authorization_endpoint // empty')
[[ "$auth_endpoint" == "$AUTH_SERVER_PUBLIC_URL"/* ]] \
  || fail "Inji Web auth URL must be $AUTH_SERVER_PUBLIC_URL/... (got: ${auth_endpoint:-<empty>})"
ok "Mimoto exposes browser Keycloak auth URL for Inji Web"

config_errors=$(curl -sf "http://localhost:4004/v1/mimoto/issuers/$ISSUER_ID/configuration" | jq -r '.errors | length')
cred_count=$(curl -sf "http://localhost:4004/v1/mimoto/issuers/$ISSUER_ID/configuration" | jq -r '.response.credentials_supported | length')
[[ "$config_errors" == "0" && "$cred_count" == "$TYPE_COUNT" ]] \
  || fail "issuer configuration must list the $TYPE_COUNT credential types of smoke.json (errors=$config_errors, credentials_supported=$cred_count) — Keycloak well-known via keycloak:8080 often 502 until keycloak nginx reload"
ok "Mimoto issuer configuration lists the $TYPE_COUNT credential types of smoke.json for Inji Web"

token_ep=$(curl -sf "http://localhost:4004/v1/mimoto/issuers/$ISSUER_ID" | jq -r '.response.token_endpoint // empty')
[[ "$token_ep" == http://localhost:4004/v1/mimoto/get-token/* ]] \
  || fail "issuer token_endpoint must use Inji Web proxy :4004 (got: ${token_ep:-<empty>}) — run bootstrap configure_mode"
ok "Issuer token_endpoint uses Inji Web same-origin :4004"

auth_aud=$(curl -sf "http://localhost:4004/v1/mimoto/issuers/$ISSUER_ID" | jq -r '.response.authorization_audience // empty')
[[ "$auth_aud" == "$AUTH_SERVER_TOKEN_ENDPOINT" ]] \
  || fail "authorization_audience must be AUTH_SERVER_TOKEN_ENDPOINT, $AUTH_SERVER_TOKEN_ENDPOINT (got: ${auth_aud:-<empty>})"
ok "Issuer authorization_audience is the configured token endpoint"

# The mock adapter answers contract 2b's three paths and a 404, and serves an edited CSV value at once. The edit
# case runs on a copy of the CSV served by a second adapter container, so the installation's file is never rewritten.
adapter_copy_dir="$REPO_ROOT/.demo-state/adapter-copy"
rm -rf "$adapter_copy_dir" && mkdir -p "$adapter_copy_dir"
cp "$csv_file" "$adapter_copy_dir/student_identity_data.csv"
docker rm -f adapter-copy >/dev/null 2>&1 || true
docker compose run -d --no-deps --name adapter-copy -e ADAPTER_CSV=/copy/student_identity_data.csv \
  -v "$adapter_copy_dir:/copy:ro" adapter >/dev/null || fail "cannot start a second adapter on a copy of the CSV"
adapter_rc=0
docker compose run --rm --no-deps -T \
  -v "$STACK_DIR/../adapter/test_adapter.py:/demo/adapter/test_adapter.py:ro" \
  demo-app python adapter/test_adapter.py http://adapter:8000 \
  "/demo/installations/$INSTALLATION/adapter/student_identity_data.csv" \
  http://adapter-copy:8000 /demo/.demo-state/adapter-copy/student_identity_data.csv || adapter_rc=$?
docker rm -f adapter-copy >/dev/null 2>&1 || true
rm -rf "$adapter_copy_dir"
[[ "$adapter_rc" == 0 ]] || fail "mock adapter (adapter/test_adapter.py)"
ok "mock adapter serves the degree list, the record and the eligibility attributes, and an edited value at once"

# The Gateway answers contract 2a's cases with the mock adapter beside it and writes one issuance row per 200.
# Run from the gateway image (httpx, psycopg), whose environment carries the token and the database URL.
docker compose run --rm --no-deps -T \
  -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" \
  -v "$INSTALLATION_DIR:/installation:ro" \
  gateway python tests/test_issuances.py http://gateway:8000 /installation/adapter/student_identity_data.csv \
  /installation/smoke.json \
  || fail "Gateway (gateway/tests/test_issuances.py)"
ok "Gateway: 200, 403 per failing check, 404, 400, 401, one issuance row per 200"

load_type 0  # the adapter-down and Gateway-down checks below run for the first type

# An adapter failure during a request is a Gateway error (502), not a crash. The adapter is restarted
# whether or not the check passes, so later steps still see it.
docker compose stop adapter >/dev/null || fail "cannot stop the adapter"
adapter_down_rc=0
docker compose run --rm --no-deps -T -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" -v "$FIXTURES:/smoke.json:ro" \
  gateway python tests/test_issuances.py adapter-down http://gateway:8000 /smoke.json || adapter_down_rc=$?
docker compose start adapter >/dev/null || fail "cannot restart the adapter"
adapter_up=0
for _ in $(seq 1 30); do
  if docker compose run --rm --no-deps -T gateway python -c     "import httpx; httpx.get('http://adapter:8000/students/${ELIGIBLE[0]}/eligibility', timeout=3).raise_for_status()" >/dev/null 2>&1; then
    adapter_up=1; break
  fi
  sleep 2
done
[[ "$adapter_up" == 1 ]] || fail "adapter did not answer again after restart"
[[ "$adapter_down_rc" == 0 ]] || fail "Gateway with the adapter down must answer 502 gateway_error (gateway/tests/test_issuances.py adapter-down)"
ok "Gateway: adapter down is a 502 gateway_error, and the adapter is back"

# Scripted issuance, then verification with a tampered copy, inside the Docker network (see the script's docstring).
issue_and_verify() {
  docker compose run --rm --no-deps -T \
    -v "$STACK_DIR/issue_and_verify.py:/demo/vc-stack/issue_and_verify.py:ro" \
    demo-app python vc-stack/issue_and_verify.py "$@"
}
issuance_rows() {
  docker compose exec -T database psql -U postgres -d inji_certify -tAc "select count(*) from gateway.issuances"     | tr -d '[:space:]'
}
for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  # One file per type, kept as a CI artifact; with several eligible personas it holds the last one's credential.
  smoke_vc=".demo-state/smoke-credential-$CONFIG.json"
  for persona in "${ELIGIBLE[@]}"; do
    rows_before=$(issuance_rows) || fail "cannot count gateway.issuances"
    issue_and_verify issue "$INSTALLATION" "$persona" "$SCOPE" "$smoke_vc" \
      || fail "scripted issuance of $CONFIG to $persona (vc-stack/issue_and_verify.py issue)"
    jq -e --arg u "$ctx_url" '."@context" | index($u)' "$REPO_ROOT/$smoke_vc" >/dev/null \
      || fail "issued credential does not name $ctx_url in its @context"
    issue_and_verify verify "$smoke_vc" "${TAMPER[@]}" || fail "verification of $CONFIG for $persona (vc-stack/issue_and_verify.py verify)"
    rows_issued=$(issuance_rows) || fail "cannot count gateway.issuances"
    [[ "$rows_issued" == "$((rows_before + 1))" ]] \
      || fail "the Certify-path issuance of $CONFIG to $persona must add one gateway.issuances row (before: $rows_before, after: $rows_issued)"
    ok "the Certify-path issuance of $CONFIG to $persona wrote one gateway.issuances row"
  done

  # Each persona the Gateway's checklist refuses gets the OpenID4VCI error body with its code.
  for persona in "${REFUSED[@]}"; do
    issue_and_verify refused "$INSTALLATION" "$persona" "$SCOPE" checklist_failed \
      || fail "refused persona $persona for $CONFIG through Certify (vc-stack/issue_and_verify.py refused ... checklist_failed)"
  done
  rows_refused=$(issuance_rows) || fail "cannot count gateway.issuances"
  [[ "$rows_refused" == "$rows_issued" ]] \
    || fail "the refused personas of $CONFIG must add no gateway.issuances row (before: $rows_issued, after: $rows_refused)"
  ok "the refused personas of $CONFIG wrote no gateway.issuances row"
done

# With the Gateway down, Certify still starts (the plugin calls nothing at startup) and a credential request is
# gateway_error. The Gateway is started again whether or not the checks pass, so later steps still see it.
docker compose stop gateway >/dev/null || fail "cannot stop the Gateway"
docker compose restart certify >/dev/null || fail "cannot restart certify"
retry() { local tries=$1; shift; for _ in $(seq 1 "$tries"); do "$@" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
certify_up=0
retry 90 curl -sf http://localhost:9091/.well-known/openid-credential-issuer && certify_up=1
gateway_down_rc=1
if [[ "$certify_up" == 1 ]]; then
  gateway_down_rc=0
  issue_and_verify refused "$INSTALLATION" "${ELIGIBLE[0]}" "$SCOPE" gateway_error || gateway_down_rc=$?
fi
docker compose start gateway >/dev/null || fail "cannot restart the Gateway"
[[ "$certify_up" == 1 ]] || fail "Certify did not start while the Gateway was down"
[[ "$gateway_down_rc" == 0 ]] || fail "with the Gateway down a credential request must be refused with gateway_error"
retry 30 docker compose exec -T gateway python -c \
  "import httpx; httpx.get('http://gateway:8000/docs', timeout=3).raise_for_status()" \
  || fail "the Gateway did not answer again after restart"
ok "Certify starts with the Gateway down and then answers gateway_error; the Gateway is back"

stack_logs=$(docker compose logs --no-color certify verify-service 2>&1) || fail "cannot read the certify and verify-service logs"
context_warnings=$(grep -E 'Cannot load context|is not an absolute IRI nor @json' <<<"$stack_logs" | head -5 || true)
[[ -z "$context_warnings" ]] || fail "JSON-LD context warnings in the certify or verify-service log: $context_warnings"
ok "no context-loading or datatype warnings in the certify and verify-service logs"

# Step 1: the JSON-LD libraries each image carries must be the ones the research note's section 4 expects.
jsonld_libs() {
  docker compose exec -T "$1" unzip -l "/home/inji/$2.jar" 2>/dev/null | tr -d '\r' \
    | grep -oE 'BOOT-INF/lib/(jsonld|titanium|rdf-urdna|ld-signatures)[^/]*\.jar$' \
    | sed 's|.*/||' | sort | tr '\n' ' ' | sed 's/ $//'
}
assert_jsonld_libs() {
  local svc="$1" found="$2" jar missing=""
  shift 2
  for jar in "$@"; do
    grep -qxF "$jar" <<<"${found// /$'\n'}" || missing="$missing $jar"
  done
  [[ -z "$missing" ]] || fail "$svc JSON-LD libraries: missing${missing}; found: ${found:-nothing}"
  if grep -qE '(^| )jsonld-java-' <<<"$found"; then
    fail "$svc carries a jsonld-java jar; found: $found"
  fi
  ok "$svc JSON-LD libraries as expected: $found"
}
certify_libs=$(jsonld_libs certify certify-service || echo unreadable)
assert_jsonld_libs certify "$certify_libs" titanium-json-ld-1.6.0.jar titanium-jcs-1.0.0.jar titanium-rdfc-2.0.0.jar \
  jsonld-common-java-1.14.0.jar rdf-urdna-1.4.jar
verify_libs=$(jsonld_libs verify-service verify-service || echo unreadable)
assert_jsonld_libs verify-service "$verify_libs" titanium-json-ld-1.3.2.jar titanium-json-ld-jre8-1.3.1.jar \
  jsonld-common-java-1.8.0.jar rdf-urdna-1.2.jar ld-signatures-java-1.11.0.jar

python3 "$STACK_DIR/test_inji_web_vc_readiness.py" --live

echo "All smoke checks passed."
