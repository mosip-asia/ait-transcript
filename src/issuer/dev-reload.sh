#!/usr/bin/env bash
# ==============================================================================
# Loop 3: Fast Compile & Reload Helper
# ==============================================================================
# Compiles the Java SPI plugin and updates Inji Certify with the fresh JAR
# in ~3 seconds using compose.dev.yaml.
# ==============================================================================
set -euo pipefail
ISSUER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ISSUER_DIR"

# Ensure hot-reload file overlay is active for this reload
export COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml:compose.dev.yaml}"

echo "==> [1/2] Compiling plugin JAR..."
if command -v mvn >/dev/null 2>&1; then
  mvn -f plugin/pom.xml -q clean package -DskipTests
else
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$ISSUER_DIR/plugin:/src" -w /src \
    maven:3.9-eclipse-temurin-21 mvn -q clean package -DskipTests
fi

echo "==> [2/2] Updating Inji Certify with fresh JAR (using $COMPOSE_FILE)..."
docker compose up -d certify

echo ""
echo "✓ Certify updated with latest plugin JAR in ~3 seconds!"
