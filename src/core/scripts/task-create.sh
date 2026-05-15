#!/usr/bin/env bash
# Create a new task file and append an active task entry.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 <NUM> \"<TITLE>\""
  echo ""
  echo "Create a new task detail file and add an entry to the task index."
  echo ""
  echo "Arguments:"
  echo "  NUM      Task number (integer, e.g. 110)"
  echo "  TITLE    Task title with domain tag (e.g. \"[BACKEND] Auth flow implementation\")"
  echo ""
  echo "Domain tags: DOCS, BACKEND, FRONTEND, UI, CONTENT, SEO, FULL-STACK"
  echo "Each tag auto-selects REF codes and playbook routing from domain-config.json."
  echo ""
  echo "Example:"
  echo "  $0 110 \"[DOCS] Task system contract hardening\""
  exit 0
fi

NUM="${1:-}"
TITLE="${2:-}"

if [ -z "$NUM" ] || [ -z "$TITLE" ]; then
  echo "Usage: $0 <NUM> \"<TITLE>\""
  echo "Example: $0 110 \"[DOCS] Task system contract hardening\""
  exit 1
fi

if ! [[ "$NUM" =~ ^[0-9]+$ ]]; then
  err "NUM must be numeric"
fi

TASK_INDEX="docs/tasks.md"
TODAY=$(date +%Y-%m-%d)

python3 - "$NUM" "$TITLE" "$TODAY" "$TASK_INDEX" <<'PY'
import os
from pathlib import Path
import json
import re
import sys

num_raw, title, today, task_index_path = sys.argv[1:5]
num = int(num_raw)
task_id = f"TASK-{num:03d}"
index_path = Path(task_index_path)

tag_match = re.match(r"^\[([^\]]+)\]\s*(.+)$", title)
if tag_match:
    tag = tag_match.group(1).upper()
    short_title = tag_match.group(2).strip()
else:
    tag = "ALL"
    short_title = title.strip()

_cos_state = os.environ.get("COS_STATE_DIR", ".coding-os")
for _cp in [Path(_cos_state) / "domain-config.json", Path("infrastructure/scripts/domain-config.json")]:
    if _cp.exists():
        config_path = _cp
        break
else:
    config_path = None
if config_path is None:
    raise SystemExit(f"ERROR: Config not found: {config_path}")
config = json.loads(config_path.read_text())
domain = config["domain_map"].get(tag, config.get("default_domain", "ALL"))

slug_source = re.sub(r"\[[^\]]+\]", "", title).strip().lower()
slug = re.sub(r"[^a-z0-9]+", "-", slug_source).strip("-")
if not slug:
    raise SystemExit("ERROR: Title must contain at least one alphanumeric character")

target = Path("docs/tasks") / f"{task_id}-{slug}.md"
if target.exists():
    raise SystemExit(f"ERROR: File already exists: {target}")

refs_by_tag = config["refs_by_tag"]
refs = refs_by_tag.get(tag, config["default_refs"])
read_first_lines = "\n".join(f"- `{ref}`" for ref in refs)

# Read canonical template — SSOT for task detail structure
tpl_path = Path("docs/governance/_templates/task-detail.md")
if not tpl_path.exists():
    raise SystemExit(f"ERROR: Template not found: {tpl_path}")
tpl = tpl_path.read_text()

# Phase L lean template detection: presence of YAML frontmatter at the top
# with `id: {{TASK_ID}}` placeholder.  Renders by simple {{...}} substitution.
# Pre-Phase-L 12-section format (with `## Goal` H2) takes the legacy branch.
is_lean_template = tpl.startswith("---") and "{{TASK_ID}}" in tpl

if is_lean_template:
    # Phase L: substitute placeholders in the lean template.
    # Swimlane defaults to a config-mapped value; agents using
    # cos_task_create (L.3) supply the real swimlane explicitly.
    swimlane_default = config.get("swimlane_default", domain.lower() if domain else "core")
    kind_default = config.get("kind_default", "feature")
    priority_default = config.get("priority_default", "P2")
    appetite_default = config.get("appetite_default", "1d")
    substitutions = {
        "{{TASK_ID}}": task_id,
        "{{TITLE}}": title,
        "{{SWIMLANE}}": swimlane_default,
        "{{KIND}}": kind_default,
        "{{EPIC|null}}": "null",
        "{{LABELS|[]}}": "[]",
        "{{PRIORITY|P2}}": priority_default,
        "{{APPETITE|1d}}": appetite_default,
        "{{TODAY}}": today,
        "{{DEPENDS_ON|[]}}": "[]",
        "{{REFERENCES|[]}}": "[]",
    }
    content = tpl
    for placeholder, value in substitutions.items():
        content = content.replace(placeholder, value)

    # Inject domain-specific Read First refs into the placeholder bullets.
    # The lean template ships with two example bullets; replace them with
    # the config-driven REF codes so `enforce-doc-anchor.sh` finds real
    # paths instead of placeholder strings (`path/to/doc.md`).
    rf_header = "## Read First"
    rf_idx = content.find(rf_header)
    if rf_idx != -1:
        next_section = content.find("\n## ", rf_idx + len(rf_header))
        if next_section == -1:
            next_section = len(content)
        rf_block = content[rf_idx:next_section]
        # Trailing comment block + the two placeholder bullets get replaced.
        new_rf = f"{rf_header}\n\n{read_first_lines}\n"
        content = content[:rf_idx] + new_rf + content[next_section:]

    target.write_text(content)
else:
    # Legacy 12-section template path (kept for backward-compat with
    # consumer projects that have not yet run `cos update`).
    content = f"""<!-- domain:{domain} | layer:task | ssot:true | updated:{today} -->
# {task_id}: {title}

Purpose: Execute {short_title.lower()} without drifting from the canonical docs workflow.
Read when: Working on this exact task.
Skip when: Another task is active.

> Nav: [Tasks Index](../tasks.md) | [Docs Index](../00-index.md)

- Created: {today}
"""
    goal_idx = tpl.find("## Goal")
    if goal_idx == -1:
        raise SystemExit("ERROR: Template missing ## Goal section (legacy path)")
    body = tpl[goal_idx:]

    marker = "<!-- DOMAIN_REFS -->"
    if marker in body:
        marker_idx = body.find(marker)
        next_section = body.find("\n## ", marker_idx)
        if next_section == -1:
            next_section = len(body)
        body = body[:marker_idx] + read_first_lines + body[next_section:]

    content += "\n" + body
    target.write_text(content)

text = index_path.read_text()
entry = f"- [ ] {task_id}: {title}\n"
if re.search(rf"^.*{re.escape(task_id)}:.*$", text, re.MULTILINE):
    raise SystemExit(f"ERROR: {task_id} already exists in {index_path}")

# Append new task entry at the end of the task list
text = text.rstrip('\n') + '\n' + entry

index_path.write_text(text)
print(f"Created: {target}")
print(f"Updated: {index_path}")
print()
print("REMINDER: Before starting, verify each requirement has:")
print("  - Specific verb + target")
print("  - SSOT document reference")
print("  - Testable Given/When/Then criteria")
print("  See docs/engineering/anti-ambiguity.md for guidance.")
PY

# Phase C: fire-and-forget full sync — indexes the new task file into
# the tasks table (with embedding if rag extras are available).
#
# TASK-030 root cause: when the caller is `subprocess.Popen(..., capture_output=True)`
# (as pytest does via `make task-create`), a naïve `python3 ... &` inherits
# the captured stdout/stderr pipes on fds 1/2 — and `communicate()` blocks
# until every writer on those pipes exits. Fire-and-forget becomes blocking.
# Fix: spawn the sync through a daemonised Python helper that double-forks
# itself, so the grandchild has no inherited fds and the parent shell can
# return immediately. `COS_DISABLE_TASK_SYNC=1` opts out entirely.
if [ "${COS_DISABLE_TASK_SYNC:-0}" != "1" ]; then
  python3 "$(dirname "$0")/_daemon_task_sync.py" >/dev/null 2>&1 </dev/null || true
fi
