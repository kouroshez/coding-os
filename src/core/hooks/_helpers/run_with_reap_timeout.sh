#!/usr/bin/env bash
# run_with_reap_timeout.sh — sourceable: run a command under a portable hard
# wall-clock ceiling, reaping the WHOLE process subtree on timeout. Both
# timeout(1) and setsid are absent on stock macOS, so this uses a bash
# background watchdog + recursive pgrep tree-kill. Source it, then call:
#   cos_run_with_reap_timeout <seconds> <cmd> [args...]
# Returns the command's exit code, or 137/143 when the watchdog killed a hang.
# Never hangs past <seconds> + ~2s KILL grace.

# Recursively TERM/KILL a pid and all its descendants (pgrep ships on macOS+Linux).
_cos_reap_tree() {
  local pid="$1" sig="${2:-TERM}" child
  while IFS= read -r child; do
    [ -n "$child" ] && _cos_reap_tree "$child" "$sig"
  done < <(pgrep -P "$pid" 2>/dev/null || true)
  kill -"$sig" "$pid" 2>/dev/null || true
}

cos_run_with_reap_timeout() {
  local timeout_s="$1"
  shift
  [ "$#" -gt 0 ] || return 0

  "$@" &
  local cmd_pid=$!

  (
    sleep "$timeout_s"
    if kill -0 "$cmd_pid" 2>/dev/null; then
      _cos_reap_tree "$cmd_pid" TERM
      sleep 2
      _cos_reap_tree "$cmd_pid" KILL
    fi
  ) &
  local watchdog_pid=$!

  local rc=0
  wait "$cmd_pid" 2>/dev/null || rc=$?

  # Command finished (or was reaped) — cancel the watchdog.
  kill "$watchdog_pid" 2>/dev/null || true
  wait "$watchdog_pid" 2>/dev/null || true

  return "$rc"
}
