#!/usr/bin/env bash
# Start a task: create detail file if missing, mark [/], load context.
# Usage: task-start.sh <TASK number or TASK-###>
set -euo pipefail
source "$(dirname "$0")/_lib.sh"
source "$(dirname "$0")/../hooks/cos-env.sh" 2>/dev/null || true

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 <TASK>"
  echo ""
  echo "Start a task: create detail file if missing, mark [/] in-progress, load context."
  echo ""
  echo "Arguments:"
  echo "  TASK    Task number or ID (e.g. 43, 043, TASK-43, TASK-043)"
  echo ""
  echo "Steps performed:"
  echo "  1. Validate task exists in docs/tasks.md"
  echo "  2. Create detail file from template if missing"
  echo "  3. Mark task [/] in index"
  echo "  4. Check dependencies and warn if prerequisites not done"
  echo "  5. Load context via task-context.sh"
  echo ""
  echo "Guards:"
  echo "  - Refuses to start already-done tasks"
  echo "  - Refuses to start BLOCKED tasks"
  echo "  - Warns about incomplete dependencies (non-blocking)"
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
from datetime import date
import json
import re
import sys

raw_task = sys.argv[1]
match = re.fullmatch(r"(?:TASK-?)?(\d+)", raw_task)
if not match:
    raise SystemExit("Usage: task-start <TASK number or TASK-###>")

task_num = int(match.group(1))
padded = f"{task_num:03d}"
task_id = f"TASK-{padded}"
root = Path(".")
index_path = root / "docs/tasks.md"
# Search for config in COS_STATE_DIR, then legacy path
_cos_state = os.environ.get("COS_STATE_DIR", ".coding-os")
for _cp in [Path(_cos_state) / "domain-config.json", Path("infrastructure/scripts/domain-config.json")]:
    if _cp.exists():
        config_path = _cp
        break
else:
    config_path = None
if config_path is None:
    raise SystemExit(f"ERROR: Config not found: {config_path}")

index_text = index_path.read_text()
index_lines = index_text.splitlines()

# Find the task line in the index — match only checkbox lines, not dependency references
task_pattern = re.compile(rf"^- \[.\] {re.escape(task_id)}:")
task_line = None
task_line_idx = None
for i, line in enumerate(index_lines):
    if task_pattern.match(line.strip()):
        task_line = line
        task_line_idx = i
        break

if task_line is None:
    raise SystemExit(f"ERROR: {task_id} not found in {index_path}")

# Detect current status
stripped = task_line.strip()
if stripped.startswith("- [x]"):
    print(f"Task {task_id} is already done. Cannot start.")
    sys.exit(1)
if stripped.startswith("- (BLOCKED:"):
    reason = re.search(r"\(BLOCKED:\s*(.+?)\)", stripped, re.IGNORECASE)
    reason_text = reason.group(1) if reason else "unknown"
    print(f"Task {task_id} is BLOCKED: {reason_text}")
    sys.exit(1)

is_already_wip = stripped.startswith("- [/]") or stripped.startswith("[/]")

# Extract title from index line
title_match = re.search(rf"{re.escape(task_id)}:\s*(.+)$", task_line)
title = title_match.group(1).strip() if title_match else f"[ALL] {task_id}"

# Step 1: Check if detail file exists, create if missing
task_files = sorted((root / "docs/tasks").glob(f"{task_id}-*.md"))
detail_file = task_files[0] if task_files else None

if detail_file is None:
    print(f"Creating detail file for {task_id}...")
    today = date.today().isoformat()

    # Parse domain tag from title
    tag_match = re.match(r"^\[([^\]]+)\]\s*(.+)$", title)
    tag = tag_match.group(1).upper() if tag_match else "ALL"
    short_title = tag_match.group(2).strip() if tag_match else title.strip()

    config = json.loads(config_path.read_text())
    domain = config["domain_map"].get(tag, config.get("default_domain", "ALL"))

    slug_source = re.sub(r"\[[^\]]+\]", "", title).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug_source).strip("-")
    if not slug:
        slug = f"task-{padded}"

    # Domain-aware REF codes
    refs_by_tag = config["refs_by_tag"]
    refs = refs_by_tag.get(tag, config["default_refs"])
    read_first_lines = "\n".join(f"- `{ref}`" for ref in refs)

    target = root / "docs/tasks" / f"{task_id}-{slug}.md"

    # Read canonical template — SSOT for task detail structure
    tpl_path = root / "docs/governance/templates/task-detail.md"
    if not tpl_path.exists():
        raise SystemExit(f"ERROR: Template not found: {tpl_path}")
    tpl = tpl_path.read_text()

    # Replace template header/metadata with task-specific values
    content = f"""<!-- domain:{domain} | layer:task | ssot:true | updated:{today} -->
# {task_id}: {title}

Purpose: Execute {short_title.lower()} without drifting from the canonical docs workflow.
Read when: Working on this exact task.
Skip when: Another task is active.

> Nav: [Tasks Index](../tasks.md) | [Docs Index](../00-index.md)

- Created: {today}
"""
    # Extract body sections from canonical template (everything from ## Goal onward)
    goal_idx = tpl.find("## Goal")
    if goal_idx == -1:
        raise SystemExit("ERROR: Template missing ## Goal section")
    body = tpl[goal_idx:]

    # Inject domain-specific Read First refs using marker
    marker = "<!-- DOMAIN_REFS -->"
    if marker in body:
        marker_idx = body.find(marker)
        next_section = body.find("\n## ", marker_idx)
        if next_section == -1:
            next_section = len(body)
        body = body[:marker_idx] + read_first_lines + body[next_section:]

    content += "\n" + body
    target.write_text(content)
    detail_file = target
    print(f"Created: {detail_file}")

# Step 2: Mark [/] in index (if currently open)
if not is_already_wip:
    stripped_line = task_line.strip()
    if stripped_line.startswith("- [ ]"):
        new_line = task_line.replace("- [ ]", "- [/]", 1)
        index_lines[task_line_idx] = new_line
        index_path.write_text("\n".join(index_lines) + "\n")
        print(f"Marked {task_id} as [/] in index.")

    # Status is tracked only in docs/tasks.md — no status update in detail file.
else:
    print(f"{task_id} is already in progress [/].")

# Step 2.5: Check dependencies (informational warning)
if detail_file and detail_file.exists():
    dep_text = detail_file.read_text()
    dep_section = []
    in_deps = False
    for dline in dep_text.splitlines():
        if dline.strip() == "## Dependencies":
            in_deps = True
            continue
        if in_deps and dline.startswith("## "):
            break
        if in_deps:
            dep_section.append(dline)

    dep_ids = re.findall(r"TASK-(\d{3})", "\n".join(dep_section))
    if dep_ids:
        not_done = []
        for dep_id in dep_ids:
            dep_task_id = f"TASK-{dep_id}"
            dep_line = next((l for l in index_lines if dep_task_id in l and ":" in l), "")
            if dep_line and not dep_line.strip().startswith("- [x]"):
                not_done.append(dep_task_id)
        if not_done:
            print(f"WARNING: Dependencies not yet done: {', '.join(not_done)}")
            print("  Proceeding anyway. Check dependency status before closing this task.")

# --- Doc anchor extraction (docs-first principle) ---
# The active task file's "Source of Truth" and "Read First" sections are
# the contract between the user's docs and the code the agent writes.
# We extract them into $COS_STATE_DIR/.doc-anchor so enforce-doc-anchor.sh
# can verify every code Edit/Write traces back to real docs.
#
# PLACEHOLDER_PATTERNS are the template defaults left unfilled — if those
# are all we see, the task isn't ready to start and we emit a warning so
# the user/agent populates the section before writing code.
PLACEHOLDER_RE = re.compile(
    r"(\{[^}]*\}|_\(not recorded\)_|_\(to be defined\)_|\(none\)|^-?\s*$)",
    re.IGNORECASE,
)

def _is_placeholder_line(line: str) -> bool:
    """Return True when a task template default slipped into the section."""
    normalized = re.sub(r"^[-*]\s+", "", line.strip())
    if PLACEHOLDER_RE.fullmatch(normalized):
        return True
    if normalized.lower().startswith("**required"):
        return True
    if normalized.startswith("Pre-implementation:") and "docs/..." in normalized:
        return True
    if normalized.startswith("Post-implementation:") and "path/to/code.ext" in normalized:
        return True
    if normalized in {"`docs/...`", "`path/to/code.ext`", "docs/...", "path/to/code.ext"}:
        return True
    return False

def _extract_section(body: str, heading: str) -> list[str]:
    """Return the non-empty, non-placeholder lines under an H2 heading."""
    lines = body.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if line.strip() == f"## {heading}":
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("<!--") and stripped.endswith("-->"):
                continue
            if _is_placeholder_line(stripped):
                continue
            out.append(stripped)
    return out

anchor_lines: list[str] = []
if detail_file and detail_file.exists():
    _detail_text = detail_file.read_text(encoding="utf-8")
    anchor_lines = (
        _extract_section(_detail_text, "Source of Truth")
        + _extract_section(_detail_text, "Read First")
    )

_anchor_path = Path(os.environ.get("COS_STATE_DIR", ".coding-os")) / ".doc-anchor"
_session_path = Path(os.environ.get("COS_STATE_DIR", ".coding-os")) / "session-id"
_session_id = _session_path.read_text().strip() if _session_path.exists() else ""

if anchor_lines:
    _anchor_path.write_text(
        f"{_session_id} task:{task_id}\n" + "\n".join(anchor_lines) + "\n",
        encoding="utf-8",
    )
    print(f"📎 Doc anchor recorded: {len(anchor_lines)} reference(s) from {detail_file.name}")
else:
    # Task file has no usable anchors yet — emit a clear warning but
    # don't block task-start (the agent may be about to fill them in).
    # enforce-doc-anchor.sh will block any subsequent code write until
    # the anchor is populated.
    print()
    print(f"⚠️  Task {task_id} has no Source of Truth or Read First references.")
    print(f"   Populate docs/tasks/{detail_file.name if detail_file else task_id + '*.md'}")
    print(f"   with real doc paths, then re-run `make task-start TASK={task_num}`.")
    print(f"   Code Write/Edit will be BLOCKED until the anchor is recorded.")
    print()

# --- Learning suggestions (fire-and-forget) ---
db_path = Path(os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db"))
if db_path.exists():
    try:
        import sqlite3
        _conn = sqlite3.connect(str(db_path), timeout=2)
        _conn.row_factory = sqlite3.Row

        # Detect domain from title
        _title_lower = title.lower()
        _domain = "INFRA"
        for _d, _signals in [
            ("BACKEND", ["backend", "django", "api", "model"]),
            ("FRONTEND", ["frontend", "react", "next", "component", "ui"]),
            ("DOCS", ["doc", "governance", "content"]),
        ]:
            if any(s in _title_lower for s in _signals):
                _domain = _d
                break

        # Read complexity from gate file (session-scoped: "session-id CLASSIFICATION N")
        _complexity = ""
        _gate = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/.thinking_os-gate")
        if _gate.exists():
            _parts = _gate.read_text().strip().split()
            # Skip session ID prefix (first field) if present
            _complexity = _parts[1] if len(_parts) >= 2 else _parts[0]

        sys.path.insert(0, os.environ.get("COS_BRAIN_DIR", str(Path(__file__).resolve().parent.parent / "thinking_os")))
        from tools.learning import learn_suggest
        _result = learn_suggest(_conn, domain=_domain, complexity=_complexity, limit=3)
        _suggestions = _result.get("suggestions", [])
        if _suggestions:
            print("💡 Learned patterns relevant to this task:")
            for s in _suggestions:
                print(f"   • {s['pattern']} (confidence: {s['confidence']:.2f})")
            print()
        _conn.close()
    except Exception:
        pass  # fire-and-forget: never block task-start

# --- Phase M: Persona + Situation markers ---
# Populate .persona, .situation, .formulas in $COS_AGENT_DIR so the
# supervisor (cos_supervise) and hook (enforce-anti-ambiguity.sh) know
# which cognitive routing was chosen for this task.
try:
    _cos_agent_dir = Path(os.environ.get("COS_AGENT_DIR", ".coding-os/claude"))
    _cos_agent_dir.mkdir(parents=True, exist_ok=True)

    # Read Phase M override fields from task YAML frontmatter
    _intensity_val = None
    _persona_override = None
    _situation_override = None
    if detail_file and detail_file.exists():
        import re as _fm_re
        _task_text = detail_file.read_text(encoding="utf-8")
        _fm = _fm_re.match(r"^---\s*\n(.*?)\n---\s*\n", _task_text, _fm_re.DOTALL)
        if _fm:
            try:
                import yaml as _yaml
                _fm_data = _yaml.safe_load(_fm.group(1)) or {}
                _intensity_val = _fm_data.get("intensity")
                _persona_override = _fm_data.get("persona")
                _situation_override = _fm_data.get("situation")
            except Exception:
                pass

    # Write situation marker
    if _situation_override:
        (_cos_agent_dir / ".situation").write_text(str(_situation_override), encoding="utf-8")

    # Phase N: compose role chain from task signals (replaces deprecated persona auto-route).
    # Frontmatter override (chain or single role) wins; otherwise use a default
    # analyst,architect,implementer,reviewer chain — agents call cos_compose_chain for refinement.
    _brain_dir = os.environ.get("COS_BRAIN_DIR", str(Path.cwd() / "core/thinking_os"))
    if _brain_dir not in sys.path:
        sys.path.insert(0, _brain_dir)
    if _persona_override:
        _chain = str(_persona_override)
        if not _chain.startswith("chain:") and "," in _chain:
            _chain = "chain:" + _chain
    else:
        _chain = "chain:analyst,architect,implementer,reviewer"

    (_cos_agent_dir / ".persona").write_text(_chain, encoding="utf-8")
    if _chain.startswith("chain:"):
        _formulas = _chain[len("chain:"):]
        (_cos_agent_dir / ".formulas").write_text(_formulas, encoding="utf-8")

    if _intensity_val:
        (_cos_agent_dir / ".intensity").write_text(str(_intensity_val), encoding="utf-8")

    _intensity_label = f" (intensity: {_intensity_val})" if _intensity_val else ""
    print(f"🧠 Role chain: {_chain}{_intensity_label}")
except Exception:
    pass  # fire-and-forget: never block task-start

print()
PY

# Step 3: Write session-scoped active task marker for enforce-task-start.sh hook
bash "$(dirname "$0")/../hooks/write-state.sh" "${COS_STATE_DIR:-.coding-os}/.task-current" "$RAW_TASK"

# Step 4: Load context
bash "$(dirname "$0")/task-context.sh" "$RAW_TASK"

# Step 5 (Phase C): fire-and-forget sync of docs/tasks/*.md → tasks table.
# Runs in the background so the agent doesn't wait for parsing/embedding.
# Missing rag extras, missing v6 schema, or missing tasks/ dir → silent no-op.
(
  python3 -c "
import os, sys, logging
from pathlib import Path
logger = logging.getLogger('cos.task_start.sync')
try:
    _brain = os.environ.get('COS_BRAIN_DIR')
    if not _brain:
        for _c in ('core/thinking_os', '.coding-os/thinking_os', '.coding-os/thinking_os'):
            if (Path(_c) / 'db.py').exists():
                _brain = _c
                break
    if _brain:
        sys.path.insert(0, _brain)
    from db import init_db
    from task_sync import sync_tasks
    conn = init_db(os.environ.get('COS_DB_PATH'))
    sync_tasks(conn, project_root=Path.cwd())
    conn.close()
except Exception as exc:
    logger.debug('task-start sync_safe failed: %s', exc)
" > /dev/null 2>&1 &
)
