#!/usr/bin/env bash
# check-mcp-extras.sh — SessionStart
#
# PURPOSE
#   At session start, verify the global `cos` binary has the required Python
#   extras (graph_os, board_os, rag/sentence_transformers). If any are missing,
#   the MCP server crashes silently on launch — every cos_* tool call fails
#   with no clear root cause visible to the agent.
#
#   Emits a loud, actionable warning with the exact fix command before the
#   agent starts using cos_* tools.
#
# FAST — uses direct Python import check (<200ms). Does NOT start the server.
# NON-BLOCKING — always exits 0.
#
# DESIGN
#   1. Locate global cos binary via PATH (the one .mcp.json launches).
#   2. Find its Python interpreter (sibling python3 in same bin/).
#   3. Try importing required modules — failures = missing extras.
#   4. If missing: emit warning + exact fix command.
#   5. Log result regardless.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook check-mcp-extras entry 2>/dev/null || true

# Locate global cos (the one .mcp.json uses — resolved via PATH)
GLOBAL_COS="$(command -v cos 2>/dev/null || true)"
if [[ -z "$GLOBAL_COS" ]]; then
    cos_log_hook check-mcp-extras skip-cos-not-found 2>/dev/null || true
    exit 0
fi

COS_BIN_DIR="$(dirname "$GLOBAL_COS")"
COS_PYTHON="${COS_BIN_DIR}/python3"

# Fallback: if no sibling python3 (e.g. cos installed via brew wrapper script),
# try PATH python3. If nothing found, skip check — can't validate safely.
if [[ ! -x "$COS_PYTHON" ]]; then
    COS_PYTHON="$(command -v python3 2>/dev/null || true)"
    if [[ -z "$COS_PYTHON" || ! -x "$COS_PYTHON" ]]; then
        cos_log_hook check-mcp-extras skip-python-not-found 2>/dev/null || true
        exit 0
    fi
fi

# Quick import check — no server startup needed
MISSING="$("$COS_PYTHON" -c '
missing = []
checks = {
    "graph_os":             "graph_os",
    "board_os":             "board_os",
    "sentence_transformers": "rag",
}
for mod, label in checks.items():
    try:
        __import__(mod)
    except ImportError:
        missing.append(label)
print(",".join(missing))
' 2>/dev/null || echo "check-failed")"

if [[ -z "$MISSING" ]]; then
    cos_log_hook check-mcp-extras ok 2>/dev/null || true
    exit 0
fi

if [[ "$MISSING" == "check-failed" ]]; then
    cos_log_hook check-mcp-extras python-check-error 2>/dev/null || true
    exit 0
fi

# Find the source path for the fix command
COS_SRC="$("$COS_PYTHON" -c '
import pathlib, importlib.util
spec = importlib.util.find_spec("cli")
if spec and spec.origin:
    print(pathlib.Path(spec.origin).parent.parent)
' 2>/dev/null || true)"
[[ -z "$COS_SRC" ]] && COS_SRC="<path-to-coding-os>"

cos_log_hook check-mcp-extras "FAIL missing=${MISSING}" 2>/dev/null || true

cat >&2 <<MSG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  MCP will be DOWN — global cos missing: ${MISSING}

   Every cos_* tool call will fail silently until fixed.

   Fix (run in terminal, then restart Claude Code):
     uv tool install --editable ${COS_SRC} --with "coding-os[rag,graph_os]"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MSG

exit 0
