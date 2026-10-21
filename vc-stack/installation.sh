# Sourced by run-demo.sh, bootstrap.sh and smoke.sh before they touch Docker.
# INSTALLATION names the directory under installations/ that docker-compose.yaml
# mounts; the environment wins over vc-stack/.env, which wins over the marker file
# vc-stack/.installation. Exits when it names no directory,
# otherwise exports INSTALLATION (for Compose) and sets INSTALLATION_DIR.

STACK_ENV="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"

# The last value of a key in vc-stack/.env, trimmed; empty when absent.
env_value() {
  local key="$1"
  [[ -f "$STACK_ENV" ]] || return 0
  awk -F= -v key="$key" '$1 == key { value=$2 } END { print value }' "$STACK_ENV" \
    | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

INSTALLATION="${INSTALLATION:-$(env_value INSTALLATION)}"
MARKER="$(dirname "$STACK_ENV")/.installation"
if [[ -z "$INSTALLATION" && -f "$MARKER" ]]; then
  INSTALLATION="$(head -n 1 "$MARKER" | tr -d '\r' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
fi
if [[ -z "$INSTALLATION" || ! -d "$(dirname "$STACK_ENV")/../installations/$INSTALLATION" ]]; then
  echo "INSTALLATION must name a directory under installations/ (got: '$INSTALLATION')." >&2
  echo "Set it in the environment, in vc-stack/.env or in vc-stack/.installation, e.g. INSTALLATION=ait ./run-demo.sh" >&2
  exit 1
fi
INSTALLATION_DIR="$(cd "$(dirname "$STACK_ENV")/../installations/$INSTALLATION" && pwd)"
export INSTALLATION
