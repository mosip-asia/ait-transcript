# Sourced by run-demo.sh, bootstrap.sh and smoke.sh before they touch Docker.
# INSTALLATION names the directory under installations/ that vc-stack's compose files
# mount; the environment wins over vc-stack/.env, which wins over the marker file
# vc-stack/.installation. Exits when it names no directory,
# otherwise exports INSTALLATION (for Compose) and sets INSTALLATION_DIR, REALM and ISSUER_ID, and defines
# load_auth_server_settings.

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
# The installation's stand-in Keycloak realm and Mimoto issuer id.
REALM="$(jq -r .realm "$INSTALLATION_DIR/keycloak-realm.json")"
ISSUER_ID="$(jq -r '.issuers[0].issuer_id' "$INSTALLATION_DIR/mimoto-issuers-config.json.template")"

# Sets every key of the installation's authorization-server.env (AUTH_SERVER_ISSUER, AUTH_SERVER_TOKEN_ENDPOINT, ...)
# to the value Certify runs with: read back through `docker compose config`, so .env's per-environment values win
# exactly as they do in the containers. Call it from vc-stack/ once .env exists.
load_auth_server_settings() {
  local resolved key value
  resolved=$(docker compose config --format json | jq -c '.services.certify.environment') \
    || { echo "docker compose config failed: cannot read the Authorization Server settings" >&2; exit 1; }
  for key in $(tr -d '\r' <"$INSTALLATION_DIR/authorization-server.env" | awk -F= '/^AUTH_SERVER_/ { print $1 }'); do
    value=$(jq -r --arg key "$key" '.[$key] // empty' <<<"$resolved")
    [[ -n "$value" ]] || { echo "$key is empty: set it in vc-stack/.env or $INSTALLATION_DIR/authorization-server.env" >&2; exit 1; }
    printf -v "$key" '%s' "$value"
  done
}
