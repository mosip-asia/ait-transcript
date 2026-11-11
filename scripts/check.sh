#!/usr/bin/env bash
# Local checks to run before a push: data guard, compose configs, JSON validation, and tests.
#
# Usage: bash scripts/check.sh
# Exit codes: 0 every check passed, otherwise the exit code of the first check that failed.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

step() { echo; echo "== $*"; }

step "data guard"
bash scripts/check-data-guard.sh

step "release checks"
# shellcheck source=/dev/null
source scripts/release-checks.sh
log_info() { echo "[INFO] $*"; }
log_ok() { echo "[OK] $*"; }
log_warn() { echo "[WARN] $*"; }
log_err() { echo "[ERROR] $*" >&2; }
run_release_checks

echo
echo "check: all passed"
