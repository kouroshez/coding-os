#!/usr/bin/env bash
# PreToolUse Write|Edit hook: block hardcoded stack/adapter literals in cli/*.py.
#
# Catches the SSOT drift at EDIT time instead of test time. Stack and
# adapter IDs ("django", "claude", "python-django", …) must never appear
# as quoted literals inside cli/*.py — the registry loader reads them
# from YAML. Pytest has tests/test_no_hardcoded_stacks.py as the rear
# guard; this hook is the front guard so the offending edit never
# lands on disk.
#
# Scope: only fires for files under cli/*.py (the data-driven layer).
# Everywhere else — tests, templates, adapters — literals are expected.
#
# Escape hatch: $COS_STATE_DIR/.literals-override for one-shot bypass.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# Fail-closed: an SSOT-drift gate that cannot read its input must DENY,
# not silently allow when jq is absent (observability-eye I8). cos_json_field
# falls back to python3, so the gate keeps working when only jq is missing.
cos_require_parser block-hardcoded-literals

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)
[[ -z "$FILE_PATH" ]] && exit 0

# Only guard the data-driven CLI layer.
case "$FILE_PATH" in
  *cli/*.py) ;;
  *) exit 0 ;;
esac

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

if cos_one_shot_override literals 2>/dev/null; then
  exit 0
fi

if [[ "$TOOL" == "Write" ]]; then
  CONTENT=$(printf '%s' "$INPUT" | cos_json_field tool_input.content)
else
  CONTENT=$(printf '%s' "$INPUT" | cos_json_field tool_input.new_string)
fi
[[ -z "$CONTENT" ]] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" && pwd)"
CHECKER="${HOOK_DIR}/../scripts/check_hardcoded_literals.py"

if [[ ! -f "$CHECKER" ]]; then
  exit 0
fi

echo "$CONTENT" | python3 "$CHECKER" --file "$FILE_PATH"
RC=$?

if [[ $RC -eq 2 ]]; then
  echo "  One-shot override: touch $COS_STATE_DIR/.literals-override" >&2
  echo "  (or: echo '{\"literals\":{\"reason\":\"\"}}' > $COS_STATE_DIR/.overrides.json)" >&2
  exit 2
fi

exit 0
