#!/usr/bin/env bash
# Data guard: refuse files that could carry sensitive data, or that break the repository's
# conventions, before they reach GitHub.
#
# Usage: bash scripts/check-data-guard.sh [--staged]
#   no option   check every tracked file, before a push (scripts/check.sh runs it)
#   --staged    check the files staged for the next commit, as a pre-commit hook:
#               printf '#!/bin/sh\nexec bash scripts/check-data-guard.sh --staged\n' > .git/hooks/pre-commit
#
# Refused: spreadsheets (*.xlsx *.xlsm *.xlsb *.xls *.ods), Excel lock files (~$*), database
# dumps (*.dump *.backup), SQL outside deploy/, CSV outside deploy/ and tests/, a UTF-8 byte order mark,
# CRLF line endings (except *.bat and *.cmd), and files over 512 KB (except uv.lock).
# Images (*.png *.jpg *.jpeg *.gif *.webp) are binary: only the name and size rules apply.
#
# Exit codes: 0 clean, 1 findings, 2 usage or environment error.
set -euo pipefail

die() { echo "check-data-guard: $*" >&2; exit 2; }
usage() { sed -n '2,16p' "$0"; exit 2; }

mode=tracked
case "${1:-}" in
  "") ;;
  --staged) mode=staged ;;
  *) usage ;;
esac

cd "$(git rev-parse --show-toplevel)" || die "not inside the repository"

if [ "$mode" = staged ]; then
  mapfile -t files < <(git diff --cached --name-only --diff-filter=ACMR)
  content() { git show ":$1"; }
else
  mapfile -t files < <(git ls-files)
  content() { cat -- "$1"; }
fi

limit=$((512 * 1024))
findings=0
report() { echo "REFUSED: $1: $2"; findings=$((findings + 1)); }

# Each file is copied once and checked from the copy. No reader in a pipe stops early
# (with pipefail, the writer's broken pipe would turn a hit into a miss), and tr counts raw
# bytes: grep on Git Bash strips the CR of CRLF before it matches.
copy=$(mktemp)
trap 'rm -f "$copy"' EXIT

for f in "${files[@]}"; do
  if [ "$mode" = tracked ] && [ ! -f "$f" ]; then
    continue
  fi
  case "${f##*/}" in
    '~$'*) report "$f" "Excel lock file" ;;
  esac
  case "$f" in
    *.xlsx | *.xlsm | *.xlsb | *.xls | *.ods) report "$f" "spreadsheet (credentials/data exports stay in .local/)" ;;
    *.dump | *.backup) report "$f" "database dump" ;;
    *.sql) case "$f" in deploy/*) ;; *) report "$f" "SQL outside deploy/" ;; esac ;;
    *.csv) case "$f" in deploy/*/adapter/* | tests/* | mock/* | src/tools/tests/*) ;; *) report "$f" "CSV outside allowed directories" ;; esac ;;
  esac
  content "$f" > "$copy"
  case "$f" in
    *.png | *.jpg | *.jpeg | *.gif | *.webp) ;;
    *)
      if [ "$(head -c 3 "$copy" | od -An -tx1 | tr -d ' \n')" = "efbbbf" ]; then
        report "$f" "UTF-8 byte order mark"
      fi
      case "$f" in
        *.bat | *.cmd) ;;
        *) if [ "$(tr -cd '\r' < "$copy" | wc -c | tr -d ' ')" -gt 0 ]; then
             report "$f" "CRLF line endings"
           fi ;;
      esac ;;
  esac
  size=$(wc -c < "$copy" | tr -d ' ')
  if [ "$f" != uv.lock ] && [ "$size" -gt "$limit" ]; then
    report "$f" "larger than 512 KB"
  fi
done

if [ "$findings" -gt 0 ]; then
  echo "check-data-guard: $findings finding(s)"
  exit 1
fi
echo "check-data-guard: ${#files[@]} files clean"
