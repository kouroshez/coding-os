"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

The `ready` label and its Definition-of-Ready gate: the label patch on the task
file, the DoR evaluation reused from the icebox→in_progress validator, and the
`cos_task_ready` tool itself.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path

from board_os.config import (
    READY_LABEL,
)
from board_os.sync import sync_one
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_shared import (
    _project_root,
)

# ---------- cos_task_ready ----------


def _labels_list_from_json(raw: object) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x) for x in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [t.strip() for t in raw.split(",") if t.strip()]
        if isinstance(parsed, list):
            return [str(x) for x in parsed]
    return []


def _patch_labels_line(file_path: Path, labels: list[str]) -> None:
    content = file_path.read_text(encoding="utf-8")
    flow = "[" + ", ".join(labels) + "]"
    fm_re = re.compile(r"^(---\s*\n.*?\n---\s*\n)", re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{file_path}: no frontmatter to patch")
    head = m.group(1)
    label_re = re.compile(r"^labels:.*$", re.MULTILINE)
    if label_re.search(head):
        new_head = label_re.sub(f"labels: {flow}", head, count=1)
    else:
        new_head = head.replace("---\n", f"---\nlabels: {flow}\n", 1)
    new_content = new_head + content[m.end() :]
    tmp = file_path.with_suffix(file_path.suffix + ".tmp")
    tmp.write_text(new_content, encoding="utf-8")
    os.replace(tmp, file_path)


def _ready_dor_check(
    file_path: Path,
    agent_session: str | None,
) -> tuple[list[dict[str, str]], str | None]:
    from board_os.transition_gates import GatesConfigError, load_gates_config
    from board_os.transition_gates_validator import evaluate_dor, evaluate_override
    from board_os.workflow import _extract_kind_from_frontmatter

    try:
        body = file_path.read_text(encoding="utf-8")
        kind = _extract_kind_from_frontmatter(body) or "feature"
        config = load_gates_config()
        result = evaluate_dor(kind, body, config)
    except (GatesConfigError, OSError, ValueError) as exc:
        return [{"code": "DOR_CHECK_SKIPPED", "severity": "warn", "message": str(exc)}], None

    gaps = [
        {"code": m.code, "severity": m.severity.value, "message": m.message}
        for m in result.messages
    ]
    # Warn-default: surface gaps but still let the label land. Block only when
    # the operator opted into COS_READY_DOR=strict AND the DoR actually fails.
    if not result.blocked or os.environ.get("COS_READY_DOR") != "strict":
        return gaps, None

    if os.environ.get("COS_DOR_OVERRIDE") == "1":
        override_result, _request = evaluate_override(
            "dor",
            reason=os.environ.get("COS_OVERRIDE_REASON"),
            actor=os.environ.get("COS_AGENT") or agent_session,
            config=config,
        )
        if not override_result.blocked:
            return gaps, None  # override accepted — proceed, gaps stay advisory
        rejected = "; ".join(m.message for m in override_result.messages)
        summary = "; ".join(f"[{g['code']}] {g['message']}" for g in gaps)
        return gaps, f"DoR not met and override rejected: {summary} | {rejected}"

    summary = "; ".join(f"[{g['code']}] {g['message']}" for g in gaps)
    return gaps, (
        f"ready refused — Definition of Ready not met: {summary}. "
        "Fix the task body, unset COS_READY_DOR, or set "
        "COS_DOR_OVERRIDE=1 with a COS_OVERRIDE_REASON."
    )


@safe_tool
def cos_task_ready(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    ready: bool = True,
    agent_session: str | None = None,
) -> str:
    """Add or remove the 'ready' label that gates icebox→in_progress."""
    row = conn.execute(
        "SELECT status, file_path, labels_json FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    labels = _labels_list_from_json(row[2])
    has_ready = READY_LABEL in labels
    if ready == has_ready:
        return ok(
            {
                "task_id": task_id,
                "ready": ready,
                "labels": labels,
                "warnings": [
                    f"no-op (label '{READY_LABEL}' already {'set' if ready else 'absent'})"
                ],
            },
            meta={"layer": "tasks", "source": "board_os.cos_task_ready"},
        )

    project_root = _project_root()
    rel_path = row[1]
    file_path = project_root / rel_path if rel_path else None

    # DoR surfacing (TASK-258): reuse the icebox→in_progress validator so a
    # task can't be silently labeled ready while incomplete. Runs BEFORE the
    # label mutation so a strict-mode refusal leaves no half-applied change.
    dor_gaps: list[dict[str, str]] = []
    if ready and file_path is not None and file_path.exists():
        dor_gaps, block_reason = _ready_dor_check(file_path, agent_session)
        if block_reason is not None:
            return fail("validation", block_reason)

    if ready:
        labels.append(READY_LABEL)
    else:
        labels = [lbl for lbl in labels if lbl != READY_LABEL]

    if file_path is not None and file_path.exists():
        try:
            _patch_labels_line(file_path, labels)
        except (OSError, ValueError) as exc:
            return fail("validation", f"labels patch failed: {exc}")
        sync_one(conn, file_path, project_root=project_root)
    else:
        conn.execute(
            "UPDATE tasks SET labels_json = ? WHERE task_id = ?",
            (json.dumps(labels), task_id),
        )
        conn.commit()

    data: dict[str, object] = {
        "task_id": task_id,
        "ready": ready,
        "labels": labels,
        "status": str(row[0]),
    }
    if dor_gaps:
        data["dor"] = dor_gaps
    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_ready"})
