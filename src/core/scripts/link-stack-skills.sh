#!/usr/bin/env bash
# link-stack-skills.sh — symlink stack-scoped skills into an agent's skills dir.
#
# Called by src/cli/main.py after all templates are applied. Agent-agnostic: the
# caller passes the target skills dir, coding-os root, and active stacks.
#
# Usage:
#   bash link-stack-skills.sh <agent_skills_dir> <cos_root> <stack1> [stack2 ...]
#
# Example (claude adapter):
#   bash link-stack-skills.sh /proj/.claude/skills /coding-os django nextjs
# Example (codex adapter):
#   bash link-stack-skills.sh /proj/.agents/skills /coding-os django nextjs
#
# For each stack, walks $cos_root/templates/<stack>/skills/ and creates
# <agent_skills_dir>/<skill_name> folder links pointing at the source.
# Skipped silently if the stack has no skills/ dir.
set -euo pipefail

if [ "$#" -lt 3 ]; then
  echo "Usage: $0 <agent_skills_dir> <cos_root> <stack1> [stack2 ...]" >&2
  exit 64
fi

AGENT_SKILLS_DIR="$1"
COS_ROOT="$2"
shift 2

mkdir -p "$AGENT_SKILLS_DIR"
# shellcheck source=_skill_link.sh
source "$(dirname "$0")/_skill_link.sh"

linked=0
for stack in "$@"; do
  stack_skills_dir="${COS_ROOT}/templates/${stack}/skills"
  if [ ! -d "$stack_skills_dir" ]; then
    continue
  fi
  for skill_dir in "${stack_skills_dir}/"*/; do
    [ -d "$skill_dir" ] || continue
    skill_name="$(basename "$skill_dir")"
    target_skill_md="${skill_dir}SKILL.md"
    if [ ! -f "$target_skill_md" ]; then
      continue
    fi
    cos_link_skill_dir "$skill_dir" "${AGENT_SKILLS_DIR}/${skill_name}" "$COS_ROOT"
    echo "  linked ${stack}/${skill_name}" >&2
    linked=$((linked + 1))
  done
done

echo "[link-stack-skills] linked ${linked} skill(s) across $# stack(s)"
