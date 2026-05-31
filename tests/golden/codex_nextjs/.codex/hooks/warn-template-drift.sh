#!/usr/bin/env bash
# PreToolUse hook (transitional): warn when an adapter template JSON is
# edited directly instead of via src/core/hooks/registry.yaml.
#
# The registry is now the SSOT for hook registration. Hand-editing
# adapters/*/settings.template.json or adapters/*/hooks.template.json
# will be overwritten on the next `make regen-adapter-templates`. This
# hook catches the drift at edit time.
#
# ⚠️ Delete this hook once the registry has been load-bearing for one
# full release cycle and no one hand-edits the templates anymore. The
# `category: meta` + `phase: G` markers in registry.yaml flag it as
# transitional.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

case "$FILE_PATH" in
  */adapters/claude/settings.template.json|*/adapters/codex/hooks.template.json)
    ;;
  *)
    exit 0
    ;;
esac

cos_log_hook warn-template-drift fire "path=${FILE_PATH}"

cat >&2 <<MSG
⚠️  You are editing a generated adapter template:
     $FILE_PATH

   This file is regenerated from src/core/hooks/registry.yaml on:
     make regen-adapter-templates
     (or automatically during \`make dogfood-full\`)

   Your edit will be overwritten on the next regen. Instead:
     1. Open src/core/hooks/registry.yaml
     2. Find or add the hook entry
     3. Run: make regen-adapter-templates

   Set \$COS_STATE_DIR/.template-drift-override to bypass once (rare).
MSG

# One-shot override for intentional edits (e.g. debugging the renderer).
OVERRIDE="${COS_STATE_DIR:-.coding-os}/.template-drift-override"
if [[ -f "$OVERRIDE" ]]; then
  rm -f "$OVERRIDE"
  cos_log_hook warn-template-drift override-used ""
  exit 0
fi

cos_log_hook warn-template-drift warn "no-override"
# Warn only, don't block — the edit might be part of a conscious
# transition. The next regen will reset it if it was unintentional.
exit 0
