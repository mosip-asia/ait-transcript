# shellcheck shell=bash
# ==============================================================================
# This repository's release checks, sourced by scripts/release.sh. Defines
# run_release_checks; it runs from the repository root on the commit being
# released and returns non-zero when a check fails.
# ==============================================================================

run_release_checks() {
  log_info "Running the sensitive data guard..."
  if ! bash scripts/check-data-guard.sh; then
    log_err "The data guard refused the tree (spreadsheets, CSV files, CRLF line endings or large files)."
    return 1
  fi

  log_info "Validating Docker Compose configurations..."
  local temp_env=false rc=0
  if [[ ! -f .env ]]; then
    cp .env.example .env
    temp_env=true
  fi
  # Pin ':' as the separator: Docker Compose on Windows splits COMPOSE_FILE on ';' by default,
  # while .env.example and the Linux hosts use the ':' form.
  if ! COMPOSE_PATH_SEPARATOR=: docker compose config --quiet; then
    log_err "Base compose.yaml configuration failed validation."
    rc=1
  elif ! COMPOSE_PATH_SEPARATOR=: COMPOSE_FILE=compose.yaml:compose.verify.yaml docker compose config --quiet; then
    log_err "Verifier overlay compose configuration failed validation."
    rc=1
  elif ! COMPOSE_PATH_SEPARATOR=: COMPOSE_FILE=compose.yaml:compose.demo.yaml docker compose config --quiet; then
    log_err "Demo overlay compose configuration failed validation."
    rc=1
  fi
  if [[ "$temp_env" == true ]]; then
    rm -f .env
  fi
  if [[ "$rc" -ne 0 ]]; then
    return "$rc"
  fi

  log_info "Validating JSON schemas, credentials, and fixtures..."
  local py=""
  for candidate in .venv/bin/python python3 python; do
    if [[ -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0)' >/dev/null 2>&1; then
        py="$candidate"
        break
      fi
    fi
  done
  if [[ -n "$py" ]]; then
    for f in docs/schemas/*.json deploy/*/credentials/*.json deploy/*/contexts/*/*.json deploy/base/*.json tests/fixtures/*.json; do
      if [[ -f "$f" ]]; then
        if ! "$py" -m json.tool "$f" >/dev/null; then
          log_err "JSON syntax error in $f"
          return 1
        fi
      fi
    done
    log_ok "JSON syntax verified."
  fi

  log_info "Running host test suite..."
  local test_py=""
  if [[ -x .venv/bin/python ]]; then
    test_py=".venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    test_py="python3"
  else
    log_err "No python interpreter found to run host tests."
    return 1
  fi

  for t in \
    src/tools/test_generate_csv.py \
    src/tools/test_render_mimoto_issuers_config.py \
    src/verifier/test_verifier.py \
    tests/test_installations.py \
    tests/test_authorization_server.py \
    tests/test_inji_web_vc_readiness.py \
    tests/test_issue_and_verify.py \
    tests/test_adapter.py \
    tests/test_courses.py \
    src/gateway/tests/test_evaluations.py
  do
    if ! "$test_py" "$t" >/dev/null 2>&1; then
      log_err "Test failed: $t"
      return 1
    fi
  done
  log_ok "Host test suite passed."
}
