#!/usr/bin/env bash
# Issuer-only smoke checks (curl/jq): the Issuer and the mock Adapter up from issuer-dev.yaml, demo/ and verify/ down.
#   docker compose --env-file vc-stack/.env -f vc-stack/issuer-dev.yaml up -d --build
#   ./vc-stack/bootstrap.sh --did-refresh
#   ./vc-stack/issuer-smoke.sh
# Without the Gateway, the same with issuer-dev-no-gateway.yaml, and COMPOSE_FILE=issuer-dev-no-gateway.yaml for the
# smoke: Certify's log says the gate is off, the metadata and contexts are as with it on, and no gateway runs.
# It waits for Certify, and for the Gateway only with the gate on, then checks that Certify loads the Data-provider
# plugin configured by its ten keys (the Adapter's, the switch and the Gateway's) with the gate as set, signs as its
# live did:key (which --did-refresh writes), serves the issuer metadata for the installation's credential types with
# the claims of the Adapter contract's record schemas, that certify-nginx serves their contexts from the VDR, and that
# the Gateway answers every persona of deploy/$INSTALLATION/smoke.json on POST /evaluations (200 eligible, 403
# checklist_failed refused, 404 no_record unknown) and 502 gateway_error with the Adapter down. There is no
# Authorization Server, so no credential is issued: the full-stack smoke.sh does that. The contexts are checked by path,
# whatever host the seed names; before Certify can sign on issuer-dev, bootstrap.sh --did-refresh moves the AIT row to
# CERTIFY_PUBLIC_BASE_URL.
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$STACK_DIR"
REPO_ROOT="$(cd "$STACK_DIR/.." && pwd)"
source "$STACK_DIR/installation.sh"

FIXTURES="$INSTALLATION_DIR/smoke.json"

# Every docker compose call, here and in issuer-checks.sh, runs issuer-dev.yaml, or the form COMPOSE_FILE names
# (relative to vc-stack/, the cwd).
export COMPOSE_FILE=${COMPOSE_FILE:-issuer-dev.yaml}
source "$STACK_DIR/issuer-checks.sh"

retry 150 curl -sf http://localhost:9091/.well-known/openid-credential-issuer \
  || fail "Certify's issuer metadata not reachable on :9091 within 5 minutes"
retry 30 in_network http://adapter:8000/docs || fail "the mock Adapter does not answer"
if [[ "$GATE_ENABLED" == true ]]; then
  retry 30 in_network http://gateway:8000/docs || fail "the Gateway does not answer"
fi

issuer_checks

echo "All Issuer-only smoke checks passed."
