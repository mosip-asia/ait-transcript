# Sourced by smoke.sh and issuer-smoke.sh, from vc-stack/ after installation.sh: the checks the Issuer passes with the
# mock Adapter beside it, and the helpers both scripts use. `docker compose` finds the stack the caller runs:
# compose.yaml by default, or the file COMPOSE_FILE names (issuer-dev.yaml, or a no-Gateway form). The caller sets
# REPO_ROOT and FIXTURES (installations/$INSTALLATION/smoke.json); issuer_checks leaves Certify's issuer metadata in
# issuer_json. GATE_ENABLED (true or false) and GATE_URL are the plugin's switch as Certify runs it.

fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }
# retry TRIES CMD...: runs CMD every 2 s until it succeeds, at most TRIES times.
retry() { local tries=$1; shift; for _ in $(seq 1 "$tries"); do "$@" >/dev/null 2>&1 && return 0; sleep 2; done; return 1; }
# in_network URL: the body of a GET from inside the Docker network, through the mock Adapter's container, which every
# stack form runs.
in_network() {
  docker compose exec -T adapter python -c \
    "import sys, urllib.request; print(urllib.request.urlopen(sys.argv[1], timeout=5).read().decode())" "$1"
}

# switch_setting VARIABLE PROPERTY: the value Certify runs with, its Compose environment's VARIABLE (a no-Gateway form
# or vc-stack/.env sets it), else the installation's PROPERTY.
switch_setting() {
  local from_env
  from_env=$(docker compose config --format json | jq -r --arg v "$1" '.services.certify.environment[$v] // empty') \
    || fail "docker compose config failed: cannot read Certify's environment"
  if [[ -n "$from_env" ]]; then
    echo "$from_env"
  else
    tr -d '\r' <"$INSTALLATION_DIR/certify-installation.properties" | grep "^$2=" | cut -d= -f2-
  fi
}
GATE_ENABLED=$(switch_setting MOSIP_CERTIFY_GATEWAY_ENABLED mosip.certify.gateway.enabled)
GATE_URL=$(switch_setting MOSIP_CERTIFY_GATEWAY_URL mosip.certify.gateway.url)
[[ "$GATE_ENABLED" == true || "$GATE_ENABLED" == false ]] \
  || fail "mosip.certify.gateway.enabled must be true or false (got: ${GATE_ENABLED:-<unset>})"
echo "The plugin's gate: enabled=$GATE_ENABLED, Gateway $GATE_URL"

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
  # 1. Certify started with the Data-provider plugin selected and the gate as configured. The installation's
  # properties carry the plugin's ten keys and no other; the plugin reads all ten with the gate on, and with it off
  # all but the token and the Gateway's timeouts, so Certify's environment may override only those it reads. With the
  # gate on, its token is the Gateway's.
  local certify_log certify_props plugin_keys all_keys want_keys env_keys unread
  certify_log=$(docker compose logs --no-color certify 2>&1) || fail "cannot read the certify log"
  ! grep -qE 'NoSuchBeanDefinitionException|NoUniqueBeanDefinitionException' <<<"$certify_log" \
    || fail "missing-bean or duplicate-bean error in the certify log"
  grep -qF "IssuerDataProviderPlugin selected: gateway.enabled=$GATE_ENABLED, Gateway ${GATE_URL%/}, Adapter http" <<<"$certify_log" \
    || fail "the certify log does not name IssuerDataProviderPlugin with gateway.enabled=$GATE_ENABLED, the Gateway $GATE_URL and its Adapter"
  ok "Certify started with IssuerDataProviderPlugin, gateway.enabled=$GATE_ENABLED"
  certify_props=$(tr -d '\r' <"$INSTALLATION_DIR/certify-installation.properties")
  plugin_keys=$( (grep -oE '^mosip\.certify\.((adapter|gateway)\.[a-z-]+|integration\.(data-provider-plugin|scan-base-package))=' <<<"$certify_props" || true) \
    | tr -d = | LC_ALL=C sort)
  all_keys=$(printf '%s\n' mosip.certify.adapter.{connect-timeout-ms,read-timeout-ms,url} \
    mosip.certify.gateway.{auth-token,connect-timeout-ms,enabled,read-timeout-ms,url} \
    mosip.certify.integration.{data-provider-plugin,scan-base-package} | LC_ALL=C sort)
  if [[ "$GATE_ENABLED" == true ]]; then
    want_keys=$all_keys
  else
    want_keys=$(grep -vE '^mosip\.certify\.gateway\.(auth-token|connect-timeout-ms|read-timeout-ms)$' <<<"$all_keys")
  fi
  [[ "$plugin_keys" == "$all_keys" ]] || fail "Certify's plugin keys must be the plugin's ten (got: $plugin_keys)"
  # MOSIP_CERTIFY_GATEWAY_AUTH_TOKEN is the property mosip.certify.gateway.auth-token, by Spring's relaxed binding.
  env_keys=$(docker compose config --format json | jq -r '.services.certify.environment | to_entries[]
    | select(.value != null) | .key | ascii_downcase | select(test("^mosip_certify_(adapter|gateway)_"))
    | capture("^mosip_certify_(?<peer>[a-z]+)_(?<key>.+)$") | "mosip.certify.\(.peer).\(.key | gsub("_"; "-"))"' \
    | LC_ALL=C sort) || fail "docker compose config failed: cannot read Certify's environment"
  unread=$(LC_ALL=C comm -23 <(echo "$env_keys") <(echo "$want_keys") | awk 'NF')
  [[ -z "$unread" ]] || fail "with gateway.enabled=$GATE_ENABLED Certify's environment sets plugin keys the plugin does not read: $unread"
  ! grep -q '^mosip\.certify\.mock\.data-provider\.' <<<"$certify_props" || fail "the CSV plugin's keys are still in Certify's properties"
  if [[ "$GATE_ENABLED" == true ]]; then
    [[ "$(grep '^mosip.certify.gateway.auth-token=' <<<"$certify_props")" == \
       "mosip.certify.gateway.auth-token=$(tr -d '\r' <"$INSTALLATION_DIR/gateway.env" | grep '^GATEWAY_AUTH_TOKEN=' | cut -d= -f2-)" ]] \
      || fail "mosip.certify.gateway.auth-token must equal GATEWAY_AUTH_TOKEN in gateway.env"
    ok "Certify's plugin configuration is the ten keys; its token is the Gateway's"
  else
    ok "Certify's plugin configuration is the ten keys, of which the gate off reads $(wc -l <<<"$want_keys")"
  fi

  # 2. Certify signs as its live key: did.json's id (a credential's issuer) is the did:key of the key it publishes, and
  # every credential configuration's did_url (a credential's verificationMethod) is that DID. A fresh keystore holds a
  # new key, so until bootstrap.sh --did-refresh writes the DID, every credential fails verification.
  local did_doc live_did stale
  did_doc=$(curl -sf http://localhost:9091/.well-known/did.json) || fail "Certify's did.json not reachable on :9091"
  live_did="did:key:$(jq -r '.verificationMethod[0].publicKeyMultibase' <<<"$did_doc")"
  [[ "$(jq -r .id <<<"$did_doc")" == "$live_did" ]] \
    || fail "Certify's DID is $(jq -r .id <<<"$did_doc"), not its live key $live_did: run bootstrap.sh --did-refresh"
  stale=$(docker compose exec -T database psql -U postgres -d inji_certify -tAc \
    "select credential_config_key_id from certify.credential_config where did_url is distinct from '$live_did'" | awk 'NF' | paste -sd' ')
  [[ -z "$stale" ]] || fail "$stale name another DID than the live key $live_did: run bootstrap.sh --did-refresh"
  ok "Certify signs as its live key $live_did"

  # 3. Certify's issuer metadata lists exactly the installation's credential types, each with the claims of the Adapter
  # contract's record schema for its scope.
  issuer_json=$(curl -sf http://localhost:9091/.well-known/openid-credential-issuer) \
    || fail "Certify's issuer metadata not reachable on :9091"
  want_configs=$(jq -r '[.[].credentialConfig] | sort | join(" ")' "$FIXTURES")
  got_configs=$(jq -r '.credential_configurations_supported | keys | sort | join(" ")' <<<"$issuer_json")
  [[ "$got_configs" == "$want_configs" ]] || fail "expected exactly the credential configs $want_configs, got: $got_configs"
  for ((i = 0; i < $(jq length "$FIXTURES"); i++)); do
    config=$(jq -r ".[$i].credentialConfig" "$FIXTURES")
    scope=$(jq -r ".[$i].scope" "$FIXTURES")
    # The required claims of the scope's record schema in adapter/openapi.yaml, read in the mock Adapter's image (PyYAML).
    want_claims=$(docker compose run --rm --no-deps -T -v "$REPO_ROOT/adapter:/repo/adapter:ro" \
      -v "$REPO_ROOT/data:/repo/data:ro" adapter python /repo/adapter/test_adapter.py --record-claims "$scope" \
      | sort | awk 'NF') || fail "cannot read the record schema for $scope from adapter/openapi.yaml"
    [[ -n "$want_claims" ]] || fail "adapter/openapi.yaml names no claim for $scope"
    got_claims=$(jq -r --arg c "$config" '.credential_configurations_supported[$c].credential_definition.credentialSubject | keys[]' \
      <<<"$issuer_json" | sort | awk 'NF')
    [[ "$got_claims" == "$want_claims" ]] || fail "issuer metadata claim names for $config differ from the contract's record schema for $scope"
    ok "Certify lists $config with the claims of the contract's record schema for $scope"
  done

  # 4. certify-nginx, the Issuer's entry point, serves the contexts from the VDR.
  check_contexts http://localhost:9091 certify-nginx

  # With the gate off the stack form leaves the Gateway out: no gateway service runs, and nothing below asks one.
  if [[ "$GATE_ENABLED" == false ]]; then
    ! docker compose config --services | grep -qx gateway || fail "the gate is off, but the stack form defines a gateway service"
    [[ -z "$(docker ps -q --filter name='^gateway$')" ]] || fail "the gate is off, but a gateway container is running"
    ok "the gate is off and no gateway service is running"
    return 0
  fi

  # 5. The Gateway's POST /evaluations answers every persona of smoke.json with the mock Adapter beside it (the live
  # mode of gateway/tests/test_evaluations.py). Run from the gateway image, whose environment carries the token.
  docker compose run --rm --no-deps -T -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" -v "$FIXTURES:/smoke.json:ro" \
    gateway python tests/test_evaluations.py http://gateway:8000 /smoke.json \
    || fail "Gateway evaluations (gateway/tests/test_evaluations.py)"
  ok "Gateway evaluations: 200 eligible, 403 checklist_failed with the failing checks, 404 no_record unknown, 400, 401"

  # 6. An Adapter failure during an evaluation is a Gateway error (502), not a crash. The Adapter is started again
  # whether or not the check passes, and answers again before the next step, so the stack is left as it was.
  docker compose stop adapter >/dev/null || fail "cannot stop the adapter"
  adapter_down_rc=0
  docker compose run --rm --no-deps -T -v "$REPO_ROOT/gateway/tests:/gateway/tests:ro" -v "$FIXTURES:/smoke.json:ro" \
    gateway python tests/test_evaluations.py adapter-down http://gateway:8000 /smoke.json || adapter_down_rc=$?
  docker compose start adapter >/dev/null || fail "cannot restart the adapter"
  eligible=$(jq -r '.[0].eligible | if type == "array" then .[0] else . end' "$FIXTURES")
  scope=$(jq -r '.[0].scope' "$FIXTURES")
  retry 30 in_network "http://adapter:8000/records/$eligible/eligibility?scope=$scope" || fail "adapter did not answer again after restart"
  [[ "$adapter_down_rc" == 0 ]] || fail "Gateway with the adapter down must answer 502 gateway_error (test_evaluations.py adapter-down)"
  ok "Gateway: adapter down is a 502 gateway_error on /evaluations, and the adapter is back"
}
