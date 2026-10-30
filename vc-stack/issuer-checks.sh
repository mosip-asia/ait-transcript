# Sourced by smoke.sh and issuer-smoke.sh, from vc-stack/ after installation.sh: the checks the Issuer passes with the
# mock Adapter beside it, and the helpers both scripts use. `docker compose` finds the stack the caller runs:
# compose.yaml by default, issuer-dev.yaml when the caller exports COMPOSE_FILE. The caller sets REPO_ROOT and FIXTURES
# (installations/$INSTALLATION/smoke.json); issuer_checks leaves Certify's issuer metadata in issuer_json.

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }
# retry TRIES CMD...: runs CMD every 2 s until it succeeds, at most TRIES times.
retry() { local tries=$1; shift; for _ in $(seq 1 "$tries"); do "$@" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
# in_network URL: the body of a GET from inside the Docker network, through the running Gateway's container.
in_network() {
  docker compose exec -T gateway python -c \
    "import sys, httpx; r = httpx.get(sys.argv[1], timeout=5); r.raise_for_status(); print(r.text)" "$1"
}

# check_contexts BASE NAME: BASE serves the context every credential configuration names under /contexts/, as
# committed under vc-lab/contexts/. The path comes from the configuration's @context, whatever host the seed names.
check_contexts() {
  local base=$1 name=$2 i config ctx_url ctx_path served_ctx
  for ((i = 0; i < $(jq length "$FIXTURES"); i++)); do
    config=$(jq -r ".[$i].credentialConfig" "$FIXTURES")
    ctx_url=$(jq -r --arg c "$config" \
      '[.credential_configurations_supported[$c].credential_definition["@context"][] | select(contains("/contexts/"))][0] // empty' \
      <<<"$issuer_json")
    [[ -n "$ctx_url" ]] || fail "$config @context names no context under /contexts/"
    ctx_path="${ctx_url#*/contexts/}"
    served_ctx=$(curl -sf "$base/contexts/$ctx_path") || fail "$name does not serve /contexts/$ctx_path"
    [[ "$(jq -S . <<<"$served_ctx")" == "$(jq -S . "$REPO_ROOT/vc-lab/contexts/$ctx_path")" ]] \
      || fail "$name's /contexts/$ctx_path differs from vc-lab/contexts/$ctx_path"
    ok "$name serves /contexts/$ctx_path from the VDR"
  done
}

issuer_checks() {
  local want_configs got_configs i config scope want_claims got_claims eligible adapter_down_rc
  # 1. Certify started with the Gateway plugin selected.
  local certify_log
  certify_log=$(docker compose logs --no-color certify 2>&1) || fail "cannot read the certify log"
  ! grep -qE 'NoSuchBeanDefinitionException|NoUniqueBeanDefinitionException' <<<"$certify_log" \
    || fail "missing-bean or duplicate-bean error in the certify log"
  grep -q 'GatewayDataProviderPlugin selected' <<<"$certify_log" || fail "the certify log does not name GatewayDataProviderPlugin"
  ok "Certify started with GatewayDataProviderPlugin"

  # 2. Certify's issuer metadata lists exactly the installation's credential types, each with the Gateway's claims.
  issuer_json=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer) \
    || fail "Certify's issuer metadata not reachable on :9091"
  want_configs=$(jq -r '[.[].credentialConfig] | sort | join(" ")' "$FIXTURES")
  got_configs=$(jq -r '.credential_configurations_supported | keys | sort | join(" ")' <<<"$issuer_json")
  [[ "$got_configs" == "$want_configs" ]] || fail "expected exactly the credential configs $want_configs, got: $got_configs"
  for ((i = 0; i < $(jq length "$FIXTURES"); i++)); do
    config=$(jq -r ".[$i].credentialConfig" "$FIXTURES")
    scope=$(jq -r ".[$i].scope" "$FIXTURES")
    # The record model's fields and the derived claims (gateway/credential_types.py), read in the Gateway's container.
    want_claims=$(docker compose exec -T gateway python -c "import sys, credential_types as ct
t = ct.REGISTRY[sys.argv[1]]; print('\n'.join([*t.record.model_fields, *t.derived]))" "$scope" | sort | awk 'NF')
    got_claims=$(jq -r --arg c "$config" '.credential_configurations_supported[$c].credential_definition.credentialSubject | keys[]' \
      <<<"$issuer_json" | sort | awk 'NF')
    [[ "$got_claims" == "$want_claims" ]] || fail "issuer metadata claim names for $config differ from the Gateway's for $scope"
    ok "Certify lists $config with the Gateway's claims for $scope"
  done

  # 3. certify-nginx, the Issuer's entry point, serves the contexts from the VDR.
  check_contexts http://localhost:9091 certify-nginx

  # 4. The Gateway answers every persona of smoke.json with the mock Adapter beside it (the live mode of
  # gateway/tests/test_issuances.py) and writes one issuance row per 200. Run from the gateway image (httpx, psycopg),
  # whose environment carries the token and the database URL.
  docker compose run --rm --no-deps -T \
    -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" \
    -v "$INSTALLATION_DIR:/installation:ro" \
    gateway python tests/test_issuances.py http://gateway:8000 /installation/adapter/student_identity_data.csv \
    /installation/smoke.json \
    || fail "Gateway (gateway/tests/test_issuances.py)"
  ok "Gateway: 200 eligible, 403 checklist_failed with the failing checks, 404 no_record unknown, 400, 401, one issuance row per 200"

  # 5. An Adapter failure during a request is a Gateway error (502), not a crash. The Adapter is started again whether
  # or not the check passes, and answers again before the next step, so the stack is left as it was.
  docker compose stop adapter >/dev/null || fail "cannot stop the adapter"
  adapter_down_rc=0
  docker compose run --rm --no-deps -T -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" -v "$FIXTURES:/smoke.json:ro" \
    gateway python tests/test_issuances.py adapter-down http://gateway:8000 /smoke.json || adapter_down_rc=$?
  docker compose start adapter >/dev/null || fail "cannot restart the adapter"
  eligible=$(jq -r '.[0].eligible | if type == "array" then .[0] else . end' "$FIXTURES")
  retry 30 in_network "http://adapter:8000/students/$eligible/eligibility" || fail "adapter did not answer again after restart"
  [[ "$adapter_down_rc" == 0 ]] || fail "Gateway with the adapter down must answer 502 gateway_error (gateway/tests/test_issuances.py adapter-down)"
  ok "Gateway: adapter down is a 502 gateway_error, and the adapter is back"
}
