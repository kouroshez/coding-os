#!/usr/bin/env bash
# triage.sh — PURPOSE: one-pass read-only host health snapshot.
# INPUT: [--json] machine output · [--top N] heaviest procs (default 5).
# OUTPUT: summary on stdout (text or JSON). DEPS: coreutils, ps; uses df/free/
# ss/uptime/systemctl when present (degrades gracefully). NOTES: READ-ONLY —
# changes nothing. Portable Linux+macOS. Spec: docs/playbooks/skill-authoring.md.
set -euo pipefail
IFS=$'\n\t'

as_json=0
top_n=5
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) as_json=1; shift ;;
    --top)  top_n="${2:?--top needs a value}"; shift 2 ;;
    -h|--help) echo "usage: $0 [--json] [--top N]" >&2; exit 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

# Collect (each guarded; "-" when the tool is absent).
load="-"; have uptime && load="$(uptime | sed 's/.*load average[s]*: //')"
mem="-";  have free && mem="$(free -h | awk '/^Mem:/{print $3"/"$2" used"}')"
disk="$(df -h / 2>/dev/null | awk 'NR==2{print $5" of "$2" ("$4" free)"}')"
ports="-"; have ss && ports="$(ss -ltn 2>/dev/null | awk 'NR>1{print $4}' | wc -l | tr -d ' ')"
failed="-"
if have systemctl; then
  failed="$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | paste -sd, - )"
  [[ -z "$failed" ]] && failed="none"
fi
# ps flags differ (GNU -eo vs BSD -Ao); try GNU, fall back, never abort.
heaviest="$( { ps -eo pcpu,comm 2>/dev/null || ps -Ao %cpu,comm 2>/dev/null || true; } \
            | sort -rn | head -n "$((top_n + 1))" | tail -n "$top_n" \
            | awk '{printf "%s(%s%%cpu) ", $2, $1}' || true)"
[[ -z "$heaviest" ]] && heaviest="-"

if [[ "$as_json" -eq 1 ]]; then
  esc() { printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'; }
  printf '{"load":"%s","mem":"%s","disk":"%s","listening_ports":"%s","failed_units":"%s","top":"%s"}\n' \
    "$(esc "$load")" "$(esc "$mem")" "$(esc "$disk")" "$(esc "$ports")" "$(esc "$failed")" "$(esc "$heaviest")"
else
  printf 'load   : %s\n' "$load"
  printf 'mem    : %s\n' "$mem"
  printf 'disk / : %s\n' "$disk"
  printf 'ports  : %s listening\n' "$ports"
  printf 'failed : %s\n' "$failed"
  printf 'top%-2d  : %s\n' "$top_n" "$heaviest"
fi
