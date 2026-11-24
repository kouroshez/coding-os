#!/usr/bin/env bash
# native-review-subagent.sh — SubagentStart hands a cos-reviewer / cos-security-auditor
# subagent its review package; SubagentStop records its verdict in the review ledger,
# so the verdict never passes through the main agent.
# Contract: docs/engineering/agent-supervision.md § A review on the session's own
# runtime runs as its native subagent.
# Fail-open: a review that cannot be recorded ends as the gate's stale warning.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null \
  || source "$(dirname "$0")/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi
command -v jq >/dev/null 2>&1 || exit 0

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
EVENT=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)
case "$EVENT" in
  SubagentStart) MODE=start ;;
  SubagentStop) MODE=stop ;;
  *) exit 0 ;;
esac
# The parent session's panel holds the request the move to testing wrote.
cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true

_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HELPER="$(cd -P "$(dirname "$_src")" && pwd)/../../../core/hooks/_helpers/native_review.py"
[ -f "$HELPER" ] || exit 0

COS_PY="$(cos_resolve_python 2>/dev/null || echo python3)"
[ -x "$COS_PY" ] || COS_PY=python3

printf '%s' "$INPUT" | "$COS_PY" "$HELPER" "$MODE" 2>/dev/null || true
AGENT_TYPE=$(printf '%s' "$INPUT" | jq -r '.agent_type // empty' 2>/dev/null || true)
cos_log_hook native-review-subagent ok "event=${EVENT} agent=${AGENT_TYPE}" || true
exit 0
