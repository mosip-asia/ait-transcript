#!/usr/bin/env bash
# ==============================================================================
# Release and promotion helper: the SAME file across mosip-asia repositories
# (ait-oauth-adapter, ait-sis-adapter, ait-transcript). Each repository's own checks
# (tests, realm files, compose configuration...) live in scripts/release-checks.sh,
# which defines run_release_checks.
#
# One pipeline (.github/workflows/cd.yml), three environments:
#   dev         <- every release tag v* cut from 'dev'   (GCE VM issuer-dev / issuer-dev-vm)
#   uat         <- every push to branch 'uat'             (GCE VM issuer-uat / issuer-uat-vm)
#   production  <- every push to branch 'main'            (campus VM ait-itserv-vm)
#
# Usage (Git Bash on Windows; any bash elsewhere):
#   scripts/release.sh vX.Y.Z                 Run the checks, tag the tip of origin/dev as vX.Y.Z and
#                                              push the tag (it deploys to dev), then create the
#                                              GitHub Release.
#   scripts/release.sh promote uat [vX.Y.Z]    Fast-forward branch 'uat' to a release tag (default:
#                                              the newest tag on dev); the push deploys it to uat.
#   scripts/release.sh promote main [vX.Y.Z]   Fast-forward branch 'main' to the release tag that
#                                              'uat' is at; the push deploys it to production.
#
# Rules: versions only go up and tags never move (Fail Forward); a promotion is a fast-forward
# to a release tag, never a merge commit or a force push. Resume: if a run created the tag
# locally but its push failed, run the same command again. Pushes and the GitHub Release are
# retried, since GitHub answers transient 5xx errors now and then.
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
    if ((n >= attempts)); then
      return 1
    fi
    log_warn "Attempt ${n}/${attempts} failed: $*. Retrying in ${delay}s..."
    n=$((n + 1))
    sleep "$delay"
  done
}

confirm() {
  local answer
  read -r -p "$1 [y/N]: " answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

banner() {
  echo ""
  echo -e "${BOLD}======================================================================${NC}"
  echo -e "${BOLD}  $*${NC}"
  echo -e "${BOLD}======================================================================${NC}"
}

SCRIPT_PATH="${BASH_SOURCE[0]}"
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd -P)"
cd "$ROOT_DIR"

# Docker Compose on Windows splits COMPOSE_FILE on ';' unless told otherwise; the checks use ':'.
export COMPOSE_PATH_SEPARATOR=:

SEMVER='^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?$'
REPO_SLUG="$(git remote get-url origin | sed -E 's#\.git$##; s#^.*github\.com[:/]##')"
ACTIONS_URL="https://github.com/${REPO_SLUG}/actions/workflows/cd.yml"

describe_env() {
  case "$1" in
    dev) echo "dev (GCE VM issuer-dev / issuer-dev-vm)" ;;
    uat) echo "uat (GCE VM issuer-uat / issuer-uat-vm)" ;;
    main) echo "production (campus VM ait-itserv-vm)" ;;
  esac
}

usage() {
  sed -n '2,24p' "$SCRIPT_PATH" | sed 's/^# \{0,1\}//'
}

# release_tags [ref]: release tags (vX.Y.Z), oldest first; only those reachable from ref if given
release_tags() {
  if [[ -n "${1:-}" ]]; then
    git tag --merged "$1" --list 'v*'
  else
    git tag --list 'v*'
  fi | { grep -E "$SEMVER" || true; } | sort -V
}

# ------------------------------------------------------------------------------
# release vX.Y.Z: tag the tip of origin/dev; the tag push deploys it to dev
# ------------------------------------------------------------------------------
release() {
  local version="$1"
  if [[ ! "$version" =~ $SEMVER ]]; then
    log_err "Invalid version tag '${version}'."
    log_err "Use Semantic Versioning with a leading 'v' (e.g. v0.0.10, v1.0.0, v1.0.0-rc1)."
    exit 1
  fi

  log_info "Running local pre-flight checks..."
  if [[ -n "$(git status --porcelain)" ]]; then
    log_err "Working tree is dirty. Please commit, stash, or discard local changes first:"
    git status -s
    exit 1
  fi

  log_info "Fetching the latest branches and tags from origin..."
  retry 3 5 git fetch -q --tags origin
  local dev_commit
  dev_commit="$(git rev-parse origin/dev)"

  # A tag on origin means the version is released; a local-only tag at origin/dev means an
  # earlier run was interrupted after creating it, and this run resumes from the push.
  local resume=false
  if git ls-remote --exit-code --tags origin "refs/tags/${version}" >/dev/null 2>&1; then
    log_err "Tag '${version}' already exists on origin: this version is released."
    log_err "To move it on: scripts/release.sh promote uat ${version}"
    exit 1
  fi
  if git rev-parse -q --verify "refs/tags/${version}" >/dev/null; then
    local tag_commit
    tag_commit="$(git rev-parse "${version}^{commit}")"
    if [[ "$tag_commit" == "$dev_commit" ]]; then
      log_warn "Tag '${version}' exists locally at ${tag_commit:0:7} (= origin/dev) but not on origin."
      log_warn "Resuming the interrupted release: the tag will be pushed and the GitHub Release created."
      resume=true
    else
      log_err "Tag '${version}' exists locally at ${tag_commit:0:7}, but origin/dev is at ${dev_commit:0:7}."
      log_err "Delete the local tag ('git tag -d ${version}') and run again."
      exit 1
    fi
  fi

  local previous
  previous="$(release_tags | tail -n 1)"
  if [[ "$resume" == false && -n "$previous" ]]; then
    if [[ "$(printf '%s\n%s\n' "$previous" "$version" | sort -V | tail -n 1)" != "$version" ]]; then
      log_err "Version ${version} is not higher than the newest release ${previous}: versions only go up."
      exit 1
    fi
  fi

  if [[ "$resume" == false ]]; then
    if [[ "$(git rev-parse --abbrev-ref HEAD)" != "dev" ]]; then
      log_info "Switching to 'dev'..."
      git checkout -q dev
    fi
    log_info "Updating 'dev' from origin (fast-forward only)..."
    git merge -q --ff-only origin/dev
    if [[ "$(git rev-parse HEAD)" != "$dev_commit" ]]; then
      log_err "Local 'dev' ($(git rev-parse --short HEAD)) has commits that are not on origin/dev (${dev_commit:0:7})."
      log_err "Releases are cut from what is on GitHub: merge them through a pull request first."
      exit 1
    fi
    log_ok "'dev' matches origin/dev at ${dev_commit:0:7}."

    log_info "Running this repository's release checks (scripts/release-checks.sh)..."
    # shellcheck source=/dev/null
    source scripts/release-checks.sh
    run_release_checks
    log_ok "Release checks passed."
  fi

  # Preview & confirmation gate
  if [[ "$resume" == true ]]; then
    banner "RESUME RELEASE: ${GREEN}${version}${NC}"
    echo -e "Tag ${YELLOW}${version}${NC} already points at ${dev_commit:0:7} (= origin/dev)."
    echo -e "This run only pushes the tag (which deploys to dev) and creates the GitHub Release."
  else
    banner "RELEASE PREVIEW: ${GREEN}${version}${NC}"
    local since
    since="$(release_tags origin/dev | tail -n 1)"
    if [[ -n "$since" ]]; then
      echo -e "Commits since ${YELLOW}${since}${NC}:"
      git --no-pager log --oneline "${since}..${dev_commit}"
    else
      echo -e "Initial release commits:"
      git --no-pager log --oneline -n 10 "$dev_commit"
    fi
  fi
  echo -e "${BOLD}Release commit:${NC} ${dev_commit:0:7} (tip of origin/dev)"
  echo -e "${BOLD}Tag:${NC}            ${version}"
  echo -e "${BOLD}Deploys to:${NC}     $(describe_env dev), when the tag is pushed"
  echo -e "${BOLD}Then:${NC}           scripts/release.sh promote uat ${version}"
  echo ""

  if ! confirm "Tag ${version} and deploy it to dev?"; then
    log_warn "Release aborted; nothing was tagged or pushed."
    exit 0
  fi

  if [[ "$resume" == false ]]; then
    log_info "Creating annotated tag '${version}' on ${dev_commit:0:7}..."
    git tag -a "$version" -m "Release $version" "$dev_commit"
  fi

  log_info "Pushing tag '${version}' (this starts the deployment to dev)..."
  if ! retry 3 5 git push -q origin "refs/tags/${version}"; then
    log_err "Pushing tag '${version}' failed three times (the tag exists locally)."
    log_err "Run the same command again later to resume: scripts/release.sh ${version}"
    exit 1
  fi
  log_ok "Tag '${version}' pushed to GitHub."

  # GitHub Release with auto-generated notes if the gh CLI is authenticated
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    log_info "Creating the GitHub Release with auto-generated release notes..."
    if retry 3 10 gh release create "$version" --title "Release $version" --generate-notes >/dev/null; then
      log_ok "GitHub Release published."
    else
      log_warn "GitHub Release not created (the deployment is already triggered by the tag). Create it later with:"
      log_warn "  gh release create ${version} --title \"Release ${version}\" --generate-notes"
    fi
  fi

  banner "${GREEN}🎉 Release ${version} cut: deploying to dev${NC}"
  echo -e "Watch the deployment: ${BLUE}${ACTIONS_URL}${NC}"
  echo -e "After testing on dev: ${BOLD}scripts/release.sh promote uat ${version}${NC}"
  echo ""
}

# ------------------------------------------------------------------------------
# promote uat|main [vX.Y.Z]: fast-forward the branch to a release tag; the push deploys it
# ------------------------------------------------------------------------------
promote() {
  local target="${1:-}" version="${2:-}"
  if [[ "$target" != "uat" && "$target" != "main" ]]; then
    log_err "Usage: scripts/release.sh promote uat|main [vX.Y.Z]"
    exit 2
  fi
  if [[ -n "$version" && ! "$version" =~ $SEMVER ]]; then
    log_err "Invalid version tag '${version}'."
    exit 1
  fi

  log_info "Fetching the latest branches and tags from origin..."
  retry 3 5 git fetch -q --tags origin

  local src tag
  if [[ "$target" == "uat" ]]; then
    tag="${version:-$(release_tags origin/dev | tail -n 1)}"
    if [[ -z "$tag" ]]; then
      log_err "There is no release tag on dev yet: run scripts/release.sh vX.Y.Z first."
      exit 1
    fi
    if ! git ls-remote --exit-code --tags origin "refs/tags/${tag}" >/dev/null 2>&1; then
      log_err "Tag '${tag}' is not on origin: release it first with scripts/release.sh ${tag}"
      exit 1
    fi
    src="$(git rev-parse "${tag}^{commit}")"
    if ! git merge-base --is-ancestor "$src" origin/dev; then
      log_err "Tag '${tag}' (${src:0:7}) is not on 'dev': only releases cut from dev are promoted."
      exit 1
    fi
  else
    if ! git rev-parse -q --verify origin/uat >/dev/null; then
      log_err "Branch 'uat' does not exist yet: run scripts/release.sh promote uat first."
      exit 1
    fi
    src="$(git rev-parse origin/uat)"
    if [[ -n "$version" ]]; then
      if ! git tag --points-at "$src" | grep -qxF "$version"; then
        log_err "'uat' (${src:0:7}) is not at ${version}: promote ${version} to uat and test it there first."
        exit 1
      fi
      tag="$version"
    else
      tag="$(git tag --points-at "$src" --list 'v*' | { grep -E "$SEMVER" || true; } | sort -V | tail -n 1)"
    fi
    if [[ -z "$tag" ]]; then
      log_err "'uat' (${src:0:7}) is not at a release tag: only a released and tested commit goes to production."
      exit 1
    fi
  fi

  local current=""
  if git rev-parse -q --verify "origin/${target}" >/dev/null; then
    current="$(git rev-parse "origin/${target}")"
    if [[ "$current" == "$src" ]]; then
      log_ok "'${target}' is already at ${tag} (${src:0:7}): nothing to do."
      exit 0
    fi
    if ! git merge-base --is-ancestor "$current" "$src"; then
      log_err "'${target}' (${current:0:7}) is not an ancestor of ${tag} (${src:0:7}): a promotion is a fast-forward only."
      log_err "Either the version is older than what '${target}' has, or '${target}' was changed directly. Never force-push it."
      exit 1
    fi
  fi

  banner "PROMOTE ${GREEN}${tag}${NC}${BOLD} to '${target}'"
  if [[ -n "$current" ]]; then
    echo -e "Commits that reach '${target}' (from ${current:0:7}):"
    git --no-pager log --oneline "${current}..${src}"
  else
    echo -e "'${target}' does not exist on origin yet: it is created at ${tag}."
    git --no-pager log --oneline -n 5 "$src"
  fi
  echo -e "${BOLD}Promotes:${NC}   ${tag} (${src:0:7})"
  echo -e "${BOLD}Deploys to:${NC} $(describe_env "$target"), when '${target}' is pushed"
  echo ""
  if [[ "$target" == "main" ]]; then
    log_warn "This deploys to PRODUCTION (the campus VM)."
  fi

  if ! confirm "Promote ${tag} to '${target}' and deploy it?"; then
    log_warn "Promotion aborted; nothing was pushed."
    exit 0
  fi

  log_info "Pushing ${tag} to '${target}' (this starts the deployment)..."
  if ! retry 3 5 git push -q origin "${src}:refs/heads/${target}"; then
    log_err "Pushing '${target}' failed three times. Run the same command again later."
    exit 1
  fi

  banner "${GREEN}🎉 ${tag} promoted to '${target}': deploying to $(describe_env "$target")${NC}"
  echo -e "Watch the deployment: ${BLUE}${ACTIONS_URL}${NC}"
  if [[ "$target" == "uat" ]]; then
    echo -e "After testing on UAT: ${BOLD}scripts/release.sh promote main${NC}"
  fi
  echo ""
}

# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------
case "${1:-}" in
  promote)
    shift
    promote "$@"
    ;;
  -h | --help)
    usage
    ;;
  "")
    usage
    echo ""
    read -r -p "Version to release (e.g. v0.0.10), or Enter to stop: " ANSWER
    if [[ -z "$ANSWER" ]]; then
      exit 0
    fi
    release "$ANSWER"
    ;;
  *)
    release "$1"
    ;;
esac
