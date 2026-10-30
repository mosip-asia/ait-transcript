#!/usr/bin/env bash
# Issuer-only smoke checks (curl/jq): the Issuer and the mock Adapter up from issuer-dev.yaml, demo/ and verify/ down.
#   docker compose --env-file vc-stack/.env -f vc-stack/issuer-dev.yaml up -d --build
#   ./vc-stack/issuer-smoke.sh
# It waits for Certify and the Gateway, then checks that Certify loads the Gateway plugin, serves the issuer metadata
# for the installation's credential types, that certify-nginx serves their contexts from the VDR, and that the Gateway
# answers every persona of installations/$INSTALLATION/smoke.json (200 eligible, 403 checklist_failed refused, 404
# no_record unknown) and 502 gateway_error with the Adapter down. There is no Authorization Server, so no credential
# is issued: the full-stack smoke.sh does that. The contexts are checked by path, whatever host the seed names; before
# Certify can sign on issuer-dev, bootstrap.sh --context-refresh moves the AIT row to CERTIFY_PUBLIC_BASE_URL.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"
source "$STACK_DIR/installation.sh"

FIXTURES="$INSTALLATION_DIR/smoke.json"

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }
compose() { docker compose -f "$STACK_DIR/issuer-dev.yaml" "$@"; }
# retry TRIES CMD...: runs CMD every 2 s until it succeeds, at most TRIES times.
retry() { local tries=$1; shift; for _ in $(seq 1 "$tries"); do "$@" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
# in_network URL: the body of a GET from inside the Docker network, through the running Gateway's container.
in_network() {
  compose exec -T gateway python -c \
    "import sys, httpx; r = httpx.get(sys.argv[1], timeout=5); r.raise_for_status(); print(r.text)" "$1"
}

retry 150 curl -sf http://localhost:9091/.well-known/openid-credential-issuer \
  || fail "Certify's issuer metadata not reachable on :9091 within 5 minutes"
retry 30 in_network http://gateway:8000/docs || fail "the Gateway does not answer"
retry 30 in_network http://adapter:8000/docs || fail "the mock Adapter does not answer"

# 1. Certify started with the Gateway plugin selected.
certify_log=$(compose logs --no-color certify 2>&1) || fail "cannot read the certify log"
! grep -qE 'NoSuchBeanDefinitionException|NoUniqueBeanDefinitionException' <<<"$certify_log" \
  || fail "missing-bean or duplicate-bean error in the certify log"
grep -q 'GatewayDataProviderPlugin selected' <<<"$certify_log" || fail "the certify log does not name GatewayDataProviderPlugin"
ok "Certify started with GatewayDataProviderPlugin"

# 2. Certify's issuer metadata lists exactly the installation's credential types, each with the Gateway's claims.
issuer_json=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer) || fail "Certify's issuer metadata"
want_configs=$(jq -r '[.[].credentialConfig] | sort | join(" ")' "$FIXTURES")
got_configs=$(jq -r '.credential_configurations_supported | keys | sort | join(" ")' <<<"$issuer_json")
[[ "$got_configs" == "$want_configs" ]] || fail "expected exactly the credential configs $want_configs, got: $got_configs"
type_count=$(jq length "$FIXTURES")
for ((i = 0; i < type_count; i++)); do
  config=$(jq -r ".[$i].credentialConfig" "$FIXTURES")
  scope=$(jq -r ".[$i].scope" "$FIXTURES")
  # The record model's fields and the derived claims (gateway/credential_types.py), read in the Gateway's container.
  want_claims=$(compose exec -T gateway python -c "import sys, credential_types as ct
t = ct.REGISTRY[sys.argv[1]]; print('\n'.join([*t.record.model_fields, *t.derived]))" "$scope" | sort | awk 'NF')
  got_claims=$(jq -r --arg c "$config" '.credential_configurations_supported[$c].credential_definition.credentialSubject | keys[]' \
    <<<"$issuer_json" | sort | awk 'NF')
  [[ "$got_claims" == "$want_claims" ]] || fail "issuer metadata claim names for $config differ from the Gateway's for $scope"
  ok "Certify lists $config with the Gateway's claims for $scope"

  # 3. certify-nginx, the Issuer's entry point, serves the context the configuration names from the VDR, as committed
  # under vc-lab/contexts/.
  ctx_url=$(jq -r --arg c "$config" \
    '[.credential_configurations_supported[$c].credential_definition["@context"][] | select(contains("/contexts/"))][0] // empty' \
    <<<"$issuer_json")
  [[ -n "$ctx_url" ]] || fail "$config @context names no context under /contexts/"
  ctx_path="${ctx_url#*/contexts/}"
  served_ctx=$(curl -sf "http://localhost:9091/contexts/$ctx_path") || fail "certify-nginx does not serve /contexts/$ctx_path"
  [[ "$(jq -S . <<<"$served_ctx")" == "$(jq -S . "$REPO_ROOT/vc-lab/contexts/$ctx_path")" ]] \
    || fail "certify-nginx's /contexts/$ctx_path differs from vc-lab/contexts/$ctx_path"
  ok "certify-nginx serves /contexts/$ctx_path from the VDR"
done

# 4. The Gateway answers every persona of smoke.json with the mock Adapter beside it (the live mode of
# gateway/tests/test_issuances.py, as in smoke.sh), then 502 gateway_error with the Adapter stopped.
compose run --rm --no-deps -T \
  -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" \
  -v "$INSTALLATION_DIR:/installation:ro" \
  gateway python tests/test_issuances.py http://gateway:8000 /installation/adapter/student_identity_data.csv \
  /installation/smoke.json \
  || fail "Gateway (gateway/tests/test_issuances.py)"
ok "Gateway: 200 eligible, 403 checklist_failed with the failing checks, 404 no_record unknown"

# The Adapter is started again whether or not the check passes, so the stack is left as it was.
compose stop adapter >/dev/null || fail "cannot stop the adapter"
adapter_down_rc=0
compose run --rm --no-deps -T -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" -v "$FIXTURES:/smoke.json:ro" \
  gateway python tests/test_issuances.py adapter-down http://gateway:8000 /smoke.json || adapter_down_rc=$?
compose start adapter >/dev/null || fail "cannot restart the adapter"
[[ "$adapter_down_rc" == 0 ]] || fail "Gateway with the adapter down must answer 502 gateway_error (gateway/tests/test_issuances.py adapter-down)"
ok "Gateway: adapter down is a 502 gateway_error"

echo "All Issuer-only smoke checks passed."
