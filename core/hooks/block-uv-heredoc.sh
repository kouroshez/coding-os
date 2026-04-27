#!/usr/bin/env bash
# PreToolUse Bash hook: block `uv run ... <<` heredoc patterns.
#
# Source of truth: CLAUDE.md Critical Rule #9 — "Always use Python for
# multi-step verification scripts. Bash heredoc inside `$(...)` with
# `uv run` hangs. Write to a Python file and invoke via
# subprocess.run(..., timeout=N). See scripts/verify_phase_c_e2e.py."
#
# This hook matches three forms observed to hang or truncate silently:
#   1. `uv run python - <<'EOF' ... EOF`     (stdin-piped Python)
#   2. `uv run python -c "$(cat <<'EOF' ...` (heredoc inside command-sub)
#   3. `output=$(uv run python - <<EOF ...)` (capture + stdin-piped)
#
# Escape hatch: touch $COS_AGENT_DIR/.uv-heredoc-override for one-shot bypass.
# Use sparingly — the Python-file pattern is almost always cleaner.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$CMD" ]] && exit 0

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
cos_log_hook block-uv-heredoc fire "tool=Bash"

# One-shot override (consumed on use). Unified registry checked first;
# legacy $COS_AGENT_DIR/.uv-heredoc-override still honoured.
if cos_one_shot_override uv-heredoc 2>/dev/null; then
  cos_log_hook block-uv-heredoc bypass "reason=override"
  exit 0
fi

# Detect `uv run` followed (within reasonable distance) by heredoc operator.
# We accept `<<`, `<<-`, `<<'EOF'`, `<<"EOF"`, `<<EOF` variants.
if echo "$CMD" | grep -qE 'uv[[:space:]]+run[^|&;]*<<'; then
  cos_log_hook block-uv-heredoc block "rule=uv-run-heredoc"
  echo "BLOCKED: \`uv run\` with heredoc is known to hang silently." >&2
  echo "  CLAUDE.md Critical Rule #9 — always use a real Python file:" >&2
  echo "" >&2
  echo "    # write the script" >&2
  echo "    cat > scripts/my_check.py <<'PY'" >&2
  echo "    ..." >&2
  echo "    PY" >&2
  echo "" >&2
  echo "    # then invoke via subprocess-friendly single-quoted path" >&2
  echo "    uv run --extra rag python scripts/my_check.py" >&2
  echo "" >&2
  echo "  Reference: scripts/verify_phase_c_e2e.py" >&2
  echo "  One-shot override: touch $COS_AGENT_DIR/.uv-heredoc-override" >&2
  exit 2
fi

exit 0
