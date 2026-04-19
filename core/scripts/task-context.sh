#!/usr/bin/env bash
# Show compact task context for agents.
set -euo pipefail
source "$(dirname "$0")/_lib.sh"

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 <TASK>"
  echo ""
  echo "Show compact task context for AI agents. Read-only, no file modifications."
  echo ""
  echo "Arguments:"
  echo "  TASK    Task number or ID (e.g. 43, 043, TASK-43, TASK-043)"
  echo ""
  echo "Output sections:"
  echo "  Task              Index entry + file path"
  echo "  Domain            Detected domain + playbook route"
  echo "  Read First        Resolved REF:* codes -> file paths"
  echo "  Verification      Domain-specific make commands"
  echo "  Dependencies      Prerequisite tasks + status"
  echo "  Session Checkpoint  Previous progress (if exists)"
  echo "  Warnings          Missing files, normalization notes"
  exit 0
fi

RAW_TASK="${1:-${TASK:-}}"

if [ -z "$RAW_TASK" ]; then
  echo "Usage: $0 <TASK number or TASK-###>"
  exit 1
fi

python3 - "$RAW_TASK" <<'PY'
import os
from pathlib import Path
import json
import re
import sys

raw_task = sys.argv[1]
match = re.fullmatch(r"(?:TASK-?)?(\d+)", raw_task)
if not match:
    raise SystemExit("Usage: task-context <TASK number or TASK-###>")

task_num = int(match.group(1))
task_id = f"TASK-{task_num:03d}"
root = Path(".")
index_path = root / "docs/tasks.md"
foundation_path = root / "docs/foundation-map.md"

index_text = index_path.read_text()
index_lines = index_text.splitlines()
# Match only checkbox lines, not dependency references
task_pat = re.compile(rf"^- \[.\] {re.escape(task_id)}:")
index_line = next((line for line in index_lines if task_pat.match(line.strip())), "")

if not index_line:
    print(f"ERROR: {task_id} not found in {index_path}")
    sys.exit(1)

task_files = sorted((root / "docs/tasks").glob(f"{task_id}-*.md"))
task_file = task_files[0] if task_files else None

ref_map = {}
if foundation_path.exists():
    for line in foundation_path.read_text().splitlines():
        m = re.match(r"- `(REF:[A-Z0-9_-]+)` → `(.*)`", line)
        if m:
            ref_map[m.group(1)] = m.group(2)

def parse_section(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    if start is None:
        return []
    out = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        out.append(line)
    while out and out[0].strip() == "":
        out.pop(0)
    while out and out[-1].strip() == "":
        out.pop()
    return out

def detect_status_from_index(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("- [ ]"):
        return "open"
    if stripped.startswith("- [/]") or stripped.startswith("[/]"):
        return "wip"
    if stripped.startswith("- [x]"):
        return "done"
    if stripped.startswith("- (BLOCKED:") or stripped.startswith("(BLOCKED:"):
        return "blocked"
    return "unknown"

_cos_state = os.environ.get("COS_STATE_DIR", ".coding-os")
for _cp in [Path(_cos_state) / "domain-config.json", Path("infrastructure/scripts/domain-config.json")]:
    if _cp.exists():
        config_path = _cp
        break
else:
    config_path = None
if not config_path.exists():
    raise SystemExit(f"ERROR: Config not found: {config_path}")
config = json.loads(config_path.read_text())

def suggest_playbook(line: str) -> str:
    for tag, playbook in config["playbook_map"].items():
        if f"[{tag}]" in line:
            return playbook
    return config["default_playbook"]

warnings = []
index_status = detect_status_from_index(index_line) if index_line else "missing"
task_text = task_file.read_text() if task_file else ""

if index_line and index_status in {"wip", "done", "blocked"} and not task_file:
    warnings.append("Primary task file is missing for a non-backlog task state.")
if raw_task != task_id and raw_task != str(task_num):
    warnings.append(f"Normalized task id to {task_id}.")

print("=== Task ===")
if index_line:
    print(index_line)
else:
    print(f"No active index entry found for {task_id}")
print(f"File: {task_file if task_file else '(no detail file found)'}")

# Domain + Playbook detection
playbook = suggest_playbook(index_line) if index_line else config["default_playbook"]
domain_tag = "UNKNOWN"
for tag in config["playbook_map"]:
    if f"[{tag}]" in (index_line or ""):
        domain_tag = tag
        break
print(f"\n=== Domain ===")
print(f"Tag: {domain_tag} | Playbook: {playbook}")

# Scope suggestion from Scope In section
if task_file:
    scope_in = parse_section(task_text, "### In")
    item_count = sum(1 for l in scope_in if l.strip().startswith("-"))
    if item_count <= 2:
        scope_hint = "Small (1-2 items)"
    elif item_count <= 5:
        scope_hint = "Medium (3-5 items)"
    else:
        scope_hint = "Large (6+ items)"
    print(f"Scope hint: {scope_hint} ({item_count} scope items)")
    checkpoint_lines = parse_section(task_text, "### Session Checkpoint")
    cp_text = " ".join(checkpoint_lines).lower()
    if any(w in cp_text for w in ["complete", "verification only", "needs only", "already"]):
        print("  ^ Note: Checkpoint suggests reduced scope (verification/completion phase)")

print("\n=== Read First ===")
if task_file:
    read_first = parse_section(task_text, "## Read First")
    if read_first:
        for line in read_first:
            ref_match = re.search(r"`?(REF:[A-Z0-9_-]+)`?", line)
            if ref_match and ref_match.group(1) in ref_map:
                print(f"- `{ref_match.group(1)}` -> `{ref_map[ref_match.group(1)]}`")
            elif line.strip():
                print(line)
    else:
        print("- No `## Read First` section found.")
else:
    print("- `docs/tasks.md`")
    print("- `AGENTS.md`")

print("\n=== Verification ===")
if task_file:
    verification = parse_section(task_text, "## Verification")
    if verification:
        for line in verification:
            if line.strip():
                print(line)
    else:
        print("- No `## Verification` section found.")
else:
    fallback = suggest_playbook(index_line)
    if "docs-governance" in fallback:
        print("- `make docs-lint`")
    elif "frontend-ui" in fallback and "backend-api" not in fallback:
        print("- `npm run lint`")
    elif "backend-api" in fallback and "frontend-ui" not in fallback:
        print("- `make lint-backend`")
        print("- `make test-backend`")
    else:
        print("- Choose verification from the matching playbook.")

print("\n=== Dependencies ===")
if task_file:
    deps = parse_section(task_text, "## Dependencies")
    dep_tasks = []
    for line in deps:
        for m in re.finditer(r"TASK-(\d{3})", line):
            dep_tasks.append(m.group(1))
    if dep_tasks:
        for dep_id in dep_tasks:
            dep_task_id = f"TASK-{dep_id}"
            dep_line = next((l for l in index_lines if dep_task_id in l and ":" in l), "")
            dep_status = detect_status_from_index(dep_line) if dep_line else "not found"
            marker = "WARNING" if dep_status not in {"done"} else "ok"
            print(f"- {dep_task_id}: {dep_status} ({marker})")
    else:
        print("- None logged.")
else:
    print("- No detail file to check.")

# Experiments
print("\n=== Experiments ===")
if task_file:
    experiments = parse_section(task_text, "## Experiments")
    table_rows = [l for l in experiments if l.strip().startswith("|") and "---" not in l and "Hypothesis" not in l]
    if table_rows:
        for line in table_rows:
            print(line)
    else:
        print("- No experiments recorded.")
else:
    print("- No detail file.")

# Session Checkpoint
print("\n=== Session Checkpoint ===")
if task_file:
    checkpoint = parse_section(task_text, "### Session Checkpoint")
    if checkpoint:
        for line in checkpoint:
            if line.strip():
                print(line)
    else:
        print("- No previous session checkpoint.")
else:
    print("- No detail file.")

# Status mismatch detection
if task_file and index_status == "open":
    notes = parse_section(task_text, "## Notes")
    notes_text = " ".join(notes).lower()
    if any(w in notes_text for w in ["complete", "implemented", "done", "finished", "already exists"]):
        warnings.append(f"Status is [ ] (open) but Notes suggest work may already be complete. Verify before starting.")

print("\n=== Warnings ===")
if warnings:
    for warning in warnings:
        print(f"- {warning}")
else:
    print("- None.")
PY
