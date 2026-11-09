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

echo "Target Installation: ${INSTALLATION}"
export INSTALLATION

# Ensure .env exists with required defaults
if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
fi

# Ensure plugin JAR is built
PLUGIN_JAR="src/issuer/target/issuer-data-provider-plugin.jar"
if [ ! -f "$PLUGIN_JAR" ]; then
  echo "Building Inji Certify DataProviderPlugin JAR via compiler container..."
  docker compose -f compose.build.yaml run --rm plugin-builder
fi

echo "Tearing down existing stack..."
if [ "$WIPE_FLAG" = true ]; then
  echo "Wiping database and volumes (--wipe specified)..."
  docker compose down -v --remove-orphans
else
  docker compose down --remove-orphans
fi

echo "Building local services (template-sync, etc.)..."
docker compose build --quiet

echo "Starting fresh stack..."
docker compose up -d --remove-orphans

echo "Waiting for Inji Certify issuer engine to initialize..."
CERTIFY_PORT="${CERTIFY_PORT:-9091}"
CERTIFY_URL="http://127.0.0.1:${CERTIFY_PORT}"
TIMEOUT=90
ELAPSED=0

while [ "$ELAPSED" -lt "$TIMEOUT" ]; do
  if curl -sf "${CERTIFY_URL}/.well-known/openid-credential-issuer" >/dev/null 2>&1 || \
     curl -sf "${CERTIFY_URL}/v1/certify/.well-known/openid-credential-issuer" >/dev/null 2>&1; then
    echo "Inji Certify is ready!"
    break
  fi
  sleep 3
  ELAPSED=$((ELAPSED + 3))
done

if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
  echo "Error: Inji Certify failed to become ready within ${TIMEOUT}s. Recent logs:"
  docker compose logs --tail 50 certify
  exit 1
fi

echo "Running post-deployment issuance smoke test..."
if ! bash scripts/smoke-test.sh "${CERTIFY_URL}"; then
  echo "Error: Post-deployment smoke test failed. Recent logs:"
  docker compose logs --tail 50 certify
  exit 1
fi

echo "Stack status:"
docker compose ps
