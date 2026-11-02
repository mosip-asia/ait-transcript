#!/usr/bin/env bash
# Automated smoke checks for Phase 1 (curl/jq). Run from vc-stack/ after bootstrap.
# The same script for every installation: what differs comes from installations/$INSTALLATION (the stand-in realm and
# the Mimoto issuer id, set by installation.sh, the Authorization Server settings, which must name the stand-in, and smoke.json: a list with one entry per credential type, each with the
# credential configuration, its scope, the eligible persona (or a list of them), each refused persona with the check it fails, the claims
# to tamper and, optionally, the Mimoto PDF template). Every issued, refused and tampered case runs for every type.
# Without the Gateway (COMPOSE_FILE=compose-no-gateway.yaml, as run-demo.sh took it), the refused personas are issued
# too, the unknown one is still no_record, and the Adapter stopped is adapter_error instead of the Gateway's checks.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"
source "$STACK_DIR/installation.sh"
load_auth_server_settings

FIXTURES="$INSTALLATION_DIR/smoke.json"
source "$STACK_DIR/issuer-checks.sh"
fixture() { jq -r "$1" "$FIXTURES"; }
TYPE_COUNT=$(fixture length)
# Sets the variables the per-type checks read from the i-th entry of smoke.json.
load_type() {
  local entry=".[$1]"
  CONFIG=$(fixture "$entry.credentialConfig")
  SCOPE=$(fixture "$entry.scope")
  # One eligible persona, or a list of them; ${ELIGIBLE[0]} is the first.
  mapfile -t ELIGIBLE < <(fixture "$entry.eligible | if type == \"array\" then .[] else . end")
  mapfile -t REFUSED < <(fixture "$entry.refused | keys_unsorted[]")
  UNKNOWN=$(fixture "$entry.unknown")
  mapfile -t TAMPER < <(fixture "$entry.tamper[]")
  MIMOTO_TEMPLATE=$(fixture "$entry.mimotoTemplate // empty")
  # The context under /contexts/ that the configuration names, which every credential issued for it must carry.
  ctx_url=$(jq -r --arg c "$CONFIG" '[.credential_configurations_supported[$c].credential_definition["@context"][] | select(contains("/contexts/"))][0] // empty' <<<"$issuer_json")
}

sorted_lines() {
  sort | awk 'NF'
}

python3 "$REPO_ROOT/data/generate_csv.py" >/dev/null

# The Issuer's own checks first, as issuer-smoke.sh runs them (issuer-checks.sh): the Data-provider plugin in Certify's
# log, the issuer metadata against the Adapter contract's record schemas, the contexts through certify-nginx, and with
# the gate on every persona through the Gateway and 502 with the adapter down. They leave Certify's metadata in
# issuer_json.
issuer_checks

auth_srv=$(echo "$issuer_json" | jq -r '.authorization_servers[0] // empty')
[[ "$auth_srv" == "$AUTH_SERVER_ISSUER" ]] \
  || fail "Certify authorization_servers must be AUTH_SERVER_ISSUER, $AUTH_SERVER_ISSUER (got: ${auth_srv:-<empty>})"
ok "Certify OID4VCI authorization_servers name the configured issuer $AUTH_SERVER_ISSUER"

# The context check of wiki/concepts/transcript-context.md ("How it is checked"): the contexts here, issuance and the
# tampered copies below, then the log warnings and the JSON-LD library versions.
check_contexts http://localhost:9098 "the public gateway"

csv_file="$INSTALLATION_DIR/adapter/student_identity_data.csv"
# Every realm user but the smoke's unknown persona, which signs in and has no record.
kc_users=$(jq -r --slurpfile smoke "$FIXTURES" '[$smoke[0][].unknown] as $unknown | .users[].username
  | select(. as $u | $unknown | index($u) | not)' "$INSTALLATION_DIR/keycloak-realm.json" | sorted_lines)
csv_ids=$(python3 -c "import csv, sys; from pathlib import Path
p=Path(sys.argv[1])
with p.open(newline='', encoding='utf-8') as f:
  print('\n'.join(sorted(r['id'] for r in csv.DictReader(f))))" "$csv_file")
[[ "$kc_users" == "$csv_ids" ]] || fail "Keycloak usernames but the unknown persona's must match CSV id column row-for-row"
ok "Keycloak users align with CSV ids, and the unknown persona signs in with no row"

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

# The plugin jar joins the four bundled ones (a single-file mount); issuer_checks saw Certify start with it selected.
certify_jars=$(docker compose exec -T certify ls /home/inji/additional_jars/ | tr -d '\r') \
  || fail "cannot list Certify's additional_jars/"
for jar in issuer-data-provider-plugin mock-certify-plugin sunbird-rc-certify-integration-impl \
  postgres-dataprovider-plugin mosip-identity-certify-plugin; do
  grep -qE "^$jar.*\.jar$" <<<"$certify_jars" || fail "additional_jars/ lacks $jar (has: $(tr '\n' ' ' <<<"$certify_jars"))"
done
ok "Certify's additional_jars/ holds the Data-provider plugin beside the four bundled jars"

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

# The mock adapter answers the Adapter contract's three /records paths and a 404 on each, and serves an edited CSV
# value at once. The edit case runs on a copy of the CSV served by a second adapter container, so the installation's
# file is never rewritten.
adapter_copy_dir="$REPO_ROOT/.demo-state/adapter-copy"
rm -rf "$adapter_copy_dir" && mkdir -p "$adapter_copy_dir"
cp "$csv_file" "$adapter_copy_dir/student_identity_data.csv"
docker rm -f adapter-copy >/dev/null 2>&1 || true
docker compose run -d --no-deps --name adapter-copy -e ADAPTER_CSV=/copy/student_identity_data.csv \
  -v "$adapter_copy_dir:/copy:ro" adapter >/dev/null || fail "cannot start a second adapter on a copy of the CSV"
adapter_test() {
  docker compose run --rm --no-deps -T -v "$STACK_DIR/../adapter:/demo/adapter:ro" demo-app python adapter/test_adapter.py "$@"
}
adapter_rc=0
adapter_test http://adapter:8000 "/demo/installations/$INSTALLATION/adapter/student_identity_data.csv" \
  http://adapter-copy:8000 /demo/.demo-state/adapter-copy/student_identity_data.csv || adapter_rc=$?
docker rm -f adapter-copy >/dev/null 2>&1 || true
rm -rf "$adapter_copy_dir"
[[ "$adapter_rc" == 0 ]] || fail "mock adapter (adapter/test_adapter.py)"
ok "mock adapter serves the three /records paths, a 404 on each for an unknown student, and an edited value at once"

# The contract mode (adapter/openapi.yaml), as any Adapter is checked: every type's first eligible persona.
for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  adapter_test --contract http://adapter:8000 "${ELIGIBLE[0]}" "$SCOPE" \
    || fail "the mock adapter fails the Adapter contract for $SCOPE (adapter/test_adapter.py --contract)"
  ok "the mock adapter passes the Adapter contract for $SCOPE"
done

load_type 0  # the Gateway-down (gate on) or Adapter-down (gate off) check below runs for the first type

# Scripted issuance, then verification with a tampered copy, inside the Docker network (see the script's docstring).
issue_and_verify() {
  docker compose run --rm --no-deps -T \
    -v "$STACK_DIR/issue_and_verify.py:/demo/vc-stack/issue_and_verify.py:ro" \
    demo-app python vc-stack/issue_and_verify.py "$@"
}
# Certify's ledger: one row per issued credential, its indexed attributes holding the plugin's trace keys.
ledger_rows() {
  docker compose exec -T database psql -U postgres -d inji_certify -tAc "select count(*) from certify.ledger" | tr -d '[:space:]'
}
last_ledger_trace() {
  docker compose exec -T database psql -U postgres -d inji_certify -tAc \
    "select coalesce(indexed_attributes->>'tokenSub', '<none>') || ' ' || coalesce(indexed_attributes->>'tokenClientId', '<none>')
     from certify.ledger order by id desc limit 1" | tr -d '\r'
}
# The client_id claim the realm's test-only smoke client puts in its tokens, which the plugin traces as tokenClientId.
smoke_client_id=$(jq -r '.clients[] | select(.clientId == "smoke") | .protocolMappers[]
  | select(.config["claim.name"] == "client_id") | .config["claim.value"]' "$INSTALLATION_DIR/keycloak-realm.json")
[[ -n "$smoke_client_id" ]] || fail "the realm's smoke client sets no client_id claim"
for ((i = 0; i < TYPE_COUNT; i++)); do
  load_type "$i"
  # One file per type, kept as a CI artifact; with several issued personas it holds the last one's credential.
  smoke_vc=".demo-state/smoke-credential-$CONFIG.json"
  # With the gate off nothing evaluates the Checklist, so the personas it refuses are issued too.
  issued=("${ELIGIBLE[@]}")
  [[ "$GATE_ENABLED" == true ]] || issued+=("${REFUSED[@]}")
  for persona in "${issued[@]}"; do
    rows_before=$(ledger_rows) || fail "cannot count certify.ledger"
    issue_and_verify issue "$INSTALLATION" "$persona" "$SCOPE" "$smoke_vc" \
      || fail "scripted issuance of $CONFIG to $persona (vc-stack/issue_and_verify.py issue)"
    jq -e --arg u "$ctx_url" '."@context" | index($u)' "$REPO_ROOT/$smoke_vc" >/dev/null \
      || fail "issued credential does not name $ctx_url in its @context"
    jq -e '[paths | .[-1] | strings] | any(. == "tokenSub" or . == "tokenClientId") | not' "$REPO_ROOT/$smoke_vc" >/dev/null \
      || fail "the credential of $CONFIG for $persona carries a trace key (tokenSub, tokenClientId)"
    issue_and_verify verify "$smoke_vc" "${TAMPER[@]}" || fail "verification of $CONFIG for $persona (vc-stack/issue_and_verify.py verify)"
    rows_issued=$(ledger_rows) || fail "cannot count certify.ledger"
    [[ "$rows_issued" == "$((rows_before + 1))" ]] \
      || fail "the issuance of $CONFIG to $persona must add one certify.ledger row (before: $rows_before, after: $rows_issued)"
    trace=$(last_ledger_trace) || fail "cannot read certify.ledger"
    [[ "$trace" == "$persona $smoke_client_id" ]] \
      || fail "the ledger row of $CONFIG for $persona must index tokenSub=$persona tokenClientId=$smoke_client_id (got: $trace)"
    ok "the issuance of $CONFIG to $persona added one ledger row indexing tokenSub and tokenClientId; the credential carries neither"
  done

  # With the gate on, each persona the Gateway's checklist refuses gets the OpenID4VCI error body with its code.
  if [[ "$GATE_ENABLED" == true ]]; then
    for persona in "${REFUSED[@]}"; do
      issue_and_verify refused "$INSTALLATION" "$persona" "$SCOPE" checklist_failed \
        || fail "refused persona $persona for $CONFIG through Certify (vc-stack/issue_and_verify.py refused ... checklist_failed)"
    done
  fi
  # The unknown persona signs in, but the Adapter has no record of it: no_record, with the gate on or off.
  issue_and_verify refused "$INSTALLATION" "$UNKNOWN" "$SCOPE" no_record \
    || fail "unknown persona $UNKNOWN for $CONFIG through Certify (vc-stack/issue_and_verify.py refused ... no_record)"
  rows_refused=$(ledger_rows) || fail "cannot count certify.ledger"
  [[ "$rows_refused" == "$rows_issued" ]] \
    || fail "the refused personas of $CONFIG must add no certify.ledger row (before: $rows_issued, after: $rows_refused)"
  ok "the refused personas of $CONFIG added no ledger row"
done

if [[ "$GATE_ENABLED" == true ]]; then
  # With the Gateway down, Certify still starts (the plugin calls nothing at startup) and a credential request is
  # gateway_error. The Gateway is started again whether or not the checks pass, so later steps still see it.
  docker compose stop gateway >/dev/null || fail "cannot stop the Gateway"
  docker compose restart certify >/dev/null || fail "cannot restart certify"
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
  retry 30 in_network http://gateway:8000/docs || fail "the Gateway did not answer again after restart"
  ok "Certify starts with the Gateway down and then answers gateway_error; the Gateway is back"
else
  # With the gate off the Adapter is the plugin's only peer: stopped, a credential request is adapter_error. It is
  # started again whether or not the check passes, and answers again before the next step.
  docker compose stop adapter >/dev/null || fail "cannot stop the adapter"
  adapter_down_rc=0
  issue_and_verify refused "$INSTALLATION" "${ELIGIBLE[0]}" "$SCOPE" adapter_error || adapter_down_rc=$?
  docker compose start adapter >/dev/null || fail "cannot restart the adapter"
  [[ "$adapter_down_rc" == 0 ]] || fail "with the gate off and the Adapter down a credential request must be refused with adapter_error"
  retry 30 in_network http://adapter:8000/docs || fail "the adapter did not answer again after restart"
  ok "with the gate off and the Adapter down a credential request is adapter_error; the adapter is back"
fi

stack_logs=$(docker compose logs --no-color certify verify-service 2>&1) || fail "cannot read the certify and verify-service logs"
context_warnings=$(grep -E 'Cannot load context|is not an absolute IRI nor @json' <<<"$stack_logs" | head -5 || true)
[[ -z "$context_warnings" ]] || fail "JSON-LD context warnings in the certify or verify-service log: $context_warnings"
ok "no context-loading or datatype warnings in the certify and verify-service logs"

# The JSON-LD libraries each image carries: the versions @json was checked against, and no jsonld-java (JSON-LD 1.0,
# which rejects "@type": "@json").
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
