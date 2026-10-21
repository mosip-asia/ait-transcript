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

prop_cols=$(grep '^mosip.certify.mock.data-provider.csv.data-columns=' "$INSTALLATION_DIR/certify-csvdp-student.properties" | cut -d= -f2-)
csv_header=$(head -1 "$csv_file" | tr -d '\r')
prop_n=$(echo "$prop_cols" | awk -F, '{print NF}')
csv_n=$(echo "$csv_header" | awk -F, '{print NF}')
[[ "$prop_n" -le "$csv_n" ]] || fail "data-columns count ($prop_n) exceeds CSV header count ($csv_n)"
csv_prefix=$(echo "$csv_header" | cut -d, -f1-"$prop_n")
[[ "$prop_cols" == "$csv_prefix" ]] || fail "data-columns must be the leading CSV header columns, in order (claim columns first)"
extra_n=$((csv_n - prop_n))
[[ "$extra_n" -eq 0 ]] || ok "$extra_n adapter-only column(s) after the claim columns: $(echo "$csv_header" | cut -d, -f"$((prop_n + 1))"-)"
ok "CSV column alignment"

template=config/AITUniversity-ait-transcript-template.html
[[ -f "$template" ]] || fail "missing Mimoto PDF template $template"
ok "Mimoto template filename AITUniversity-ait-transcript-template.html present"

before=$(docker compose ps -q | wc -l | tr -d ' ')
docker compose up -d >/dev/null
after=$(docker compose ps -q | wc -l | tr -d ' ')
[[ "$after" -ge "$before" ]] || fail "bootstrap re-run reduced container count"
ok "bootstrap idempotent re-run"

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

# Scripted issuance, then verification with a tampered copy, inside the Docker network (see the script's docstring).
issue_and_verify() {
  docker compose run --rm --no-deps -T \
    -v "$STACK_DIR/issue_and_verify.py:/demo/vc-stack/issue_and_verify.py:ro" \
    demo-app python vc-stack/issue_and_verify.py "$@"
}
smoke_vc=.demo-state/smoke-credential.json
issue_and_verify issue "$INSTALLATION" ait-2026-0001 ait_transcript_vc_ldp "$smoke_vc" \
  || fail "scripted issuance (vc-stack/issue_and_verify.py issue)"
jq -e --arg u "$ctx_url" '."@context" | index($u)' "$REPO_ROOT/$smoke_vc" >/dev/null \
  || fail "issued credential does not name $ctx_url in its @context"
issue_and_verify verify "$smoke_vc" || fail "credential verification (vc-stack/issue_and_verify.py verify)"

stack_logs=$(docker compose logs --no-color certify verify-service 2>&1) || fail "cannot read the certify and verify-service logs"
context_warnings=$(grep -E 'Cannot load context|is not an absolute IRI nor @json' <<<"$stack_logs" | head -5 || true)
[[ -z "$context_warnings" ]] || fail "JSON-LD context warnings in the certify or verify-service log: $context_warnings"
ok "no context-loading or datatype warnings in the certify and verify-service logs"

# Step 1: the JSON-LD libraries each image carries must be the ones the research note's section 4 expects.
jsonld_libs() {
  local jar tmp
  jar=$(docker compose exec -T "$1" sh -c 'ls /home/mosip/*.jar' 2>/dev/null | head -1 | tr -d '\r')
  [[ -n "$jar" ]] || { echo "no jar under /home/mosip"; return; }
  tmp=$(mktemp)
  docker compose cp "$1:$jar" "$tmp" >/dev/null 2>&1 && python3 - "$tmp" <<'PYEOF'
import re, sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
print(" ".join(sorted(n.rsplit("/", 1)[-1] for n in names
                      if re.search(r"(jsonld|titanium|rdf-urdna|ld-signatures)[^/]*\.jar$", n))))
PYEOF
  rm -f "$tmp"
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
certify_libs=$(jsonld_libs certify || echo unreadable)
assert_jsonld_libs certify "$certify_libs" titanium-json-ld-1.6.0.jar titanium-jcs-1.0.0.jar titanium-rdfc-2.0.0.jar \
  jsonld-common-java-1.14.0.jar rdf-urdna-1.4.jar
verify_libs=$(jsonld_libs verify-service || echo unreadable)
assert_jsonld_libs verify-service "$verify_libs" titanium-json-ld-1.3.2.jar titanium-json-ld-jre8-1.3.1.jar \
  jsonld-common-java-1.8.0.jar rdf-urdna-1.2.jar ld-signatures-java-1.11.0.jar

python3 "$STACK_DIR/test_inji_web_vc_readiness.py" --live

echo "All smoke checks passed."
