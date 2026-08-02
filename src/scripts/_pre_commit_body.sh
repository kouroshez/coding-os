#!/usr/bin/env bash
# cos pre-commit — critical validation for human direct edits.
# Installed by: bash scripts/install-git-hooks.sh
# Covers the enforcement gap where a human editing files directly bypasses
# ALL PreToolUse:Write|Edit hooks.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/src/core/hooks"

if [[ ! -d "$HOOKS_DIR" && -d "${REPO_ROOT}/core/hooks" ]]; then
  HOOKS_DIR="${REPO_ROOT}/core/hooks"
fi
if [[ -d "${REPO_ROOT}/.claude/hooks" ]]; then
  HOOKS_DIR="${REPO_ROOT}/.claude/hooks"
fi

source "${HOOKS_DIR}/cos-env.sh" 2>/dev/null || true

# _helpers/ is NOT symlinked into a consumer's .claude/hooks/, so resolve it
# through cos-env.sh's own symlink chain (then fall back to the meta tree).
HELPERS_DIR="${HOOKS_DIR}/_helpers"
if command -v _cos_helpers_dir >/dev/null 2>&1; then
  HELPERS_DIR="$(_cos_helpers_dir)"
fi
[[ -d "$HELPERS_DIR" ]] || HELPERS_DIR="${REPO_ROOT}/src/core/hooks/_helpers"

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)

if [[ -z "$STAGED_FILES" ]]; then
  exit 0
fi

FILE_COUNT=$(echo "$STAGED_FILES" | wc -l | tr -d ' ')
echo "cos pre-commit: checking ${FILE_COUNT} staged file(s)..."

# Committed agent memory (.agents/memory/**) travels to the remote — a leaked
# credential there is public. Scan staged memory files for classic secret
# shapes and BLOCK on any hit (fail-closed for this narrow, high-risk path).
MEMORY_STAGED=$(echo "$STAGED_FILES" | grep -E '^\.agents/memory/' || true)
if [[ -n "$MEMORY_STAGED" ]]; then
  SECRET_RE='-----BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|xox[baprs]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{35}'
  # Process substitution, never a herestring read-loop: the herestring's
  # tmp-file path deadlocks under bash 5.3.9 in git's hook environment
  # (repo-wide ban, enforced by test_pre_commit_no_deadlock).
  while IFS= read -r mem_file; do
    [[ -f "$mem_file" ]] || continue
    if git show ":$mem_file" 2>/dev/null | grep -qE "$SECRET_RE"; then
      echo "cos pre-commit: BLOCKED — credential-shaped content in $mem_file" >&2
      echo "  .agents/memory is committed and shared; remove the secret before committing." >&2
      exit 1
    fi
  done < <(printf '%s\n' "$MEMORY_STAGED")
fi

# Delegate the per-file iteration to a single Python helper. The previous
# bash-loop implementation (even with mktemp IPC) deadlocks git-commit's
# hook environment beyond ~15 staged files — bash 5.x fork-bombs and
# loses pipe synchronization. The Python helper does the same work in
# one process: no nested subshells, no per-file fork-bomb.
BATCH_HELPER="${HELPERS_DIR}/pre_commit_batch.py"

if [[ ! -f "$BATCH_HELPER" ]]; then
  echo "cos pre-commit: WARNING — batch helper missing; skipping hook scan." >&2
  echo "  expected at: $BATCH_HELPER" >&2
  exit 0
fi

# Pass file list as positional args (one per arg, no shell-word splits).
# Feed the loop via process substitution, NOT a `<<<` here-string: `<<<`
# writes the whole list to a self-pipe before the reader drains it, which
# deadlocks once the (shared-index) staged set exceeds the pipe buffer — the
# bash 5.x heredoc deadlock this file's own header warns about (Rule 8). The
# `< <(printf …)` form is drained line-by-line by read, so it never buffers
# the whole list and cannot deadlock regardless of staged-set size.
FILE_ARGS=()
while IFS= read -r FILE; do
  [[ -z "$FILE" ]] && continue
  FILE_ARGS+=("$FILE")
done < <(printf '%s\n' "$STAGED_FILES")

# Run the batch under a hard wall-clock ceiling so a stuck hook child can
# never hang this commit (or orphan into the next one). pre_commit_batch.py
# already kills each hook at 15s; this is the cumulative/python-level backstop.
COS_PRECOMMIT_TIMEOUT="${COS_PRECOMMIT_TIMEOUT:-180}"
source "${HELPERS_DIR}/run_with_reap_timeout.sh" 2>/dev/null || true

set +e
if command -v cos_run_with_reap_timeout >/dev/null 2>&1; then
  cos_run_with_reap_timeout "$COS_PRECOMMIT_TIMEOUT" \
    python3 "$BATCH_HELPER" "$HOOKS_DIR" "$REPO_ROOT" "${FILE_ARGS[@]}"
else
  python3 "$BATCH_HELPER" "$HOOKS_DIR" "$REPO_ROOT" "${FILE_ARGS[@]}"
fi
BATCH_RC=$?
set -e

if [[ "$BATCH_RC" -eq 0 ]]; then
  echo "cos pre-commit: OK"
  exit 0
elif [[ "$BATCH_RC" -eq 1 ]]; then
  echo "" >&2
  echo "cos pre-commit: commit blocked. Fix the issues above and re-stage." >&2
  echo "To skip (NOT recommended): git commit --no-verify" >&2
  exit 1
else
  # Non-0/1: the watchdog reaped a hang (SIGKILL 137 / SIGTERM 143 / timeout
  # 124) OR the batch helper itself crashed. Fail OPEN either way — a permanent
  # block would brick commits (the agent path cannot use --no-verify) and
  # PreToolUse hooks already validated agent edits — but distinguish the two so
  # a real crash is not misreported as a benign timeout.
  echo "" >&2
  case "$BATCH_RC" in
    124|137|143)
      echo "cos pre-commit: WARNING — scan exceeded ${COS_PRECOMMIT_TIMEOUT}s and was reaped (orphans killed; rc=${BATCH_RC})." >&2 ;;
    *)
      echo "cos pre-commit: WARNING — scan helper crashed (rc=${BATCH_RC}); commit allowed but hooks did NOT fully run." >&2 ;;
  esac
  echo "  Commit allowed; re-run for a full scan if needed." >&2
  exit 0
fi
