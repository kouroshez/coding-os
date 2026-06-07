#!/usr/bin/env bash
# PostToolUse Write|Edit|MultiEdit — code → doc staleness scanner.
#
# WHY
#   Closes the docs-first loop in the OTHER direction. Rule 0 (docs-first
#   anchor) makes new code trace TO a doc; this hook makes existing docs
#   surface when the code drifts AWAY from them. Three drift signals,
#   ranked by confidence:
#     1. Public symbol REMOVED/RENAMED + doc still mentions it.
#     2. Public symbol KEPT but signature changed (param count diff).
#        ← addresses the "agent invented a `birthdate` field" case.
#     3. Doc mtime older than code AND doc mentions a current symbol
#        (soft signal, only emitted when no stronger one fires).
#
# COLLABORATES WITH
#   - thinking_os FTS5 index (document_chunks_fts) — used to find docs
#     that lexically reference touched symbols. Far more accurate than
#     path-mirror heuristics.
#   - graph_os backend (when up) — adds "this symbol is referenced from
#     N other locations" hint via `cos_graph_references`. Capped at
#     200 ms; silent if backend down.
#
# CONTRACT
#   - WARN class: exit 0 always; advisory stderr only.
#   - Skips .md/.mdx (no recursion), .yaml/.json/.toml/.lock.
#   - Triggers only on code: .py/.ts/.tsx/.js/.jsx/.go.
#   - Hot path = local FTS query (~10 ms). Graph call only when WARN
#     already decided.
#
# FORMAT (stderr)
#     ⚠ doc-sync — code edit may have outdated docs:
#         <doc_path> — <reason>
#         ...
#       ℹ graph context: `<symbol>` referenced from N other location(s)
#
#       Docs are source of truth (AGENTS.md A0 + W8). Either:
#         1. update the doc to match the new code, OR
#         2. revert the code to match the doc spec.

set -euo pipefail

# Resolve to source dir even when invoked via .{claude,codex,cursor}/hooks
# symlink so we can find _helpers/. Same idiom as agent-presence.sh.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
COS_HOOK_SRC_DIR="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then
  cos_log_hook() { :; }
fi

INPUT=""
if [[ ! -t 0 ]]; then
  INPUT=$(cat 2>/dev/null || true)
fi

TOOL=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
FILE_PATH=$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

case "$TOOL" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac
[[ -z "$FILE_PATH" ]] && exit 0
[[ ! -f "$FILE_PATH" ]] && exit 0

# Skip docs editing docs (no recursion) and config files.
case "$FILE_PATH" in
  *.md|*.mdx|*.yaml|*.yml|*.json|*.toml|*.lock) exit 0 ;;
esac

HELPER="$COS_HOOK_SRC_DIR/_helpers/doc_sync_check.py"
[[ ! -f "$HELPER" ]] && { cos_log_hook enforce-doc-sync skip "reason=helper_missing"; exit 0; }

# Try to recover the pre-edit content for diff signals. Edit carries
# old_string for one chunk; MultiEdit carries an `edits` array (we use
# the first old_string — enough to feed the symbol extractor).
OLD_TEXT=$(printf '%s' "$INPUT" | jq -r '
  .tool_input.old_string //
  (.tool_input.edits[0].old_string // empty)
' 2>/dev/null || true)

HELPER_OUT=$(
  if [[ -n "$OLD_TEXT" ]]; then
    python3 "$HELPER" "$FILE_PATH" "$OLD_TEXT" 2>/dev/null
  else
    python3 "$HELPER" "$FILE_PATH" 2>/dev/null
  fi
) || true

# ── Verification matrix reminder (D4: absorbed from verify-changed-file.sh) ──
# Prints which test suite to run. Always emits, regardless of FTS findings.
_VERIFY_HINT=""
case "$FILE_PATH" in
  *core/thinking_os/*.py)
    _VERIFY_HINT="uv run --extra rag pytest src/core/thinking_os/tests/ -q"
    ;;
  *core/graph_os/*.py)
    _VERIFY_HINT="uv run --extra graph_os pytest src/core/graph_os/tests/ -q"
    ;;
  *core/board_os/*.py)
    _VERIFY_HINT="uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q"
    ;;
  *core/hooks/*.sh|*core/scripts/*.sh)
    _VERIFY_HINT="make verify-hooks"
    ;;
  *adapters/*.py|*adapters/*.sh)
    _VERIFY_HINT="uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q"
    ;;
  *cli/*.py)
    _VERIFY_HINT="uv run pytest tests/test_cli.py -q"
    ;;
esac

if [[ -z "$HELPER_OUT" ]]; then
  # No FTS staleness found — emit companion-doc hints as a soft reminder
  # (D2: absorbed from doc-sync-reminder.sh).
  COMPANION_DOCS=()
  case "$FILE_PATH" in
    *core/hooks/*.sh)
      COMPANION_DOCS=(
        "docs/engineering/hooks-reference.md"
        "src/core/hooks/registry.yaml (SSOT — register new hooks here)"
      )
      ;;
    *core/thinking_os/server.py|*core/thinking_os/tools/*.py)
      COMPANION_DOCS=(
        "docs/architecture.md (§ MCP Tools)"
        "docs/engineering/mcp-error-envelope.md"
      )
      ;;
    *core/thinking_os/database.py)
      COMPANION_DOCS=("docs/architecture.md (§ Database Schema)")
      ;;
    *cli/*.py)
      COMPANION_DOCS=(
        "README.md (§ Command Index)"
        "docs/features.md (§ Command Catalog)"
      )
      ;;
    *adapters/*/adapter.yaml|*adapters/*/install.sh)
      COMPANION_DOCS=("docs/architecture.md (§ Adapters / Portability)")
      ;;
  esac
  if [[ ${#COMPANION_DOCS[@]} -gt 0 ]]; then
    echo "" >&2
    echo "  📘 doc-sync hint — keep these docs in sync:" >&2
    for d in "${COMPANION_DOCS[@]}"; do
      echo "     → $d" >&2
    done
  fi
  if [[ -n "$_VERIFY_HINT" ]]; then
    echo "" >&2
    echo "  ✓ verify: $_VERIFY_HINT" >&2
  fi
  cos_log_hook enforce-doc-sync ok "file=${FILE_PATH##*/}"
  exit 0
fi

# Surface FTS staleness findings to the agent via stderr.
echo "" >&2
echo "⚠ doc-sync — code edit may have outdated docs:" >&2
STALE_COUNT=0
INFO_LINES=()
while IFS=$'\t' read -r tag doc reason; do
  case "$tag" in
    STALE)
      echo "    ${doc} — ${reason}" >&2
      STALE_COUNT=$((STALE_COUNT + 1))
      ;;
    INFO)
      INFO_LINES+=("$reason")
      ;;
  esac
done < <(printf '%s\n' "$HELPER_OUT")  # process-sub, not <<<: no bash heredoc deadlock on large helper output
if [[ ${#INFO_LINES[@]} -gt 0 ]]; then
  echo "" >&2
  for line in "${INFO_LINES[@]}"; do
    echo "  ℹ graph context: ${line}" >&2
  done
fi
echo "" >&2
echo "  Docs are source of truth (AGENTS.md). Either:" >&2
echo "    1. update the doc to match the new code, OR" >&2
echo "    2. revert the code to match the doc spec." >&2
if [[ -n "$_VERIFY_HINT" ]]; then
  echo "" >&2
  echo "  ✓ verify: $_VERIFY_HINT" >&2
fi
echo "" >&2

# D5-F5 (TASK-128): opt-in strict mode turns the WARN into a BLOCK so a CI or
# careful session can gate on stale docs. Default stays warn (exit 0).
if [[ "${COS_ENFORCE_DOC_SYNC:-warn}" == "strict" && "$STALE_COUNT" -gt 0 ]]; then
  echo "  COS_ENFORCE_DOC_SYNC=strict → blocking until docs and code are reconciled." >&2
  cos_log_hook enforce-doc-sync block "file=${FILE_PATH##*/} stale=${STALE_COUNT}"
  exit 2
fi

cos_log_hook enforce-doc-sync warn "file=${FILE_PATH##*/} stale=${STALE_COUNT}"
exit 0
