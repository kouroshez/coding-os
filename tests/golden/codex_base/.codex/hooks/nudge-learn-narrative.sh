#!/usr/bin/env bash
# nudge-learn-narrative.sh (Phase O) — Stop hook (the C path).
#
# When a session shows REAL learning signal (a file reworked >=3x, or a
# backtrack), nudge the agent ONCE to record a structured lesson via
# cos_learn_narrative (→ docs/insights/ + memory) — the channel for the deep
# engineering knowledge that auto-mining (friction/commit subjects) can't capture.
# Signal-gated (silent on trivial sessions), debounced once per session,
# warn-only, fail-open (Stop never blocks). Contract: docs/engineering/learning-extraction.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook nudge-learn-narrative enter || true

SESSION="$(cos_current_session 2>/dev/null || echo "")"
[[ -z "$SESSION" || "$SESSION" == "?" ]] && exit 0

# Debounce once per session (per-panel marker, session-tail keyed).
MARKER="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os}}/.narrative-nudged-${SESSION##*-}"
[[ -f "$MARKER" ]] && exit 0

DB="${COS_DB_PATH:-${COS_STATE_DIR:-.coding-os}/coding-os.db}"
[[ -f "$DB" ]] || exit 0

REASON="$(python3 "$(dirname "$0")/_helpers/narrative_signal.py" "$DB" "$SESSION" 2>/dev/null || true)"
if [[ -n "$REASON" ]]; then
  : > "$MARKER" 2>/dev/null || true
  printf 'warning: 🧠 [learn] This session hit real friction (%s). If you solved something non-obvious, record ONE lesson so a future session reuses it:\n' "$REASON" >&2
  printf '  cos_learn_narrative(task_id, what_failed, what_worked, key_insight) — files to docs/insights/ + memory. Be specific (situation -> why -> rule).\n' >&2
  cos_log_hook nudge-learn-narrative warn || true
  exit 0
fi
cos_log_hook nudge-learn-narrative ok || true
exit 0
