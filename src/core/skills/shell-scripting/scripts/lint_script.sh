#!/usr/bin/env bash
# lint_script.sh — PURPOSE: check a script against the seven non-negotiables.
# INPUT: one or more script paths (*.sh / *.py). OUTPUT: findings on stderr,
# "<n> issue(s)" result on stdout; exit 1 if any issue. DEPS: grep, bash,
# and ShellCheck when available. NOTES: heuristic and fail-closed; a clean
# pass is necessary not sufficient. Spec: docs/playbooks/skill-authoring.md.
set -euo pipefail
IFS=$'\n\t'

log() { printf '%s\n' "$*" >&2; }
usage() { echo "usage: $0 <script> [<script> ...]" >&2; exit 2; }
[[ $# -ge 1 ]] || usage

issues=0

flag() { log "  ✗ $1"; issues=$((issues + 1)); }

# NOTE: grep the file directly, never a "$(cat)" here-string — large
# here-strings deadlock under this bash (see bash-heredoc-deadlock.md).
check_bash() {
  local f="$1"
  head -1 "$f" | grep -qE '^#!.*(bash|sh)' || flag "$f: missing shebang"
  grep -qE 'set -[a-z]*e[a-z]* ' "$f" || flag "$f: no 'set -euo pipefail'"
  grep -q 'trap ' "$f" || log "  · $f: no trap (ok if no temp state)"
  if grep -nE '(/Users/[A-Za-z]|/home/[a-z])' "$f" | grep -qvE '^[0-9]+:[[:space:]]*#'; then
    flag "$f: hardcoded absolute home path — take a flag instead"
  fi
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -S warning "$f" >/dev/null 2>&1 || flag "$f: shellcheck warnings (run: shellcheck $f)"
  fi
}

check_python() {
  local f="$1"
  grep -q 'argparse' "$f" || grep -q 'sys.argv' "$f" \
    || flag "$f: no argument parsing (argparse/sys.argv)"
  if grep -nE "['\"](/Users/[A-Za-z]|/home/[a-z])" "$f" | grep -qvE '^[0-9]+:[[:space:]]*#'; then
    flag "$f: hardcoded absolute home path — take a flag instead"
  fi
}

for f in "$@"; do
  [[ -f "$f" ]] || { flag "$f: not a file"; continue; }
  log "checking $f"
  case "$f" in
    *.sh) check_bash "$f" ;;
    *.py) check_python "$f" ;;
    *) log "  · $f: unknown type, skipped" ;;
  esac
done

printf '%d issue(s)\n' "$issues"
[[ "$issues" -eq 0 ]]
