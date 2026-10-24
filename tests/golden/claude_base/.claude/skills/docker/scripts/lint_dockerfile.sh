#!/usr/bin/env bash
# lint_dockerfile.sh — PURPOSE: flag a Dockerfile against the image-craft rules.
# INPUT: one Dockerfile path. OUTPUT: findings on stderr, "<n> issue(s)" on
# stdout; exit 1 if any. DEPS: grep, awk. NOTES: heuristic, fail-closed; a clean
# pass is necessary not sufficient. Spec: docs/playbooks/skill-authoring.md.
set -euo pipefail
IFS=$'\n\t'

log() { printf '%s\n' "$*" >&2; }
[[ $# -eq 1 ]] || { echo "usage: $0 <Dockerfile>" >&2; exit 2; }
f="$1"
[[ -f "$f" ]] || { echo "error: $f not found" >&2; exit 2; }

issues=0
flag() { log "  ✗ $1"; issues=$((issues + 1)); }

# Untagged or :latest base image.
if grep -iE '^[[:space:]]*FROM[[:space:]]+[^[:space:]]+(:latest)?[[:space:]]*($|AS)' "$f" \
     | grep -ivqE ':[a-z0-9._-]+'; then
  flag "FROM has no version tag (or uses :latest) — pin an explicit version"
fi
grep -iqE '^[[:space:]]*FROM[^:]*:latest' "$f" && flag "FROM uses :latest — pin a version"

# Runs as root: no USER directive at all.
grep -iqE '^[[:space:]]*USER[[:space:]]' "$f" || flag "no USER directive — container runs as root"

# Secret baked via ARG/ENV (heuristic on common secret names).
if grep -iE '^[[:space:]]*(ARG|ENV)[[:space:]]' "$f" \
     | grep -iqE '(secret|token|password|passwd|api[_-]?key|private[_-]?key)'; then
  flag "secret-shaped ARG/ENV — bakes the secret into image history; use --mount=type=secret"
fi

# ADD of a local path where COPY is correct (ADD line without a URL).
if grep -iE '^[[:space:]]*ADD[[:space:]]' "$f" | grep -ivqE 'https?://'; then
  flag "ADD used for a local file — prefer COPY (ADD auto-extracts + fetches URLs)"
fi

# apt update without cleanup in the same/any RUN.
if grep -iqE 'apt(-get)?[[:space:]]+(update|install)' "$f" \
   && ! grep -iqE 'rm[[:space:]]+-rf[[:space:]]+/var/lib/apt/lists' "$f"; then
  flag "apt install without 'rm -rf /var/lib/apt/lists/*' — ships the package index"
fi

# .dockerignore alongside the Dockerfile.
[[ -f "$(dirname "$f")/.dockerignore" ]] || log "  · no .dockerignore next to $f (ships .git/node_modules into context)"

printf '%d issue(s)\n' "$issues"
[[ "$issues" -eq 0 ]]
