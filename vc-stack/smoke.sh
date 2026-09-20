#!/usr/bin/env bash
# Automated smoke checks for Phase 1 (curl/jq). Run from vc-stack/ after bootstrap.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"

CLAIMS=(
  fullName dateOfBirth country registrationNo previousDegree yearAwarded
  dateAdmitted option degreeAwarded dateGraduation faculty academicProgram
  areaOfSpecialization notes issueDate courses courseTableHtml courseList
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

kc_users=$(jq -r '.users[].username' config/keycloak-realm.json | sorted_lines)
csv_ids=$(python3 -c "import csv; from pathlib import Path
p=Path('config/student_identity_data.csv')
with p.open(newline='', encoding='utf-8') as f:
  print('\n'.join(sorted(r['id'] for r in csv.DictReader(f))))")
[[ "$kc_users" == "$csv_ids" ]] || fail "Keycloak usernames must match CSV id column row-for-row"
ok "Keycloak users align with CSV ids"

prop_cols=$(grep '^mosip.certify.mock.data-provider.csv.data-columns=' config/certify-csvdp-student.properties | cut -d= -f2-)
csv_header=$(head -1 config/student_identity_data.csv | tr -d '\r')
prop_n=$(echo "$prop_cols" | awk -F, '{print NF}')
csv_n=$(echo "$csv_header" | awk -F, '{print NF}')
[[ "$prop_n" == "$csv_n" ]] || fail "data-columns count ($prop_n) != CSV header count ($csv_n)"
[[ "$prop_cols" == "$csv_header" ]] || fail "data-columns header text mismatch"
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

python3 "$STACK_DIR/test_inji_web_vc_readiness.py" --live

echo "All smoke checks passed."
