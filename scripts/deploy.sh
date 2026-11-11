#!/usr/bin/env bash
# ==============================================================================
# Deploy or update the AIT Issuer Platform Compose stack on the host.
# ==============================================================================
# Usage:
#   ./scripts/deploy.sh [installation] [--wipe]
#
# Examples:
#   ./scripts/deploy.sh
#   ./scripts/deploy.sh ait
#   ./scripts/deploy.sh ait --wipe
#   ./scripts/deploy.sh hackathon
# ==============================================================================
set -euo pipefail

# ANSI color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
RED="\033[0;31m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m"

log_info() { echo -e "${BLUE}${BOLD}[DEPLOY]${NC} $*"; }
log_ok() { echo -e "${GREEN}${BOLD}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}${BOLD}[WARN]${NC} $*"; }
log_err() { echo -e "${RED}${BOLD}[ERROR]${NC} $*" >&2; }

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

INSTALLATION="${1:-${INSTALLATION:-ait}}"
# If first argument is --wipe, keep default installation 'ait'
if [ "$INSTALLATION" = "--wipe" ] || [ "$INSTALLATION" = "wipe" ]; then
  INSTALLATION="ait"
fi

WIPE_FLAG=false
for arg in "$@"; do
  if [ "$arg" = "--wipe" ] || [ "$arg" = "wipe" ]; then
    WIPE_FLAG=true
  fi
done

log_info "Starting deployment of ait-transcript (installation: ${INSTALLATION})..."
export INSTALLATION

# 1. Ensure .env exists with required defaults
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    log_warn "No .env file found. Creating from .env.example..."
    cp .env.example .env
  else
    log_err "Missing .env and .env.example file. Aborting."
    exit 1
  fi
fi

# Load CERTIFY_PORT if defined in .env
CERTIFY_PORT="$(grep -E '^CERTIFY_PORT=' .env 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r' || echo "")"
CERTIFY_PORT="${CERTIFY_PORT:-9091}"
CERTIFY_URL="http://127.0.0.1:${CERTIFY_PORT}"

# 2. Ensure plugin JAR is built
PLUGIN_JAR="src/issuer/target/issuer-data-provider-plugin.jar"
if [ ! -f "$PLUGIN_JAR" ]; then
  log_info "Building Inji Certify DataProviderPlugin JAR via compiler container..."
  docker compose -f compose.build.yaml run --rm plugin-builder
fi

# 3. Tear down existing stack
log_info "Tearing down existing stack..."
if [ "$WIPE_FLAG" = true ]; then
  log_warn "Wiping database and volumes (--wipe specified)..."
  docker compose down -v --remove-orphans
else
  docker compose down --remove-orphans
fi

# 4. Build local services (template-sync, etc.)
log_info "Building local services (template-sync, verifier, etc.)..."
docker compose build --quiet

# 5. Start fresh stack
log_info "Starting compose services..."
docker compose up -d --remove-orphans

# 6. Wait for Inji Certify to initialize
log_info "Waiting for Inji Certify issuer engine to initialize at ${CERTIFY_URL}..."
TIMEOUT=90
ELAPSED=0

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if curl -sf "${CERTIFY_URL}/.well-known/openid-credential-issuer" >/dev/null 2>&1 || \
     curl -sf "${CERTIFY_URL}/v1/certify/.well-known/openid-credential-issuer" >/dev/null 2>&1; then
    log_ok "Inji Certify is ready!"
    break
  fi
  sleep 3
  ELAPSED=$((ELAPSED + 3))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  log_err "Inji Certify failed to become ready within ${TIMEOUT}s. Recent logs:"
  docker compose logs --tail 50 certify
  exit 1
fi

# 7. Run post-deployment issuance smoke test
log_info "Running post-deployment issuance smoke test..."
if ! bash scripts/smoke-test.sh "${CERTIFY_URL}"; then
  log_err "Post-deployment smoke test failed. Recent logs:"
  docker compose logs --tail 50 certify
  exit 1
fi
log_ok "Post-deployment smoke test passed."

# 8. Stack status summary
echo ""
echo -e "${GREEN}${BOLD}Stack status:${NC}"
docker compose ps
echo ""
echo -e "${GREEN}${BOLD}✅ Deployment of ait-transcript completed successfully!${NC}"
