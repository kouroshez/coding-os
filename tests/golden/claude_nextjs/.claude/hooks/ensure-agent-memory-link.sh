#!/usr/bin/env bash
# Ensure the harness memory dir is a symlink into the repo's committed
# .agents/memory (portable agent memory — survives clone/laptop swap).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
command -v cos_log_hook >/dev/null 2>&1 || cos_log_hook() { :; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "${CLAUDE_PROJECT_DIR:-$PWD}")"
REPO_MEM="$REPO_ROOT/.agents/memory"
SLUG="$(printf '%s' "$REPO_ROOT" | sed 's#/#-#g')"
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
  for file in "$HARNESS_MEM"/* "$HARNESS_MEM"/.[!.]*; do
    [ -e "$file" ] || continue
    name="$(basename "$file")"
    [ -e "$REPO_MEM/$name" ] || mv "$file" "$REPO_MEM/$name"
  done
  rmdir "$HARNESS_MEM" 2>/dev/null || mv "$HARNESS_MEM" "$HARNESS_MEM.bak-$(date +%Y%m%d%H%M%S)"
fi

mkdir -p "$(dirname "$HARNESS_MEM")"
ln -s "$REPO_MEM" "$HARNESS_MEM"
cos_log_hook ensure-agent-memory-link allow "linked=$HARNESS_MEM" || true
exit 0
