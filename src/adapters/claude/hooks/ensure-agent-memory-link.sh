#!/usr/bin/env bash
# Ensure the harness memory dir is a symlink into the repo's committed
# .agents/memory (portable agent memory — survives clone/laptop swap).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null \
  || source "$(dirname "$0")/../../../core/hooks/cos-env.sh" 2>/dev/null || true
command -v cos_log_hook >/dev/null 2>&1 || cos_log_hook() { :; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-$PWD}")"
REPO_MEM="$REPO_ROOT/.agents/memory"
# Claude Code names a project dir by turning every character that is not an
# ASCII letter or digit into "-" (its own replace(/[^a-zA-Z0-9]/g,"-")); a path
# mapped any other way links a dir it never reads. Past 200 characters it
# appends a hash this hook cannot reproduce, so such a path is left alone.
SLUG="$(python3 -I -c 'import re, sys; print(re.sub(r"[^a-zA-Z0-9]", "-", sys.argv[1]))' "$REPO_ROOT" 2>/dev/null)" || SLUG=""
if [ -z "$SLUG" ] || [ "${#SLUG}" -gt 200 ]; then
  cos_log_hook ensure-agent-memory-link skip "slug-length=${#SLUG}" || true
  exit 0
fi
HARNESS_MEM="$HOME/.claude/projects/$SLUG/memory"

cos_log_hook ensure-agent-memory-link fire "slug=$SLUG" || true

mkdir -p "$REPO_MEM"

if [ -L "$HARNESS_MEM" ]; then
  if [ "$(readlink "$HARNESS_MEM")" = "$REPO_MEM" ]; then
    exit 0
  fi
  rm "$HARNESS_MEM"
elif [ -d "$HARNESS_MEM" ]; then
  # Migrate without clobber: an existing repo file wins over the machine copy.
  moved=""
  for file in "$HARNESS_MEM"/* "$HARNESS_MEM"/.[!.]*; do
    [ -e "$file" ] || continue
    name="$(basename "$file")"
    [ -e "$REPO_MEM/$name" ] || { mv "$file" "$REPO_MEM/$name" && moved="$moved $name"; }
  done
  # Those notes are now in the repository, under version control: say so.
  [ -z "$moved" ] || echo "coding-os: moved machine-local memory notes into .agents/memory (now version-controlled; review before committing):$moved" >&2
  rmdir "$HARNESS_MEM" 2>/dev/null || mv "$HARNESS_MEM" "$HARNESS_MEM.bak-$(date -u +%Y%m%dT%H%M%SZ)"
fi

mkdir -p "$(dirname "$HARNESS_MEM")"
ln -s "$REPO_MEM" "$HARNESS_MEM"
cos_log_hook ensure-agent-memory-link allow "linked=$HARNESS_MEM" || true
exit 0
