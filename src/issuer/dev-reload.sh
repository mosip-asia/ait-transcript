#!/usr/bin/env bash
# ==============================================================================
# Loop 3: Fast Compile & Reload Helper
# ==============================================================================
# Compiles the Java SPI plugin and restarts Inji Certify with the fresh JAR
# in ~3 seconds. Requires docker-compose.override.yml to be enabled.
# ==============================================================================
set -euo pipefail
ISSUER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ISSUER_DIR"

if [[ ! -f "docker-compose.override.yml" ]]; then
  echo "==> Enabling docker-compose.override.yml for local JAR mounting..."
  cp docker-compose.override.yml.example docker-compose.override.yml
fi

echo "==> [1/2] Compiling plugin JAR..."
if command -v mvn >/dev/null 2>&1; then
  mvn -f plugin/pom.xml -q clean package -DskipTests
else
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$ISSUER_DIR/plugin:/src" -w /src \
    maven:3.9-eclipse-temurin-21 mvn -q clean package -DskipTests
fi

echo "==> [2/2] Restarting Inji Certify with fresh JAR..."
docker compose restart certify

echo ""
echo "✓ Certify restarted with updated plugin JAR in ~3 seconds!"
