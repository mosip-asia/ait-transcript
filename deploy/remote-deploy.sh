#!/usr/bin/env bash
# Runs ON the transcript-demo VM as root. The Deploy workflow
# (.github/workflows/deploy.yml) copies it into the deploy user's home, runs it
# with sudo, then deletes it. It checks out exactly one commit of this repo
# into /opt/ait-transcript-demo and starts the stack with run-demo.sh.
#
# The GitHub token arrives on stdin: the run's own GITHUB_TOKEN, which expires
# when the run ends. It reaches git only through environment variables, so it
# never lands in a URL, on a command line, in .git/config or on disk.
#
# Contract with the VM (mosip-asia/ait-vc, ait-vc-transcript-demo/terraform/startup.sh.tpl):
#   /opt/ait-transcript-demo                the checkout
#   /etc/ait-transcript-demo/app.env        public URLs, copied to vc-stack/.env
#   /run/lock/transcript-demo-deploy.lock   a deploy and a boot-time restart never overlap
#
# Usage (as root, token on stdin): bash remote-deploy.sh <40-hex commit> <owner/repo>
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

SHA="${1:-}"
REPO="${2:-}"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]] || [[ ! "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "usage: remote-deploy.sh <40-hex commit> <owner/repo>" >&2
  exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (sudo)" >&2
  exit 2
fi

TOKEN=""
IFS= read -r TOKEN || true
# Nothing below may read the SSH channel (docker compose run would try).
exec </dev/null
if [ -z "$TOKEN" ]; then
  echo "no token on stdin" >&2
  exit 2
fi

REPO_DIR=/opt/ait-transcript-demo
APP_ENV=/etc/ait-transcript-demo/app.env
LOCK=/run/lock/transcript-demo-deploy.lock
NETWORK=vc_stack_network

if [ ! -f "$APP_ENV" ] || ! command -v docker >/dev/null || ! command -v git >/dev/null; then
  echo "the VM's startup script has not finished yet (sudo journalctl -u google-startup-scripts)" >&2
  exit 1
fi

# git takes the header from the environment only (GIT_CONFIG_COUNT, git >= 2.31).
AUTH_HEADER="AUTHORIZATION: basic $(printf 'x-access-token:%s' "$TOKEN" | base64 -w0)"
unset TOKEN
git_auth() {
  GIT_TERMINAL_PROMPT=0 GIT_CONFIG_COUNT=1 \
    GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
    GIT_CONFIG_VALUE_0="$AUTH_HEADER" \
    git "$@"
}

exec 9>"$LOCK"
if ! flock -w 1200 9; then
  echo "another deploy, or the boot-time restart, still holds $LOCK" >&2
  exit 1
fi

[ -d "$REPO_DIR/.git" ] || git init -q "$REPO_DIR"
cd "$REPO_DIR"
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$REPO.git"
git_auth fetch -q --no-tags --depth=1 origin "$SHA"
unset AUTH_HEADER
# --force resets tracked files the stack changed at run time (run-demo.sh
# regenerates them); ignored files such as vc-stack/.env and .demo-state stay.
git checkout -q --force --detach "$SHA"
if [ "$(git rev-parse HEAD)" != "$SHA" ]; then
  echo "checkout mismatch: HEAD is $(git rev-parse HEAD)" >&2
  exit 1
fi
echo "checked out $SHA"

# run-demo.sh uses this network (docker compose run) before
# vc-stack/bootstrap.sh creates it, so create it first on a fresh VM.
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null

cp "$APP_ENV" vc-stack/.env
./run-demo.sh
echo "deployed $SHA"
