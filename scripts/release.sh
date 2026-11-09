#!/usr/bin/env bash
# ==============================================================================
# Release Helper Script for ait-transcript
#
# Automates the safe promotion from 'dev' to 'main', creates an annotated
# SemVer release tag, and triggers the CD deployment pipeline (.github/workflows/deploy.yml).
#
# Usage:
#   ./scripts/release.sh <version>
#   ./scripts/release.sh v0.1.0
#
# Resume: if a previous run created the tag locally but the push to GitHub failed
# (the tag is missing on origin and points at origin/main), running the script
# again with the same version pushes the tag and creates the GitHub Release
# instead of starting over.
# ==============================================================================
set -euo pipefail

# ANSI Color codes
BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

log_info() { echo -e "${BLUE}${BOLD}[INFO]${NC} $*"; }
log_ok() { echo -e "${GREEN}${BOLD}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}${BOLD}[WARN]${NC} $*"; }
log_err() { echo -e "${RED}${BOLD}[ERROR]${NC} $*" >&2; }

# retry <attempts> <delay-seconds> <command...>: re-run a command that failed on a transient error
retry() {
  local attempts="$1" delay="$2" n=1
  shift 2
  until "$@"; do
    if (( n >= attempts )); then
      return 1
    fi
    log_warn "Attempt ${n}/${attempts} failed: $*. Retrying in ${delay}s..."
    n=$((n + 1))
    sleep "$delay"
  done
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"

# Docker Compose on Windows splits COMPOSE_FILE on ';' unless told otherwise; this script uses ':'.
export COMPOSE_PATH_SEPARATOR=:

# Python for the JSON check
PY=""
for candidate in python3 python; do
  if "$candidate" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [[ -z "$PY" ]]; then
  log_err "No working Python interpreter found ('python3' or 'python'); needed to validate JSON files."
  exit 1
fi

# ------------------------------------------------------------------------------
# 1. Parse & Validate Arguments
# ------------------------------------------------------------------------------
VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
  echo -e "${BOLD}Target Release Version (e.g., v0.1.0):${NC} "
  read -r VERSION
fi

if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$ ]]; then
  log_err "Invalid version tag '${VERSION}'."
  log_err "Version must follow Semantic Versioning with a leading 'v' (e.g. v0.1.0, v1.0.0, v1.0.0-rc1)."
  exit 1
fi

# ------------------------------------------------------------------------------
# 2. Local Pre-Flight Safety Checks
# ------------------------------------------------------------------------------
log_info "Running local pre-flight checks..."

# Check working tree is clean
if [[ -n "$(git status --porcelain)" ]]; then
  log_err "Working tree is dirty. Please commit, stash, or discard local changes first:"
  git status -s
  exit 1
fi

log_info "Fetching latest remote refs from origin..."
git fetch origin

RESUME=false
if git ls-remote --tags origin | grep -q "refs/tags/${VERSION}$"; then
  log_err "Tag '${VERSION}' already exists on remote 'origin': this version is released."
  exit 1
fi

if git rev-parse -q --verify "refs/tags/${VERSION}" >/dev/null; then
  TAG_COMMIT="$(git rev-list -n 1 "$VERSION")"
  MAIN_COMMIT="$(git rev-parse origin/main)"
  if [[ "$TAG_COMMIT" == "$MAIN_COMMIT" ]]; then
    log_warn "Tag '${VERSION}' exists locally at ${TAG_COMMIT:0:7} (= origin/main) but not on origin."
    log_warn "Resuming the interrupted release: the tag will be pushed and the GitHub Release created."
    RESUME=true
  else
    log_err "Tag '${VERSION}' exists locally at ${TAG_COMMIT:0:7}, but origin/main is at ${MAIN_COMMIT:0:7}."
    log_err "Delete the local tag ('git tag -d ${VERSION}') or push 'main' first, then run again."
    exit 1
  fi
fi

# Validate JSON files
log_info "Validating schema and fixture JSON files..."
for f in docs/schemas/*.json deploy/*/credentials/*.json src/portal/fixtures/*.json; do
  if [[ -f "$f" ]]; then
    if ! "$PY" -m json.tool "$f" > /dev/null; then
      log_err "Syntax error in $f"
      exit 1
    fi
  fi
done
log_ok "JSON syntax verified."

# Validate Docker Compose configuration
log_info "Validating Docker Compose configurations..."
if [[ ! -f .env ]]; then
  cp .env.example .env
  TEMP_ENV=true
else
  TEMP_ENV=false
fi

if ! docker compose config --quiet; then
  log_err "Base compose.yaml configuration failed validation."
  [[ "$TEMP_ENV" == true ]] && rm -f .env
  exit 1
fi

[[ "$TEMP_ENV" == true ]] && rm -f .env
log_ok "Docker Compose configuration verified."

if [[ "$RESUME" == false ]]; then
  # ----------------------------------------------------------------------------
  # 3. Synchronize 'dev' with Remote
  # ----------------------------------------------------------------------------
  CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  DEV_BRANCH="dev"
  if ! git show-ref --verify --quiet refs/heads/dev && ! git show-ref --verify --quiet refs/remotes/origin/dev; then
    DEV_BRANCH="$CURRENT_BRANCH"
  fi

  if [[ "$CURRENT_BRANCH" != "$DEV_BRANCH" ]]; then
    log_info "Switching to '${DEV_BRANCH}' branch..."
    git checkout "$DEV_BRANCH"
  fi

  log_info "Pulling latest changes on '${DEV_BRANCH}'..."
  git pull origin "$DEV_BRANCH" || true

  # ----------------------------------------------------------------------------
  # 4. Promote into 'main'
  # ----------------------------------------------------------------------------
  log_info "Switching to 'main' branch..."
  git checkout main
  log_info "Pulling latest changes on 'main'..."
  git pull origin main

  log_info "Merging '${DEV_BRANCH}' into 'main'..."
  if ! git merge --ff-only "$DEV_BRANCH"; then
    log_warn "Fast-forward merge not possible. Performing standard merge commit..."
    git merge -m "Merge branch '${DEV_BRANCH}' for release ${VERSION}" "$DEV_BRANCH"
  fi
  log_ok "'main' successfully updated with latest changes from '${DEV_BRANCH}'."
fi

# ------------------------------------------------------------------------------
# 5. Preview & Confirmation Gate
# ------------------------------------------------------------------------------
echo ""
echo -e "${BOLD}======================================================================${NC}"
if [[ "$RESUME" == true ]]; then
  echo -e "${BOLD}                      RESUME RELEASE: ${GREEN}${VERSION}${NC}"
else
  echo -e "${BOLD}                      RELEASE PREVIEW: ${GREEN}${VERSION}${NC}"
fi
echo -e "${BOLD}======================================================================${NC}"

if [[ "$RESUME" == true ]]; then
  echo -e "Tag ${YELLOW}${VERSION}${NC} already points at $(git rev-parse --short "${VERSION}^{commit}") (= origin/main); 'main' is already pushed."
  echo -e "This run only pushes the tag (which triggers CD) and creates the GitHub Release."
else
  LAST_TAG="$(git describe --tags --abbrev=0 2>/dev/null || echo "")"
  if [[ -n "$LAST_TAG" ]]; then
    echo -e "Commits included since last tag (${YELLOW}${LAST_TAG}${NC}):"
    git log --oneline "${LAST_TAG}..main"
  else
    echo -e "Initial release commits:"
    git log --oneline -n 10 main
  fi
fi

echo -e "${BOLD}Target Commit on main:${NC} $(git rev-parse --short main)"
echo -e "${BOLD}Pushed Tag:${NC}            ${VERSION}"
echo -e "${BOLD}Deployment Target:${NC}     AIT Campus VM (transcript-demo)"
echo -e "${BOLD}======================================================================${NC}"
echo ""

read -r -p "Deploy release ${VERSION} to production? [y/N]: " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  log_warn "Release aborted by user."
  exit 0
fi

# ------------------------------------------------------------------------------
# 6. Push 'main', Tag, and Trigger CD
# ------------------------------------------------------------------------------
if [[ "$RESUME" == false ]]; then
  log_info "Pushing 'main' to origin..."
  if ! retry 3 5 git push origin main; then
    log_err "Pushing 'main' failed three times. Nothing was tagged; fix the cause and run the script again."
    exit 1
  fi

  log_info "Creating annotated tag '${VERSION}'..."
  git tag -a "$VERSION" -m "Release $VERSION"
fi

log_info "Pushing tag '${VERSION}' to trigger CD workflow..."
if ! retry 3 5 git push origin "$VERSION"; then
  log_err "Pushing tag '${VERSION}' failed three times (the tag exists locally)."
  log_err "Run the same command again later to resume: ./scripts/release.sh ${VERSION}"
  exit 1
fi

log_ok "Tag '${VERSION}' successfully pushed to GitHub!"

# Create GitHub Release with auto-generated notes if gh CLI is authenticated
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  log_info "Creating GitHub Release with auto-generated release notes..."
  if retry 3 10 gh release create "$VERSION" --title "Release $VERSION" --generate-notes; then
    log_ok "GitHub Release published."
  else
    log_warn "GitHub Release not created (the deployment is already triggered by the tag)."
  fi
fi

echo ""
echo -e "${GREEN}${BOLD}======================================================================${NC}"
echo -e "${GREEN}${BOLD} 🎉 Release ${VERSION} successfully cut!${NC}"
echo -e "${GREEN}${BOLD}======================================================================${NC}"
exit 0
