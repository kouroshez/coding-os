#!/usr/bin/env bash
# snapshot-transcript.sh (Stop) — copy the live session transcript into the
# repo so a workflow session is auditable in-tree, not only in the agent
# runtime's global store (~/.claude/projects/...). Fires on Stop (the
# canonical session-end signal — Claude Code has no SessionEnd event).
# Fail-open telemetry: never blocks, only copies when the source moved.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook snapshot-transcript enter || true

# Opt-in only: snapshotting the full chat transcript is OFF by default — the
# conversation is NOT saved into the repo unless explicitly enabled (privacy).
# Set COS_SNAPSHOT_TRANSCRIPT=1 to re-enable (e.g. for cognition trace-replay).
if [[ "${COS_SNAPSHOT_TRANSCRIPT:-0}" != "1" ]]; then
  cos_log_hook snapshot-transcript skip || true
  exit 0
fi

INPUT="$(cos_read_stdin_bounded 2)"

# transcript_path is provided by the agent runtime in the Stop payload.
# Absent (or file gone) → nothing to snapshot; fail-open.
TRANSCRIPT=$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || echo "")
if [[ -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi

# Name the snapshot by this panel's session-id so it lines up with the
# tasks.agent_session attribution (that IS the task↔session link).
SID=""
if [[ -n "${COS_SESSION_FILE:-}" && -f "$COS_SESSION_FILE" ]]; then
  SID=$(tr -d '\n\r' < "$COS_SESSION_FILE" 2>/dev/null || true)
fi
[[ -z "$SID" ]] && SID="${COS_PANEL_ID:-unknown}"
# Strip anything path-hostile from the id before using it as a filename.
SID=$(printf '%s' "$SID" | tr -c 'A-Za-z0-9_.-' '-')
[[ -z "$SID" ]] && exit 0

DEST_DIR="${COS_AGENT_DIR:-.coding-os}/sessions/transcripts"
mkdir -p "$DEST_DIR" 2>/dev/null || true
DEST="${DEST_DIR}/${SID}.jsonl"

# Stop fires every turn, so only copy when the transcript actually grew —
# avoids re-copying a multi-MB jsonl on every turn of a long session.
if [[ ! -f "$DEST" || "$TRANSCRIPT" -nt "$DEST" ]]; then
  TMP="${DEST}.tmp.$$"
  if cp -f "$TRANSCRIPT" "$TMP" 2>/dev/null; then
    mv -f "$TMP" "$DEST" 2>/dev/null || rm -f "$TMP" 2>/dev/null || true
  fi
fi

cos_log_hook snapshot-transcript ok || true
exit 0
