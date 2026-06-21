import json
import os
import re
import sys
from pathlib import Path

try:
    from board_os.config import APPETITE_RE, KIND_ENUM, PRIORITY_ENUM, STATUS_ENUM, load_config
    from board_os.parser import extract_frontmatter, is_lean_format
except ImportError as exc:
    # Fail-soft: warn but don't block.
    print(f"WARN validate-task-frontmatter: board_os import failed: {exc}", file=sys.stderr)
    sys.exit(0)

try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

tool_input = data.get("tool_input", {})
content = tool_input.get("content") or tool_input.get("new_string") or ""
file_path = tool_input.get("file_path", "")

# For Edit, we need the final content, not just the new_string. Read
# the existing file and replace old_string with new_string if present.
if "new_string" in tool_input and "old_string" in tool_input:
    p = Path(file_path)
    if p.exists():
        try:
            old_content = p.read_text(encoding="utf-8")
            content = old_content.replace(tool_input["old_string"], tool_input["new_string"])
        except Exception as exc:  # fail-open: log + continue (Rule 6)
            print(f"validate_task_frontmatter: simulate-edit failed: {exc}", file=sys.stderr)

if not content:
    sys.exit(0)

errors: list[str] = []

if not is_lean_format(content):
    # Legacy file — allow but warn.
    print(
        "WARN validate-task-frontmatter: no frontmatter detected — "
        "consider migrating to the lean format (`cos task-migrate`)",
        file=sys.stderr,
    )
    sys.exit(0)

fm = extract_frontmatter(content)
if fm is None:
    print("ERROR validate-task-frontmatter: YAML frontmatter broken", file=sys.stderr)
    sys.exit(2)

# id matches filename
expected_id_match = re.search(r"(TASK-(?:[A-Z][A-Z0-9]*-)?\d+)", os.path.basename(file_path))
if expected_id_match and fm.get("id") and fm["id"] != expected_id_match.group(1):
    errors.append(
        f"frontmatter id {fm['id']!r} does not match filename id {expected_id_match.group(1)!r}"
    )

# Enum checks
if fm.get("status") and fm["status"] not in STATUS_ENUM:
    errors.append(f"status {fm['status']!r} not in {sorted(STATUS_ENUM)}")
if fm.get("kind") and fm["kind"] not in KIND_ENUM:
    errors.append(f"kind {fm['kind']!r} not in {sorted(KIND_ENUM)}")
if fm.get("priority") and fm["priority"] not in PRIORITY_ENUM:
    errors.append(f"priority {fm['priority']!r} not in {sorted(PRIORITY_ENUM)}")
appetite = fm.get("appetite")
if appetite and not APPETITE_RE.match(str(appetite)):
    errors.append(f"appetite {appetite!r} must match shape '30m', '1h', '1d', '1w', '1cy'")

# labels ∩ kind_enum = ∅
labels = fm.get("labels") or []
if isinstance(labels, list):
    for lbl in labels:
        if isinstance(lbl, str) and lbl in KIND_ENUM:
            errors.append(f"label {lbl!r} collides with KIND_ENUM — move to `kind:` field")

# Swimlane exists in config
from _paths import resolve_project_root

project_root = resolve_project_root()
try:
    config = load_config(project_root)
except (FileNotFoundError, Exception):
    config = None
if config is not None and fm.get("swimlane"):
    if fm["swimlane"] not in config.swimlane_ids:
        errors.append(
            f"swimlane {fm['swimlane']!r} not in scrumban-config.yaml; "
            f"valid: {sorted(config.swimlane_ids)}"
        )

if errors:
    print("ERROR validate-task-frontmatter:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    sys.exit(2)
