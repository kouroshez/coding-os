#!/usr/bin/env bash
# Mark a task as done: update docs/tasks.md, write structured entry to changes.log.
# Usage: task-done.sh <TASK> <TYPE> <MSG> <WHAT> <FILES> [OUTCOME]
set -euo pipefail
source "$(dirname "$0")/_lib.sh"
source "$(dirname "$0")/../hooks/cos-env.sh" 2>/dev/null || true

if [ "${1:-}" = "--help" ] || [ "${1:-}" = "-h" ]; then
  echo "Usage: $0 <TASK> <TYPE> <MSG> <WHAT> <FILES> [OUTCOME]"
  echo ""
  echo "Mark a task as done and log the change. Always provide WHAT and FILES."
  echo ""
  echo "Arguments:"
  echo "  TASK     Task number or ID (e.g. 14, 014, TASK-14, TASK-014)"
  echo "  TYPE     One of: feat, fix, refactor, docs, test, infra"
  echo "  MSG      Title summary (max 80 chars, quoted)"
  echo "  WHAT     Impact description (optional, max 120 chars)"
  echo "  FILES    Key files changed (optional, max 120 chars)"
  echo "  OUTCOME  One of: success, rework, partial, blocked (default: success)"
  echo ""
  echo "Steps performed:"
  echo "  1. Validate task exists and is open or in-progress"
  echo "  2. Change checkbox to [x] in docs/tasks.md"
  echo "  3. Write structured entry to changes.log (1-4 lines)"
  echo "  4. Record outcome to coding-os.db (if DB exists)"
  echo ""
  echo "Log format:"
  echo "  - TASK-###: <type> — <title>"
  echo "    What: <impact>"
  echo "    Files: <files>"
  echo "    Outcome: <outcome>"
  echo ""
  echo "Example:"
  echo "  make task-done TASK=014 TYPE=fix MSG=\"SSOT restructured\" WHAT=\"8 bugs fixed\" OUTCOME=success"
  exit 0
fi

RAW_TASK="${1:-${TASK:-}}"
TYPE="${2:-${TYPE:-}}"
MSG="${3:-${MSG:-}}"
WHAT="${4:-${WHAT:-}}"
FILES="${5:-${FILES:-}}"
OUTCOME="${6:-${OUTCOME:-success}}"

if [ -z "$RAW_TASK" ] || [ -z "$TYPE" ] || [ -z "$MSG" ]; then
  echo "Usage: $0 <TASK> <TYPE> <MSG> <WHAT> <FILES> [OUTCOME]"
  echo "All arguments recommended. TASK, TYPE, and MSG are required."
  exit 1
fi

# Validate outcome
VALID_OUTCOMES="success rework partial blocked"
if ! echo "$VALID_OUTCOMES" | grep -qw "$OUTCOME"; then
  err "OUTCOME must be one of: $VALID_OUTCOMES (got: $OUTCOME)"
fi

# Validate type
VALID_TYPES="feat fix refactor docs test infra"
if ! echo "$VALID_TYPES" | grep -qw "$TYPE"; then
  err "TYPE must be one of: $VALID_TYPES"
fi

# Validate lengths
if [ "${#MSG}" -gt 80 ]; then
  err "MSG must be 80 chars or fewer (got ${#MSG})"
fi
if [ -n "$WHAT" ] && [ "${#WHAT}" -gt 120 ]; then
  err "WHAT must be 120 chars or fewer (got ${#WHAT})"
fi

echo "=== task-done ==="

python3 - "$RAW_TASK" "$TYPE" "$MSG" "$WHAT" "$FILES" "$OUTCOME" <<'PY'
import os
from pathlib import Path
from datetime import date
import re
import sys

raw_task, entry_type, msg, what, files, outcome = sys.argv[1:7]

match = re.fullmatch(r"(?:TASK-?)?(\d+)", raw_task)
if not match:
    raise SystemExit("ERROR: Invalid task format. Use: 14, 014, TASK-14, or TASK-014")

task_num = int(match.group(1))
padded = f"{task_num:03d}"
task_id = f"TASK-{padded}"
today = date.today().isoformat()

# --- Update docs/tasks.md ---
index_path = Path("docs/tasks.md")
if not index_path.exists():
    raise SystemExit(f"ERROR: Task list not found: {index_path}")

index_text = index_path.read_text()
lines = index_text.splitlines()

task_line_idx = None
# Match only task index lines (- [ ] TASK-###: or - [/] TASK-###: or - [x] TASK-###:)
# Avoids false match on "depends: TASK-###" in other task descriptions
task_pattern = re.compile(rf"^- \[.\] {re.escape(task_id)}:")
for i, line in enumerate(lines):
    if task_pattern.match(line.strip()):
        task_line_idx = i
        break

if task_line_idx is None:
    raise SystemExit(f"ERROR: {task_id} not found in {index_path}")

task_line = lines[task_line_idx].strip()

if task_line.startswith("- [x]"):
    print(f"{task_id} is already done.")
    sys.exit(0)
if task_line.startswith("- (BLOCKED:"):
    reason = re.search(r"\(BLOCKED:\s*(.+?)\)", task_line)
    reason_text = reason.group(1) if reason else "unknown"
    raise SystemExit(f"ERROR: {task_id} is BLOCKED: {reason_text}. Unblock before marking done.")

old_line = lines[task_line_idx]
if "- [/]" in old_line:
    new_line = old_line.replace("- [/]", "- [x]", 1)
elif "- [ ]" in old_line:
    print(f"WARN: {task_id} was never started ([/]). Transitioning [ ] → [x] directly.", file=sys.stderr)
    print(f"  Consider using 'make task-start TASK={task_num}' before task-done.", file=sys.stderr)
    new_line = old_line.replace("- [ ]", "- [x]", 1)
else:
    raise SystemExit(f"ERROR: Cannot parse checkbox in: {old_line}")

lines[task_line_idx] = new_line
index_path.write_text("\n".join(lines) + "\n")
print(f"Marked {task_id} as [x] done in docs/tasks.md")

# --- Update changes.log (structured format) ---
log_path = Path("changes.log")
if log_path.exists():
    log_text = log_path.read_text()
else:
    log_text = "# Project Change Log\n"

date_header = f"## {today}"
if date_header not in log_text:
    first_newline = log_text.find("\n")
    if first_newline == -1:
        log_text += f"\n\n{date_header}\n\n"
    else:
        log_text = log_text[:first_newline + 1] + f"\n{date_header}\n\n" + log_text[first_newline + 1:]

# Build structured entry (1-4 lines)
entry = f"- {task_id}: {entry_type} — {msg}"
if what:
    entry += f"\n  What: {what}"
if files:
    entry += f"\n  Files: {files}"
if outcome:
    entry += f"\n  Outcome: {outcome}"

date_pos = log_text.find(date_header)
insert_pos = date_pos + len(date_header)
# Skip exactly one newline after date header, then insert
if insert_pos < len(log_text) and log_text[insert_pos] == "\n":
    insert_pos += 1
log_text = log_text[:insert_pos] + "\n" + entry + "\n" + log_text[insert_pos:]

log_path.write_text(log_text)
print(f"Logged: {entry}")

title_match = re.search(rf"{re.escape(task_id)}:\s*(.+)$", new_line)
title = title_match.group(1).strip() if title_match else task_id
print(f"\nDone: {task_id} — {title}")

# --- Record outcome to coding-os.db + breakthrough detection ---
# Resolve thinking_os dir in this order: explicit COS_BRAIN_DIR →
# meta-project layout (core/thinking_os/) → consumer-project installed
# layout (.coding-os/thinking_os/) → pre-rename legacy layout.
_brain_candidates = [
    Path(os.environ["COS_BRAIN_DIR"]) if os.environ.get("COS_BRAIN_DIR") else None,
    Path("core/thinking_os"),
    Path(".coding-os/thinking_os"),
    Path(".coding-os/thinking_os"),
]
record_script = None
for _cand in _brain_candidates:
    if _cand is None:
        continue
    _p = _cand / "record_outcome.py"
    if _p.exists():
        record_script = _p
        break
if record_script is not None:
    import subprocess
    try:
        subprocess.run(
            [sys.executable, str(record_script),
             "--task", task_id, "--type", entry_type, "--outcome", outcome,
             "--msg", msg],
            timeout=3, capture_output=True,
        )
    except Exception:
        pass  # non-blocking

    # Phase G.8: back-fill outcome on every retrieval row that supported
    # this task. Fire-and-forget — pre-v10 DBs silently no-op.
    _db_path = Path(os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db"))
    if _db_path.exists():
        try:
            import sqlite3 as _sq_bf
            _bf_conn = _sq_bf.connect(str(_db_path), timeout=2)
            _bf_conn.execute(
                "UPDATE retrievals SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
                "WHERE task_id = ? AND outcome IS NULL",
                (outcome, task_id),
            )
            _bf_conn.commit()
            _bf_conn.close()
        except Exception:
            pass  # fire-and-forget

    # Check for breakthrough after recording
    _db = Path(os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db"))
    if _db.exists() and outcome == "success":
        try:
            import sqlite3 as _sq
            _c = _sq.connect(str(_db), timeout=2)
            _bt = _c.execute(
                "SELECT previous_outcome FROM outcome_history "
                "WHERE task_id = ? AND is_breakthrough = 1 "
                "ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if _bt:
                print(f"\n🧠 Breakthrough detected! {task_id}: {_bt[0]} → success")
                print("   Call cos_learn_narrative to record what you learned:")
                print(f'   - what_failed: "approaches that didn\'t work"')
                print(f'   - what_worked: "the solution"')
                print(f'   - key_insight: "reusable lesson"')
            _c.close()
        except Exception:
            pass

# --- Auto learn_extract every 10 tasks (fire-and-forget) ---
db_path = Path(os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db"))
if db_path.exists():
    try:
        import sqlite3
        _conn = sqlite3.connect(str(db_path), timeout=2)
        _conn.row_factory = sqlite3.Row
        _count = _conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if _count > 0 and _count % 10 == 0:
            # __file__ isn't defined for heredoc stdin scripts — resolve from
            # COS_BRAIN_DIR first, then the known meta/consumer layouts.
            _learn_brain = os.environ.get("COS_BRAIN_DIR")
            if not _learn_brain:
                for _cand in ("core/thinking_os", ".coding-os/thinking_os", ".coding-os/thinking_os"):
                    if (Path(_cand) / "tools" / "learning.py").exists():
                        _learn_brain = _cand
                        break
            if _learn_brain:
                sys.path.insert(0, _learn_brain)
            from tools.learning import learn_extract
            result = learn_extract(_conn)
            extracted = result.get("extracted", [])
            if extracted:
                print(f"\n🧠 Learning: discovered {len(extracted)} pattern(s) from {_count} outcomes:")
                for p in extracted:
                    print(f"   • {p['pattern']} (confidence: {p['confidence']:.2f})")
            else:
                print(f"\n🧠 Learning: analyzed {_count} outcomes, no new patterns.")
        _conn.close()
    except Exception:
        pass  # fire-and-forget: never block task-done
PY

# Phase C: fast-path status sync — updates only the `status` column in the
# tasks table from docs/tasks.md. Full re-parse/re-embed isn't needed here
# because task-done only flips a status marker in the index.
(
  python3 -c "
import os, sys, logging
from pathlib import Path
logger = logging.getLogger('cos.task_done.status_sync')
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
    from task_sync import sync_status_only
    conn = init_db(os.environ.get('COS_DB_PATH'))
    sync_status_only(conn, project_root=Path.cwd())
    conn.close()
except Exception as exc:
    logger.debug('status_sync_safe failed: %s', exc)
" > /dev/null 2>&1 &
)

# Phase G.10 — refresh the rolling Agent Digest so the next session starts
# with the updated identity/beliefs snapshot. Fire-and-forget, bounded at
# 2s so a slow DB never holds up task completion.
(
  COS_DB_PATH="${COS_DB_PATH:-.coding-os/coding-os.db}" \
  timeout 2 python3 -c "
import os, sys, logging
from pathlib import Path
logger = logging.getLogger('cos.task_done.digest')
try:
    _brain = os.environ.get('COS_BRAIN_DIR')
    if not _brain:
        for _c in ('core/thinking_os', '.coding-os/thinking_os', '.coding-os/thinking_os'):
            if (Path(_c) / 'digest.py').exists():
                _brain = _c
                break
    if _brain:
        sys.path.insert(0, _brain)
    from db import init_db
    from digest import regenerate
    conn = init_db(os.environ.get('COS_DB_PATH'))
    regenerate(conn, project_root=Path.cwd())
    conn.close()
except Exception as exc:
    logger.debug('digest_safe failed: %s', exc)
" > /dev/null 2>&1 &
)
