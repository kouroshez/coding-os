#!/usr/bin/env bash
# PostToolUse Write|Edit hook: remind to regenerate derived artifacts when
# source-of-truth data files change. Never blocks — the agent chooses when.
#
# These file classes drive generated artifacts that CI/tests expect to
# match exactly. A stale artifact causes silent test failures in
# test_manifest_fresh, test_golden_parity, and test_rules_fresh.
#
#   src/templates/<stack>/stack.yaml     → make regen-rules + make manifest-regen
#   src/adapters/<agent>/adapter.yaml    → make manifest-regen
#   src/templates/_base/scaffold/**      → make manifest-regen + capture_golden
#   src/templates/<stack>/scaffold/**    → make manifest-regen + capture_golden
#
# Generated outputs are also flagged so the agent doesn't hand-edit them:
#
#   src/core/rules/dimension-registry.md  (generated — edit stack.yaml::dimensions)
#   src/core/rules/skill-enforcement.md   (generated — edit stack.yaml::skill_enforcement)
#   src/core/scaffold_manifest.json       (generated — run make manifest-regen)
#   tests/golden/**                   (generated — run src/scripts/capture_golden.py)
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

COMMANDS=()
HEADLINE=""

# ── Warn on edits to generated files first ─────────────────────────
BASENAME=$(basename "$FILE_PATH")
case "$FILE_PATH" in
  */core/rules/dimension-registry.md|*/core/rules/skill-enforcement.md)
    echo ""
    echo "  ⚠️  [regen] You edited a GENERATED rule file." >&2
    echo "     Hand-edits will be overwritten by \`make regen-rules\`." >&2
    echo "     Instead, edit the source field in src/templates/<stack>/stack.yaml:" >&2
    if [[ "$BASENAME" == "dimension-registry.md" ]]; then
      echo "       dimensions: [{name, read_files}, ...]" >&2
    else
      echo "       skill_enforcement: [{globs, primary, secondary}, ...]" >&2
    fi
    echo "     Then: make regen-rules" >&2
    exit 0
    ;;
  */core/scaffold_manifest.json)
    echo ""
    echo "  ⚠️  [regen] You edited a GENERATED manifest." >&2
    echo "     Run \`make manifest-regen\` to reflect templates/ state." >&2
    exit 0
    ;;
  */tests/golden/*)
    echo ""
    echo "  ⚠️  [regen] You edited a GENERATED golden fixture." >&2
    echo "     Regenerate via: uv run python src/scripts/capture_golden.py --section <id>" >&2
    exit 0
    ;;
esac

# ── Detect source-of-truth changes + emit matching regen commands ─
case "$FILE_PATH" in
  */templates/*/stack.yaml)
    HEADLINE="stack.yaml changed — regenerate derived artifacts:"
    COMMANDS+=("make regen-rules")
    COMMANDS+=("make manifest-regen")
    ;;
  */adapters/*/adapter.yaml)
    HEADLINE="adapter.yaml changed — regenerate manifest:"
    COMMANDS+=("make manifest-regen")
    ;;
  */templates/_base/scaffold/*|*/templates/*/scaffold/*)
    HEADLINE="scaffold file changed — regenerate manifest + golden fixtures:"
    COMMANDS+=("make manifest-regen")
    # Suggest regenerating all relevant golden sections. The user can narrow.
    COMMANDS+=("uv run python src/scripts/capture_golden.py --section <section_id>")
    COMMANDS+=("(or regenerate all matching sections)")
    ;;
  */core/hooks/*.sh)
    # New hook file (not edit-in-place): manifest snapshot changes.
    if [[ "$TOOL" == "Write" ]]; then
      HEADLINE="new hook file — golden fixtures include hook list:"
      COMMANDS+=("make manifest-regen")
      COMMANDS+=("uv run python src/scripts/capture_golden.py --section <affected_sections>")
    fi
    ;;
esac

if [[ ${#COMMANDS[@]} -eq 0 ]]; then
  exit 0
fi

echo ""
echo "  🔄 [regen] $HEADLINE"
for cmd in "${COMMANDS[@]}"; do
  echo "     $ $cmd"
done
echo "     (Failing CI after this file? 90% of the time it's a missing regen.)"

exit 0
