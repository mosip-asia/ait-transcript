#!/usr/bin/env bash
# Automated smoke checks for Phase 1 (curl/jq). Run from vc-stack/ after bootstrap.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"
source "$STACK_DIR/installation.sh"

CLAIMS=(
  fullName dateOfBirth country registrationNo previousDegree yearAwarded
  dateAdmitted option degreeAwarded dateGraduation faculty academicProgram
  areaOfSpecialization notes issueDate courses courseList
  thesisTitle thesisGrade programCommittee courseworkCredits thesisCredits
  totalCredits thesisExamination
)

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

sorted_lines() {
  sort | awk 'NF'
}

python3 "$REPO_ROOT/data/generate_csv.py" >/dev/null

issuer_json=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer) \
  || fail "certify issuer metadata not reachable on :9091"

config_count=$(echo "$issuer_json" | jq '.credential_configurations_supported | keys | length')
[[ "$config_count" == "1" ]] || fail "expected exactly 1 credential config, got $config_count"

got_claims=$(echo "$issuer_json" | jq -r \
  '.credential_configurations_supported["ait-transcript"].credential_definition.credentialSubject | keys[]' | sorted_lines)
want_claims=$(printf '%s\n' "${CLAIMS[@]}" | sorted_lines)
[[ "$got_claims" == "$want_claims" ]] || fail "issuer metadata claim names do not match PRD §7"
ok "issuer lists ait-transcript with PRD §7 claims"

auth_srv=$(echo "$issuer_json" | jq -r '.authorization_servers[0] // empty')
[[ "$auth_srv" == "http://keycloak:8080/realms/inji" ]] \
  || fail "Certify authorization_servers must be http://keycloak:8080/realms/inji (got: ${auth_srv:-<empty>})"
ok "Certify OID4VCI authorization_servers use Docker Keycloak URL"

# The Compose check of wiki/research/certify-json-literal.md section 4 runs below: step 2 here, steps 3 to 5
# after issuance, step 1 (library versions) printed for the record.
ctx_url=$(echo "$issuer_json" | jq -r \
  '.credential_configurations_supported["ait-transcript"].credential_definition["@context"][0]')
[[ "$ctx_url" == */contexts/transcript/v1.json ]] \
  || fail "ait-transcript @context must name the VDR's /contexts/transcript/v1.json (got: ${ctx_url:-<empty>})"
served_ctx=$(curl -sf http://localhost:9098/contexts/transcript/v1.json) \
  || fail "public gateway does not serve /contexts/transcript/v1.json (vdr container)"
[[ "$(jq -S . <<<"$served_ctx")" == "$(jq -S . "$REPO_ROOT/vc-lab/contexts/transcript/v1.json")" ]] \
  || fail "served context differs from vc-lab/contexts/transcript/v1.json"
ok "transcript context v1 served by the VDR through the public gateway"

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

template=config/AITUniversity-ait-transcript-template.html
[[ -f "$template" ]] || fail "missing Mimoto PDF template $template"
ok "Mimoto template filename AITUniversity-ait-transcript-template.html present"

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

issuer=$(curl -sf http://localhost:9080/realms/inji/.well-known/openid-configuration | jq -r '.issuer')
[[ "$issuer" == "http://keycloak:8080/realms/inji" ]] || fail "Keycloak issuer must be http://keycloak:8080/realms/inji (got: ${issuer:-<empty>})"
ok "Keycloak OIDC issuer aligned for Mimoto token aud"

auth_endpoint=$(curl -sf http://localhost:4004/v1/mimoto/issuers/AITUniversity/configuration | jq -r '.response.authorization_endpoint // empty')
[[ "$auth_endpoint" == http://localhost:9080/* ]] \
  || fail "Inji Web auth URL must be http://localhost:9080/... (got: ${auth_endpoint:-<empty>})"
ok "Mimoto exposes browser Keycloak auth URL for Inji Web"

config_errors=$(curl -sf http://localhost:4004/v1/mimoto/issuers/AITUniversity/configuration | jq -r '.errors | length')
cred_count=$(curl -sf http://localhost:4004/v1/mimoto/issuers/AITUniversity/configuration | jq -r '.response.credentials_supported | length')
[[ "$config_errors" == "0" && "$cred_count" -ge 1 ]] \
  || fail "issuer configuration must list credential types (errors=$config_errors, credentials_supported=$cred_count) — Keycloak well-known via keycloak:8080 often 502 until keycloak nginx reload"
ok "Mimoto issuer configuration lists credential types for Inji Web"

token_ep=$(curl -sf http://localhost:4004/v1/mimoto/issuers/AITUniversity | jq -r '.response.token_endpoint // empty')
[[ "$token_ep" == http://localhost:4004/v1/mimoto/get-token/* ]] \
  || fail "issuer token_endpoint must use Inji Web proxy :4004 (got: ${token_ep:-<empty>}) — run bootstrap configure_mode"
ok "Issuer token_endpoint uses Inji Web same-origin :4004"

auth_aud=$(curl -sf http://localhost:4004/v1/mimoto/issuers/AITUniversity | jq -r '.response.authorization_audience // empty')
[[ "$auth_aud" == http://keycloak:8080/* ]] \
  || fail "authorization_audience must be keycloak:8080 token URL (got: ${auth_aud:-<empty>})"
ok "Issuer authorization_audience matches Docker Keycloak token URL"

# The mock adapter answers contract 2b's three paths and a 404, and serves an edited CSV value at once.
docker compose run --rm --no-deps -T \
  -v "$STACK_DIR/../adapter/test_adapter.py:/demo/adapter/test_adapter.py:ro" \
  demo-app python adapter/test_adapter.py http://adapter:8000 \
  "/demo/installations/$INSTALLATION/adapter/student_identity_data.csv" \
  || fail "mock adapter (adapter/test_adapter.py)"
ok "mock adapter serves the degree list, the record and the eligibility attributes"

# The Gateway answers contract 2a's cases with the mock adapter beside it and writes one issuance row per 200.
# Run from the gateway image (httpx, psycopg), whose environment carries the token and the database URL.
docker compose run --rm --no-deps -T \
  -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" \
  -v "$INSTALLATION_DIR/adapter:/data:ro" \
  gateway python tests/test_issuances.py http://gateway:8000 /data/student_identity_data.csv \
  || fail "Gateway (gateway/tests/test_issuances.py)"
ok "Gateway: 200, 403 per failing check, 404, 400, 401, one issuance row per 200"

# An adapter failure during a request is a Gateway error (502), not a crash. The adapter is restarted
# whether or not the check passes, so later steps still see it.
docker compose stop adapter >/dev/null || fail "cannot stop the adapter"
adapter_down_rc=0
docker compose run --rm --no-deps -T   -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro"   gateway python tests/test_issuances.py adapter-down http://gateway:8000 || adapter_down_rc=$?
docker compose start adapter >/dev/null || fail "cannot restart the adapter"
adapter_up=0
for _ in $(seq 1 30); do
  if docker compose run --rm --no-deps -T gateway python -c     "import httpx; httpx.get('http://adapter:8000/students/ait-2026-0001/eligibility', timeout=3).raise_for_status()" >/dev/null 2>&1; then
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
rows_before=$(issuance_rows) || fail "cannot count gateway.issuances"
smoke_vc=.demo-state/smoke-credential.json
issue_and_verify issue "$INSTALLATION" ait-2026-0001 ait_transcript_vc_ldp "$smoke_vc" \
  || fail "scripted issuance (vc-stack/issue_and_verify.py issue)"
jq -e --arg u "$ctx_url" '."@context" | index($u)' "$REPO_ROOT/$smoke_vc" >/dev/null \
  || fail "issued credential does not name $ctx_url in its @context"
issue_and_verify verify "$smoke_vc" || fail "credential verification (vc-stack/issue_and_verify.py verify)"
rows_issued=$(issuance_rows) || fail "cannot count gateway.issuances"
[[ "$rows_issued" == "$((rows_before + 1))" ]]   || fail "the Certify-path issuance must add one gateway.issuances row (before: $rows_before, after: $rows_issued)"
ok "the Certify-path issuance wrote one gateway.issuances row"

# A persona the Gateway's checklist refuses (a hold on the record) gets the OpenID4VCI error body with its code.
issue_and_verify refused "$INSTALLATION" ait-2026-0002 ait_transcript_vc_ldp checklist_failed \
  || fail "refused persona through Certify (vc-stack/issue_and_verify.py refused ... checklist_failed)"
rows_refused=$(issuance_rows) || fail "cannot count gateway.issuances"
[[ "$rows_refused" == "$rows_issued" ]]   || fail "the refused persona must add no gateway.issuances row (before: $rows_issued, after: $rows_refused)"
ok "the refused persona wrote no gateway.issuances row"

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
  issue_and_verify refused "$INSTALLATION" ait-2026-0001 ait_transcript_vc_ldp gateway_error || gateway_down_rc=$?
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
