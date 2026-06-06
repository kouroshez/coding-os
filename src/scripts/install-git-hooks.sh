#!/usr/bin/env bash
# Install git pre-commit + commit-msg hooks for the human persona.
#
# Covers the enforcement gap where a human editing files directly bypasses
# ALL PreToolUse:Write|Edit hooks (thinking_os gate, doc-anchor, bad-patterns,
# task-frontmatter, etc.) plus the agent-side commit-message contract.
#
# Install: bash src/scripts/install-git-hooks.sh
# Uninstall: rm .git/hooks/{pre-commit,commit-msg}
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
  REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  echo "ERROR: not a git repository root: ${REPO_ROOT}" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/.git/hooks"

install_hook() {
  local name="$1" src="$2"
  if [[ ! -f "$src" ]]; then
    echo "ERROR: source hook body not found: $src" >&2
    exit 1
  fi
  local dst="${REPO_ROOT}/.git/hooks/${name}"
  cp "$src" "$dst"
  chmod +x "$dst"
  echo "Installed: ${dst}"
}

install_hook pre-commit  "${REPO_ROOT}/src/scripts/_pre_commit_body.sh"
install_hook commit-msg  "${REPO_ROOT}/src/scripts/_commit_msg_body.sh"
install_hook post-commit "${REPO_ROOT}/src/scripts/_post_commit_body.sh"

echo ""
echo "Coverage:"
echo "  pre-commit  → block-bad-patterns, validate-task-frontmatter, block-migration-conflict"
echo "  commit-msg  → title ≤100 chars · body ≤3 lines · no attribution / USER / Persian quotes"
echo "  post-commit → append committed code files + sha to the task's Work Log"
echo "Uninstall: rm ${REPO_ROOT}/.git/hooks/{pre-commit,commit-msg,post-commit}"
