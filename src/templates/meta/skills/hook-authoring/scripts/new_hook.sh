#!/usr/bin/env bash
# new_hook.sh — PURPOSE: scaffold a registry-compliant hook skeleton.
# INPUT: --name <hook-id> [--category safety|enforcement|observability|reminder|
#   cognition|retrieval|meta] [--root src/core/hooks] [--force].
# OUTPUT: <root>/<name>.sh (sources cos-env, set -euo pipefail, stdin read,
#   log calls) + the registry.yaml snippet to paste. DEPS: bash. NOTES:
# idempotent; the script still must be registered by hand in registry.yaml then
# `make regen-adapter-templates`. Spec: docs/playbooks/hook-authoring.md.
set -euo pipefail
IFS=$'\n\t'

log() { printf '%s\n' "$*" >&2; }
usage() { echo "usage: $0 --name <hook-id> [--category C] [--root DIR] [--force]" >&2; exit 2; }

name=""
category="enforcement"
root="src/core/hooks"
force=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)     name="${2:?--name needs a value}"; shift 2 ;;
    --category) category="${2:?--category needs a value}"; shift 2 ;;
    --root)     root="${2:?--root needs a value}"; shift 2 ;;
    --force)    force=1; shift ;;
    -h|--help)  usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[[ -n "$name" ]] || { echo "error: --name is required" >&2; usage; }
[[ "$name" =~ ^[a-z0-9-]+$ ]] || { echo "error: --name must be kebab-case" >&2; exit 2; }

mkdir -p "$root"
target="$root/$name.sh"
if [[ -e "$target" && "$force" -ne 1 ]]; then
  echo "error: $target exists (use --force)" >&2
  exit 1
fi

{
  printf '#!/usr/bin/env bash\n'
  printf '# %s.sh (Phase X) — <one-line purpose>.\n' "$name"
  printf '#\n# <2-3 line description: events, what it reads/writes, fail-open vs closed.>\n'
  printf 'set -euo pipefail\n\n'
  printf 'source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true\n'
  printf 'if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi\n\n'
  printf 'cos_log_hook %s enter || true\n\n' "$name"
  printf 'INPUT="$(cos_read_stdin_bounded 2)"\n'
  printf '# shellcheck disable=SC2034  # placeholders — wire into your decision below\n'
  printf 'FILE_PATH=$(echo "$INPUT" | jq -r '"'"'.tool_input.file_path // empty'"'"' 2>/dev/null || echo "")\n'
  printf '# shellcheck disable=SC2034\n'
  printf 'MARKER="${COS_AGENT_DIR}/.%s-marker"   # never hardcode .claude/ (Rule 1)\n\n' "$name"
  printf '# Decide; warn (exit 0) vs block (exit 2).\n'
  printf 'if false; then\n'
  printf '  echo "warning: <message>" >&2\n'
  printf '  cos_log_hook %s warn || true\n' "$name"
  printf '  exit 0\n'
  printf 'fi\n\n'
  printf 'cos_log_hook %s ok || true\n' "$name"
  printf 'exit 0\n'
} > "$target"
chmod +x "$target"

log "wrote $target"
log ""
log "Now register it in src/core/hooks/registry.yaml (SSOT):"
log "  - id: $name"
log "    script: $name.sh"
log "    description: <one line>"
log "    category: $category"
log "    phase: <PreToolUse|PostToolUse|UserPromptSubmit|SessionStart|Stop>"
log "    timeout: 5"
log "    events: [{event: PreToolUse, matcher: 'Write|Edit', status_message: '<msg>'}]"
log ""
log "Then: make regen-adapter-templates && make verify-hooks"
printf '%s\n' "$target"
