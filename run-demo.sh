#!/usr/bin/env bash
# Start the full AIT Transcript VC demo: CSV sync, Inji stack, demo app (all Docker).
set -euo pipefail

for bin in docker jq curl awk; do
  command -v "$bin" >/dev/null || { echo "missing prerequisite: $bin" >&2; exit 1; }
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
STACK="$ROOT/vc-stack"
mkdir -p "$ROOT/.demo-state"

cd "$STACK"

echo "==> Regenerate Certify CSV from data/students.json"
docker compose build demo-app
docker compose run --rm --no-deps demo-app python data/generate_csv.py

"$STACK/bootstrap.sh" "$@"

echo ""
echo "Demo app: http://localhost:4100"
echo "  Student portal:   http://localhost:4100/student/login"
echo "  Registrar portal: http://localhost:4100/registrar/login"
