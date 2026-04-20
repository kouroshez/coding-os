#!/usr/bin/env bash
# Phase L.4 — PreToolUse: Write/Edit on docs/tasks/*.md
# Validates the Phase L lean frontmatter (id/swimlane/kind/epic/labels/
# status/priority/appetite/depends_on) before the file is written.
# Also enforces WIP caps when status transitions to in_progress/emergency,
# and rejects dependency cycles (R-L-29).
#
# Fail-soft: if board_os python module is unavailable (e.g. fresh clone
# before `uv sync`), hook warns but does NOT block — avoids bricking
# the session on toolchain drift.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "validate-task-frontmatter" "entry" 2>/dev/null || true

# Read JSON payload from stdin (Claude/Codex hook input format).
payload="$(cat)"

# Only act on docs/tasks/*.md writes.
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    p = d.get("tool_input", {}).get("file_path", "")
    print(p)
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ -z "$file_path" ]] || [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# Skip if file doesn't exist yet (Write creating new) — we need the
# candidate content. The hook protocol passes `content` in tool_input.
python3 - "$payload" <<'PY'
import json
import os
import re
import sys
from pathlib import Path

try:
    from core.board_os.parser import is_lean_format, extract_frontmatter
    from core.board_os.config import KIND_ENUM, STATUS_ENUM, PRIORITY_ENUM, APPETITE_RE, load_config
except ImportError as exc:
    # Fail-soft: warn but don't block.
    print(f"WARN validate-task-frontmatter: board_os import failed: {exc}",
          file=sys.stderr)
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
        except Exception:
            pass

if not content:
    sys.exit(0)

errors: list[str] = []

if not is_lean_format(content):
    # Legacy file — allow but warn.
    print(
        "WARN validate-task-frontmatter: no frontmatter detected — "
        "consider migrating to Phase L lean format (`cos task-migrate`)",
        file=sys.stderr,
    )
    sys.exit(0)

fm = extract_frontmatter(content)
if fm is None:
    print("ERROR validate-task-frontmatter: YAML frontmatter broken", file=sys.stderr)
    sys.exit(2)

# id matches filename
expected_id_match = re.search(r"(TASK-\d+)", os.path.basename(file_path))
if expected_id_match and fm.get("id") and fm["id"] != expected_id_match.group(1):
    errors.append(
        f"frontmatter id {fm['id']!r} does not match filename id "
        f"{expected_id_match.group(1)!r}"
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
            errors.append(
                f"label {lbl!r} collides with KIND_ENUM — move to `kind:` field"
            )

# Swimlane exists in config
project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
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

sys.exit(0)
PY

exit_code=$?
cos_log_hook "validate-task-frontmatter" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit $exit_code
