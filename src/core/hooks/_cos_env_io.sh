#!/usr/bin/env bash
# Coding OS - Interpreter resolution, bounded stdin and JSON field access.
# Sourced by cos-env.sh from its own resolved directory; never run
# directly and never sourced by a hook.

# Echo a python interpreter that can import cos's installed extras (the `rag`
# group: sentence_transformers). Bare python3 usually lacks them; the `cos`
# entry point's shebang points at the venv that has them. Falls back to python3.
cos_resolve_python() {
  local gc ac py
  gc="$(command -v cos 2>/dev/null || true)"
  if [[ -z "$gc" ]]; then command -v python3 2>/dev/null || true; return; fi
  ac="$gc"
  if [[ -L "$gc" ]]; then
    ac="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$gc" 2>/dev/null || echo "$gc")"
  fi
  py="$(awk 'NR==1{sub(/^#!/,""); sub(/[[:space:]].*$/,""); print; exit}' "$ac" 2>/dev/null || true)"
  if [[ -z "$py" || ! -x "$py" ]]; then py="$(dirname "$ac")/python3"; fi
  [[ -x "$py" ]] || py="$(command -v python3 2>/dev/null || true)"
  printf '%s\n' "$py"
}

# ---------------------------------------------------------------------------
# cos_read_stdin_bounded — drain stdin with a hard timeout
#
# WHY
#   Hooks read JSON from stdin (PreToolUse / PostToolUse / Stop / etc.).
#   When invoked from a terminal (`bash hook.sh` for testing), stdin is
#   a tty and `cat` would block forever waiting for the user. perl's
#   alarm() gives us a portable stdin read with a hard ceiling — bash's
#   `read -t` doesn't slurp multi-line JSON, and `timeout(1)` is missing
#   on macOS by default. Also: when the agent runtime sends nothing, we
#   want to fall through to defaults rather than hang the hook.
#
# USAGE
#   INPUT="$(cos_read_stdin_bounded 2)"      # 2-second ceiling
#
# DEGRADATION (observability-eye I8)
#   perl → python3 → cat. perl stays the fast path (~5 ms vs python3's ~50 ms
#   startup, on a helper that runs 39× per file edit), but it is NOT a coding-os
#   dependency and slim/Alpine images ship without it. The old perl-only body
#   ended in `|| true`, so "no perl" produced an empty envelope — and an empty
#   envelope makes every gate take its no-op branch and exit 0, silently
#   disabling the whole enforcement layer, block-secrets included. The `cat`
#   floor is safe: the tty case already returned above, and an agent runtime
#   always closes the pipe.
#
# CONTRACT
#   - Returns whatever bytes arrived on stdin (possibly empty).
#   - On timeout: prints what was read so far, returns 0.
#   - When stdin is a tty: returns immediately with empty output.
# ---------------------------------------------------------------------------
cos_read_stdin_bounded() {
  local timeout_s="${1:-2}"
  if [[ -t 0 ]]; then
    return 0
  fi
  if command -v perl >/dev/null 2>&1; then
    perl -e '
      my $timeout = shift // 2;
      eval {
        local $SIG{ALRM} = sub { die "cos_stdin_timeout\n" };
        alarm $timeout;
        local $/;
        my $data = <STDIN>;
        alarm 0;
        print $data if defined $data;
      };
      exit 0;
    ' "$timeout_s" 2>/dev/null || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    python3 "$(_cos_helpers_dir)/read_stdin.py" "$timeout_s" 2>/dev/null || true
    return 0
  fi
  cat 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# cos_require_or_skip — fail-open when a required CLI binary is absent
#
# WHY
#   Hooks hard-depend on `jq` and `python3`. Fresh-clone or minimal-CI
#   runtimes may lack one. With `set -euo pipefail` a missing binary
#   would kill the hook (exit ≠ 0 → BLOCK from the agent's POV). This
#   helper logs a `skip reason=missing_dep` event and exits 0 so the
#   hook degrades gracefully.
#
# USAGE (top of hook, after sourcing cos-env.sh)
#   cos_require_or_skip jq block-secrets
#
# STRICT MODE
#   COS_STRICT_DEPS=1 makes missing deps exit 2 (block) instead of 0.
#   Opt-in for CI that demands a fully-set-up environment.
# ---------------------------------------------------------------------------
cos_require_or_skip() {
  local bin="$1"
  local hook_id="${2:-unknown-hook}"
  if command -v "$bin" >/dev/null 2>&1; then
    return 0
  fi
  cos_log_hook "$hook_id" "skip" "reason=missing_dep dep=$bin" 2>/dev/null || true
  if [[ "${COS_STRICT_DEPS:-0}" == "1" ]]; then
    echo "BLOCKED: hook $hook_id needs '$bin' on PATH (COS_STRICT_DEPS=1)" >&2
    exit 2
  fi
  exit 0
}

# ---------------------------------------------------------------------------
# cos_require_parser <hook_id> — fail-CLOSED dep guard for harm gates.
#
# WHY
#   An irreversible/integrity-harm gate (block-secrets, block-dangerous-
#   commands, ...) must be able to read its decision input. The old
#   `jq -r '...' || echo ""` returned empty when jq was missing → the gate
#   exited 0 (allow) and silently disabled itself. observability-eye I8:
#   a guard that cannot evaluate must DENY, not allow.
#
# CONTRACT
#   Run at the TOP of a harm gate, OUTSIDE command-substitution (so the
#   exit can actually block). Returns 0 when at least one JSON parser
#   (jq OR python3) is on PATH; otherwise captures + exit 2 (block).
#   python3 is a hard dep of coding-os, so the realistic degraded case
#   (jq absent) still passes — cos_json_field falls back to python3.
#
# ESCAPE
#   COS_ALLOW_MISSING_DEPS=1 lets a human bootstrap (install jq/python3)
#   when both are absent.
# ---------------------------------------------------------------------------
cos_require_parser() {
  local hook_id="${1:-unknown-hook}"
  if command -v jq >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${COS_ALLOW_MISSING_DEPS:-0}" == "1" ]]; then
    cos_log_hook "$hook_id" "skip" "reason=no_parser_override" 2>/dev/null || true
    return 0
  fi
  cos_say error "hook.${hook_id}" "no JSON parser (jq/python3) on PATH — gate fails closed" 2>/dev/null || true
  cos_log_hook "$hook_id" "block" "rule=no-parser-fail-closed" 2>/dev/null || true
  echo "BLOCKED: $hook_id needs jq or python3 to evaluate safety — neither found. Install one, or set COS_ALLOW_MISSING_DEPS=1 to bootstrap." >&2
  exit 2
}

# ---------------------------------------------------------------------------
# cos_json_field <path...> — extract first non-empty string field from a hook
# JSON envelope read on stdin. jq fast-path, python3 fallback.
#
# Echoes the value (empty if the field is genuinely absent). Does NOT block
# on a missing parser — that is cos_require_parser's job, which must run
# outside command-substitution. Replaces the `jq -r '...' || echo ""` idiom
# whose empty-on-missing-jq result drove the harm-gate fail-open class.
#
# USAGE
#   TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
#   CONTENT=$(printf '%s' "$INPUT" | cos_json_field tool_input.new_string tool_input.content)
# ---------------------------------------------------------------------------
cos_json_field() {
  local input filter="" p
  input="$(cat)"
  if command -v jq >/dev/null 2>&1; then
    for p in "$@"; do
      [[ -n "$filter" ]] && filter+=" // "
      filter+=".${p}"
    done
    filter+=" // empty"
    printf '%s' "$input" | jq -r "$filter" 2>/dev/null || true
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s' "$input" \
      | python3 "$(_cos_helpers_dir)/json_field.py" "$@" 2>/dev/null || true
    return 0
  fi
  return 0
}
