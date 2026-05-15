#!/usr/bin/env bash
# Install git pre-commit hook for the human persona.
#
# Covers the enforcement gap where a human editing files directly bypasses
# ALL PreToolUse:Write|Edit hooks (thinking_os gate, doc-anchor, bad-patterns,
# task-frontmatter, etc.). The pre-commit hook runs the critical subset on
# staged files before git commit.
#
# Install: bash scripts/install-git-hooks.sh
# Uninstall: rm .git/hooks/pre-commit
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_FILE="${REPO_ROOT}/.git/hooks/pre-commit"
SOURCE_HOOK="${REPO_ROOT}/scripts/_pre_commit_body.sh"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  echo "ERROR: not a git repository root: ${REPO_ROOT}" >&2
  exit 1
fi

if [[ ! -f "$SOURCE_HOOK" ]]; then
  echo "ERROR: source hook body not found: $SOURCE_HOOK" >&2
  exit 1
fi

mkdir -p "${REPO_ROOT}/.git/hooks"
cp "$SOURCE_HOOK" "$HOOK_FILE"
chmod +x "$HOOK_FILE"
echo "Installed: ${HOOK_FILE}"
echo "Covers: block-bad-patterns, validate-task-frontmatter, block-migration-conflict"
echo "Uninstall: rm ${HOOK_FILE}"
