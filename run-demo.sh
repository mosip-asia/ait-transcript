#!/usr/bin/env bash
# Start the full AIT Transcript VC demo: CSV sync, Inji stack, demo app (all Docker).
# INSTALLATION (environment, else vc-stack/.env, else the git-ignored vc-stack/.installation marker) names the installations/ directory: INSTALLATION=ait ./run-demo.sh
set -euo pipefail

for bin in docker jq curl awk; do
  command -v "$bin" >/dev/null || { echo "missing prerequisite: $bin" >&2; exit 1; }
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK="$ROOT/vc-stack"
source "$STACK/installation.sh"
mkdir -p "$ROOT/.demo-state"

cd "$STACK"

# .env and the external network must exist before the first Compose call below.
"$STACK/bootstrap.sh" --prepare

# The generators run as the host user, so the files they write stay the host's to edit and regenerate.
echo "==> Regenerate Certify CSV from data/students.json"
docker compose build demo-app adapter gateway
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" demo-app python data/generate_csv.py

echo "==> Render mimoto-issuers-config.json from the installation's template"
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" demo-app python data/render_mimoto_issuers_config.py

# Compose mounts the one jar into Certify's additional_jars/; the Maven repository is cached beside it (both git-ignored).
echo "==> Build the Certify data-provider plugin (gateway/plugin/) into vc-stack/plugins/"
mkdir -p "$STACK/plugins/.m2"
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$ROOT/gateway/plugin:/src" -w /src \
  -v "$STACK/plugins/.m2:/var/maven/.m2" -e MAVEN_CONFIG=/var/maven/.m2 \
  maven:3.9-eclipse-temurin-21 mvn -q -B -Duser.home=/var/maven package
cp "$ROOT/gateway/plugin/target/gateway-data-provider-plugin.jar" "$STACK/plugins/"

"$STACK/bootstrap.sh" "$@"

echo ""
echo "Demo app: http://localhost:4100"
echo "  Student portal:   http://localhost:4100/student/login"
echo "  Registrar portal: http://localhost:4100/registrar/login"
