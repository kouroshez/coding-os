#!/usr/bin/env bash
# Coding OS - Hook activity log, timing and operator-visible output.
# Sourced by cos-env.sh from its own resolved directory; never run
# directly and never sourced by a hook.

# ---------------------------------------------------------------------------
# Hook activity logging — makes hook execution visible to the user.
# Format: [ISO-8601] [hook_name] [action] agent=X session=Y task=Z detail...
# Keeps human-readable shape so `grep`/`awk`/`tail -f` all still work; new
# identity fields are appended in front of the free-form detail so downstream
# filters (cos hooks-log --agent X) never need a JSON parser.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# cos_record_activity <category> <detail> — append a per-turn activity entry
# ---------------------------------------------------------------------------
# Logs operator-visible side effects (memory capture, graph reindex, task
# sync, skill invoke, worklog) for the per-turn pulse. session-context.sh
# reads this file on the next UserPromptSubmit, summarizes, then truncates.
# Claude Code does NOT render PostToolUse stdout, so this aggregation is
# the only reliable way to surface PostToolUse activity in the chat UI.
# Fail-open: never aborts the parent hook on logging failure.
# ---------------------------------------------------------------------------
cos_record_activity() {
  local category="${1:-}"
  local detail="${2:-}"
  [[ -z "$category" ]] && return 0
  [[ -z "${COS_AGENT_DIR:-}" ]] && return 0
  local log ts size
  log="$COS_AGENT_DIR/.turn-activity.log"
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo "")"
  {
    mkdir -p "$COS_AGENT_DIR" 2>/dev/null
    printf '%s\t%s\t%s\n' "$category" "$detail" "$ts" >> "$log"
  } 2>/dev/null || true
  # Opportunistic truncation — keep last 500 lines once the file exceeds 50 KB.
  size=$(stat -f%z "$log" 2>/dev/null || stat -c%s "$log" 2>/dev/null || echo 0)
  if [[ "$size" -gt 50000 ]]; then
    {
      tail -n 500 "$log" > "${log}.tmp" && mv "${log}.tmp" "$log"
    } 2>/dev/null || true
  fi
  return 0
}

# Elapsed wall-time (ms) since this hook sourced cos-env.sh. Pure integer-µs
# math on the two $EPOCHREALTIME strings (sec.usec) — no float, no locale,
# no awk. Echoes a non-negative integer; empty when T0 / now is unavailable
# (older bash without $EPOCHREALTIME) so the dt= field is simply omitted.
cos_hook_elapsed_ms() {
  local t0="${COS_HOOK_T0:-}" now="${EPOCHREALTIME:-}"
  [[ -z "$t0" || -z "$now" ]] && return 0
  # Split sec.usec; pad/truncate the fractional part to exactly 6 digits.
  local t0_s="${t0%%.*}" t0_f="${t0#*.}" now_s="${now%%.*}" now_f="${now#*.}"
  [[ "$t0_f" == "$t0" ]] && t0_f="0"
  [[ "$now_f" == "$now" ]] && now_f="0"
  t0_f="${t0_f}000000"; t0_f="${t0_f:0:6}"
  now_f="${now_f}000000"; now_f="${now_f:0:6}"
  # Strip leading zeros so bash does not read them as octal.
  local t0_us=$((10#$t0_s * 1000000 + 10#$t0_f))
  local now_us=$((10#$now_s * 1000000 + 10#$now_f))
  local dms=$(((now_us - t0_us) / 1000))
  ((dms < 0)) && dms=0
  printf '%s' "$dms"
}

cos_log_hook() {
  local hook_name="${1:-unknown}"
  local action="${2:-fire}"
  shift 2 2>/dev/null || true
  local detail="$*"

  local ts agent session task model_bit dt_bit
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  agent="${COS_AGENT:-unknown}"
  session="$(cos_current_session)"
  task="$(cos_current_task)"
  model_bit=""
  if [[ -n "${COS_HOOK_RUNTIME_MODEL:-}" ]]; then
    model_bit=" model=${COS_HOOK_RUNTIME_MODEL}"
  fi
  dt_bit=""
  local _dms
  _dms="$(cos_hook_elapsed_ms 2>/dev/null || true)"
  if [[ -n "$_dms" ]]; then
    dt_bit=" dt=${_dms}ms"
  fi

  # Fail-open: never let a logging error abort the hook.
  {
    mkdir -p "$(dirname "$COS_HOOK_LOG")" 2>/dev/null
    local log_line
    if [[ -n "$detail" ]]; then
      log_line="[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit}${dt_bit} ${detail}"
    else
      log_line="[${ts}] [${hook_name}] [${action}] agent=${agent} session=${session} task=${task}${model_bit}${dt_bit}"
    fi
    echo "$log_line" >> "$COS_HOOK_LOG"

    # Mirror 'block' lines into the block-only durable log so the high-volume
    # main log's cap can't evict them before learn_extract mines them.
    if [[ "$action" == "block" && -n "${COS_HOOK_BLOCK_LOG:-}" ]]; then
      echo "$log_line" >> "$COS_HOOK_BLOCK_LOG"
      local blk_lines
      blk_lines=$(wc -l < "$COS_HOOK_BLOCK_LOG" 2>/dev/null || echo 0)
      if [[ "$blk_lines" -gt $((COS_HOOK_LOG_MAX_LINES * 2)) ]]; then
        tail -n "$COS_HOOK_LOG_MAX_LINES" "$COS_HOOK_BLOCK_LOG" > "${COS_HOOK_BLOCK_LOG}.tmp" \
          && mv "${COS_HOOK_BLOCK_LOG}.tmp" "$COS_HOOK_BLOCK_LOG"
      fi
    fi

    # F8: make a BLOCK durable in the SQLite log_events store the
    # logging_os sink owns so cos_log_query / error_sweep surface it — not just
    # the text logs above. Reuse the shared shell→DB writer (DB-only here).
    if [[ "$action" == "block" ]] && command -v python3 >/dev/null 2>&1; then
      local _db_helper
      _db_helper="$(_cos_helpers_dir)/cos_say_json.py"
      if [[ -f "$_db_helper" ]]; then
        python3 "$_db_helper" "$ts" "ERROR" "hook.${hook_name}" "${detail:-blocked}" \
          "action=block session=${session} task=${task}" >/dev/null 2>&1 || true
      fi
    fi

    # Opportunistic truncation — keep only last N lines when file grows past 2x cap.
    if [[ -f "$COS_HOOK_LOG" ]]; then
      local lines
      lines=$(wc -l < "$COS_HOOK_LOG" 2>/dev/null || echo 0)
      if [[ "$lines" -gt $((COS_HOOK_LOG_MAX_LINES * 2)) ]]; then
        tail -n "$COS_HOOK_LOG_MAX_LINES" "$COS_HOOK_LOG" > "${COS_HOOK_LOG}.tmp" \
          && mv "${COS_HOOK_LOG}.tmp" "$COS_HOOK_LOG"
      fi
    fi
  } 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# cos_say <level> <scope> <msg> [k=v ...] — shell parity for logging_os.
#
# Schema mirrors src/core/logging_os/ (docs/engineering/logging_os.md).
# Three renders auto-detected from env + isatty(stderr); fans out to stderr,
# $COS_LOG_FILE (always short text), and ${COS_LOG_FILE}.jsonl (always json).
# Fail-open: never aborts the parent hook on logging failure.
# ---------------------------------------------------------------------------
cos_say() {
  local level scope msg
  level="${1:-info}"
  scope="${2:-shell.unknown}"
  msg="${3:-}"
  shift 3 2>/dev/null || true
  level="$(echo "$level" | tr '[:lower:]' '[:upper:]')"
  local level_value=20
  case "$level" in
    DEBUG) level_value=10 ;;
    INFO)  level_value=20 ;;
    OK)    level_value=21 ;;
    WARN)  level_value=30 ;;
    ERROR) level_value=40 ;;
    FATAL) level_value=50 ;;
    *) level="INFO"; level_value=20 ;;
  esac

  local floor_name floor_value=20
  floor_name="$(echo "${COS_LOG_LEVEL:-info}" | tr '[:lower:]' '[:upper:]')"
  case "$floor_name" in
    DEBUG) floor_value=10 ;;
    INFO)  floor_value=20 ;;
    OK)    floor_value=21 ;;
    WARN)  floor_value=30 ;;
    ERROR) floor_value=40 ;;
    FATAL) floor_value=50 ;;
  esac
  # Per-sink flooring: the console floor (COS_LOG_LEVEL) gates the
  # human sinks (stderr/text/jsonl); the durable floor (COS_LOG_DB_MIN_LEVEL,
  # re-applied inside cos_say_json.py) gates the log_events row independently.
  # Short-circuit only when the event clears NEITHER floor — flooring at the
  # console level alone here dropped a WARN before the durable store saw it.
  local db_floor_name db_floor_value=30
  db_floor_name="$(echo "${COS_LOG_DB_MIN_LEVEL:-WARN}" | tr '[:lower:]' '[:upper:]')"
  case "$db_floor_name" in
    DEBUG) db_floor_value=10 ;;
    INFO)  db_floor_value=20 ;;
    OK)    db_floor_value=21 ;;
    WARN)  db_floor_value=30 ;;
    ERROR) db_floor_value=40 ;;
    FATAL) db_floor_value=50 ;;
  esac
  local min_floor="$floor_value"
  [[ "$db_floor_value" -lt "$min_floor" ]] && min_floor="$db_floor_value"
  if [[ "$level_value" -lt "$min_floor" ]]; then
    return 0
  fi
  local below_console=0
  [[ "$level_value" -lt "$floor_value" ]] && below_console=1

  local kv=""
  if [[ $# -gt 0 ]]; then
    kv="$*"
  fi

  local mode
  if [[ "${COS_LOG_JSON:-}" == "1" ]]; then
    mode="json"
  elif [[ "${COS_LOG_FORCE_PRETTY:-}" == "1" ]]; then
    mode="pretty"
  elif [[ -n "${NO_COLOR:-}" ]]; then
    mode="short"
  elif [[ -t 2 ]]; then
    mode="pretty"
  else
    mode="short"
  fi

  local ts_iso ts_short
  ts_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "")"
  ts_short="$(date -u +%H:%M:%S 2>/dev/null || echo "")"

  local emoji="" color="" reset=""
  case "$level" in
    DEBUG) emoji="🔍 "; color=$'\e[90m' ;;
    INFO)  emoji="ℹ️  "; color=$'\e[36m' ;;
    OK)    emoji="✅"; color=$'\e[32m' ;;
    WARN)  emoji="⚠️  "; color=$'\e[33m' ;;
    ERROR) emoji="❌"; color=$'\e[31m' ;;
    FATAL) emoji="💀"; color=$'\e[1;31m' ;;
  esac
  reset=$'\e[0m'

  local level_padded
  level_padded="$(printf '%-5s' "$level")"
  local short_line="${ts_short} ${level_padded} ${scope} ${msg}"
  [[ -n "$kv" ]] && short_line="${short_line} ${kv}"

  local helper
  helper="$(_cos_helpers_dir)/cos_say_json.py"
  local json_line=""
  if command -v python3 >/dev/null 2>&1 && [[ -f "$helper" ]]; then
    json_line="$(python3 "$helper" "$ts_iso" "$level" "$scope" "$msg" "$kv" 2>/dev/null || true)"
  fi

  local stderr_line
  case "$mode" in
    pretty)
      local pad
      pad="$(printf '%-20s' "$scope")"
      stderr_line="${emoji}  ${ts_short}  ${color}${level_padded}${reset}  ${pad}  ${msg}"
      [[ -n "$kv" ]] && stderr_line="${stderr_line}  ${kv}"
      ;;
    json)
      stderr_line="${json_line:-$short_line}"
      ;;
    *)
      stderr_line="$short_line"
      ;;
  esac

  # Human sinks respect the console floor; the durable log_events row was already
  # written above by cos_say_json.py (gated by COS_LOG_DB_MIN_LEVEL).
  if [[ "$below_console" -eq 0 ]]; then
    printf '%s\n' "$stderr_line" >&2 2>/dev/null || true
  fi

  local log_file="${COS_LOG_FILE:-${COS_STATE_DIR}/.cos.log}"
  if [[ "$below_console" -eq 0 ]]; then
    {
      mkdir -p "$(dirname "$log_file")" 2>/dev/null
      printf '%s\n' "$short_line" >> "$log_file"
    } 2>/dev/null || true

    if [[ -n "$json_line" ]]; then
      {
        printf '%s\n' "$json_line" >> "${log_file}.jsonl"
      } 2>/dev/null || true
    fi
  fi

  return 0
}
