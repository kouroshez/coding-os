#!/usr/bin/env bash
# link-stack-skills.sh — symlink stack-scoped skills into an agent's skills dir.
#
# Called by cli/main.py after all templates are applied. Agent-agnostic: the
# caller passes the target skills dir, coding-os root, and active stacks.
#
# Usage:
#   bash link-stack-skills.sh <agent_skills_dir> <cos_root> <stack1> [stack2 ...]
#
# Example:
#   bash link-stack-skills.sh /proj/.claude/skills /coding-os django nextjs
#
# For each stack, walks $cos_root/templates/<stack>/skills/ and creates
# <agent_skills_dir>/<skill_name>/SKILL.md symlinks pointing at the source.
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
    link_parent="${AGENT_SKILLS_DIR}/${skill_name}"
    mkdir -p "$link_parent"
    ln -sf "$target_skill_md" "${link_parent}/SKILL.md"
  done
done
