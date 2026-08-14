#!/usr/bin/env bash
# test-governor.sh (PreToolUse Bash) — multi-agent test-run governance.
#
# Gates pytest invocations three ways (in order):
#   1. Full sweep (bare pytest / pytest tests/ / >=3 test roots) → BLOCK unless
#      COS_FULL_SWEEP_OK=1 with COS_OVERRIDE_REASON >=15 chars (Rule 20, audited).
#   2. Dedup — the suite is already green on THIS tree within TTL (commit-keyed
#      ledger) → BLOCK with reuse message; COS_TEST_FORCE=1 re-runs.
#   3. Concurrency — $COS_STATE_DIR/.test-run.lock held by a live run → BLOCK
#      naming the holder. The lock is a per-repo JSON file (TTL-bounded); the
#      PostToolUse leg record-verify-auto.sh deletes it when pytest exits, and
#      the owner-agent pid in it lets a crashed run free early. No host-global
#      pgrep (it phantom-holds across repos + false-clears on wrapper/xdist
#      argv). flock(1) is absent on macOS and a PreToolUse hook exits before the
#      tool runs, so it cannot hold an advisory lock anyway.
# Sweep gate is fail-closed; everything else fails open (exit 0 on internal error).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this governor gates pytest invocations AND make-target verify
# suites (verify-hooks / docs-lint / ui-test …) for dedup. If the raw payload
# mentions neither "pytest" nor "make " there is nothing to gate — bail before
# any jq spawn (fires on EVERY Bash command).
case "$INPUT" in
  *pytest*|*"make "*) ;;
  *) exit 0 ;;
esac

COMMAND=$(printf '%s' "$INPUT" | cos_json_field tool_input.command)
[[ -n "$COMMAND" ]] || exit 0

# Match `make ` only at a command-word boundary (start, or after a shell
# separator) — a plain substring would also fire on cmake/gmake/remake, which
# contain "make " and would then pay the match-command spawn for nothing.
_MAKE_WORD_RE='(^|[[:space:]&|;(])make[[:space:]]'
if [[ "$COMMAND" != *pytest* ]] && [[ ! "$COMMAND" =~ $_MAKE_WORD_RE ]]; then
  exit 0
fi
case "$COMMAND" in
  *--collect-only*|*" --co"*) exit 0 ;;
esac

PROJECT_ROOT="${COS_PROJECT_ROOT:-$(pwd)}"
if command -v uv >/dev/null 2>&1; then
  PYRUN=(uv run --quiet python)
else
  PYRUN=(python3)
fi
MATCH=$(cd "$PROJECT_ROOT" && "${PYRUN[@]}" -m core.board_os.verify_suites_cli match-command --command "$COMMAND" 2>/dev/null) || MATCH='{}'

FULL_SWEEP=$(printf '%s' "$MATCH" | cos_json_field full_sweep)
FULL_SWEEP="${FULL_SWEEP:-false}"
SUITE=$(printf '%s' "$MATCH" | cos_json_field suite)
FRESH=$(printf '%s' "$MATCH" | cos_json_field fresh)
FRESH="${FRESH:-false}"
IS_PYTEST=$(printf '%s' "$MATCH" | cos_json_field pytest_invocation)
IS_PYTEST="${IS_PYTEST:-false}"

# Not a pytest run AND not a recognised suite — the command merely MENTIONS the
# trigger (echo/jq/heredoc payload), or MATCH was unavailable ({}). Bail fail-open.
# A make-target verify suite (pytest_invocation=false but SUITE set) stays in for
# dedup below.
if [[ "$IS_PYTEST" != "true" && -z "$SUITE" ]]; then
  exit 0
fi

# Inline overrides: an agent writes `COS_TEST_FORCE=1 pytest …` as ONE Bash
# command — the assignment lives in the command STRING, never in this hook's
# environment. Honor both forms.
INLINE_FORCE=false
[[ "$COMMAND" == *"COS_TEST_FORCE=1"* ]] && INLINE_FORCE=true
INLINE_SWEEP_OK=false
[[ "$COMMAND" == *"COS_FULL_SWEEP_OK=1"* ]] && INLINE_SWEEP_OK=true
INLINE_REASON=$(echo "$COMMAND" | { grep -oE "COS_OVERRIDE_REASON=('[^']*'|\"[^\"]*\")" || true; } | head -1 | sed -E "s/^COS_OVERRIDE_REASON=//; s/^['\"]//; s/['\"]$//")

# ── 1. Full-sweep gate (fail-closed, audited override) ──────────────
if [[ "$FULL_SWEEP" == "true" ]]; then
  REASON="${COS_OVERRIDE_REASON:-$INLINE_REASON}"
  SWEEP_OK="${COS_FULL_SWEEP_OK:-}"
  $INLINE_SWEEP_OK && SWEEP_OK=1
  if [[ "$SWEEP_OK" == "1" && "${#REASON}" -ge 15 ]]; then
    cos_log_hook test-governor override "full-sweep reason=$REASON" 2>/dev/null || true
  else
    cos_log_hook test-governor block "full-sweep" 2>/dev/null || true
    {
      echo "BLOCKED: full pytest sweep mid-task (Rule 20 — ~4,100 tests, minutes of CPU, melts concurrent sessions)."
      echo "  Run the matrix suite for what you changed instead (AGENTS.md § Verification Matrix)."
      echo "  Pre-merge / cross-cutting / user asked? Override (audited):"
      echo "    COS_FULL_SWEEP_OK=1 COS_OVERRIDE_REASON='...>=15 chars' <your command>"
      echo "  Tip: prefix with 'nice -n 19' to keep the laptop responsive."
    } >&2
    exit 2
  fi
fi

# ── 2. Dedup — suite already green on this exact tree ────────────────
if [[ -n "$SUITE" && "$FRESH" == "true" && "${COS_TEST_FORCE:-}" != "1" ]] && ! $INLINE_FORCE; then
  BY=$(printf '%s' "$MATCH" | cos_json_field recorded_by)
  BY="${BY:-unknown}"
  TAIL=$(printf '%s' "$MATCH" | cos_json_field session_tail)
  AGE=$(printf '%s' "$MATCH" | cos_json_field age_min)
  AGE="${AGE:-0}"
  cos_log_hook test-governor block "dedup suite=$SUITE by=$BY" 2>/dev/null || true
  {
    echo "BLOCKED: $SUITE is already green on this exact tree — passed ${AGE}min ago by ${BY}${TAIL:+ (ses=$TAIL)}."
    echo "  Reuse that result; the ledger invalidates it automatically when the tree changes."
    echo "  Re-run anyway: COS_TEST_FORCE=1 <your command>"
  } >&2
  exit 2
fi

# Make-target verify suites (verify-hooks / docs-lint / ui-test) get dedup above
# but NOT the pytest run-lock — the lock governs heavy pytest concurrency and
# re-architecting it is out of scope. A non-pytest suite that survived
# dedup just runs.
if [[ "$IS_PYTEST" != "true" ]]; then
  exit 0
fi

# ── 3. Concurrency lock (TTL + liveness; never queue-wait) ───────────
LOCK_FILE="${COS_STATE_DIR}/.test-run.lock"
LOCK_TTL=1800
NOW=$(date +%s)
if [[ -f "$LOCK_FILE" ]]; then
  STARTED=$(cos_json_field started_ts < "$LOCK_FILE")
  STARTED="${STARTED:-0}"
  H_TAIL=$(cos_json_field session_tail < "$LOCK_FILE")
  H_AGENT_PID=$(cos_json_field agent_pid < "$LOCK_FILE")
  H_AGENT_PID="${H_AGENT_PID:-0}"
  OUR_TAIL="${COS_PANEL_ID:-}"
  OUR_TAIL="${OUR_TAIL: -8}"
  AGE=$(( NOW - STARTED ))
  HELD=false
  # Held = the lock is present and within TTL. The PostToolUse leg
  # (record-verify-auto.sh) deletes this file the instant THIS repo's pytest
  # exits, so a surviving unexpired lock means a sibling run is genuinely in
  # flight. No host-global `pgrep -f pytest`: it phantom-holds across repos
  # (repo A blocked by repo B's unrelated pytest) and false-clears on
  # `uv run`/pytest-xdist worker argv (a sibling then double-runs).
  if [[ "$AGE" -lt "$LOCK_TTL" ]]; then
    HELD=true
    # Owner agent gone while the lock is still present ⇒ the run crashed before
    # its release fired — free it now instead of waiting out the TTL (the lock
    # is per-repo on one machine, so its pid is always same-host).
    if [[ "$H_AGENT_PID" =~ ^[0-9]+$ && "$H_AGENT_PID" -gt 0 ]] && ! kill -0 "$H_AGENT_PID" 2>/dev/null; then
      HELD=false
    fi
  fi
  # A lock carrying OUR session tail is a finished/failed run whose PostToolUse
  # cleanup never fired — reclaim it rather than self-block (a panel runs Bash
  # serially, so an OUR-tail lock is never a concurrent self-run).
  if [[ -n "$OUR_TAIL" && "$H_TAIL" == "$OUR_TAIL" ]]; then
    HELD=false
  fi
  if $HELD; then
    H_AGENT=$(cos_json_field agent < "$LOCK_FILE")
    H_AGENT="${H_AGENT:-unknown}"
    H_SUITE=$(cos_json_field suite < "$LOCK_FILE")
    H_SUITE="${H_SUITE:-a test run}"
    cos_log_hook test-governor block "lock-held by=$H_AGENT" 2>/dev/null || true
    {
      echo "BLOCKED: $H_AGENT${H_TAIL:+ (ses=$H_TAIL)} is running $H_SUITE on this machine (started ${AGE}s ago)."
      echo "  Concurrent heavy suites swap this laptop. Retry after it finishes —"
      echo "  the lock clears automatically (or expires after ${LOCK_TTL}s)."
    } >&2
    exit 2
  fi
fi

# Acquire: record this run so sibling sessions queue behind it.
SESSION_TAIL="${COS_PANEL_ID:-}"
SESSION_TAIL="${SESSION_TAIL: -8}"
printf '{"suite": "%s", "agent": "%s", "session_tail": "%s", "agent_pid": %s, "started_ts": %s}\n' \
  "${SUITE:-adhoc-pytest}" "${COS_AGENT:-unknown}" "$SESSION_TAIL" "${PPID:-0}" "$NOW" \
  > "$LOCK_FILE" 2>/dev/null || true

cos_log_hook test-governor allow "suite=${SUITE:-adhoc}" 2>/dev/null || true
exit 0
