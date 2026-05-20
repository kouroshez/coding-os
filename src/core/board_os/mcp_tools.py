"""board_os MCP tools — Phase L.3 surface (`cos_task_*`).

Implements board MCP tools (Phase L), including:
    cos_task_create, cos_task_board, cos_task_move, cos_task_reposition,
    cos_task_pick, cos_task_daily, cos_task_retro, cos_task_wip_check,
    cos_work_log_append

All tools use the shared ok()/fail()/@safe_tool envelope (Rule 14).
They are registered into the MCP server in
`core/thinking_os/server.py` via the `register_board_tools(mcp, conn)`
helper at the bottom of this module.

Stateless from the caller's perspective:
- Open one connection per call (via the server's connection factory),
- call the underlying board_os primitives (config.load_config,
  parser.parse_task, sync.sync_one, workflow.transition),
- shape the response into ok()/fail() with token-budgeted meta.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    STATUS_ENUM,
    load_config,
)
from board_os.parser import parse_task
from board_os.sync import sync_one
from board_os.workflow import (
    check_wip,
    patch_task_frontmatter_scalars,
    transition,
    validate_dependencies_no_cycle,
)
from thinking_os.tools._shared import fail, ok, safe_tool

logger = logging.getLogger("coding_os.board_os.mcp_tools")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------- Internal helpers ----------


def _project_root() -> Path:
    """Resolve the project root. Prefers cwd; falls back to repo root."""
    return Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()


def _current_config():
    try:
        return load_config(_project_root())
    except FileNotFoundError:
        return None


def _slugify(title: str, *, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


def _next_task_id(conn: sqlite3.Connection, project_root: Path) -> str:
    # DB is authoritative for synced tasks; filesystem catches unsynced files.
    # Taking max of both eliminates the window where two agents both read the
    # same filesystem max before either writes, each computing the same ID.
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(task_id, 6) AS INTEGER)) FROM tasks "
        "WHERE task_id LIKE 'TASK-%' AND SUBSTR(task_id, 6) GLOB '[0-9]*'"
    ).fetchone()
    db_max = int(row[0]) if row and row[0] is not None else 0

    tasks_dir = project_root / "docs" / "tasks"
    fs_max = 0
    if tasks_dir.exists():
        for p in tasks_dir.glob("TASK-*.md"):
            m = re.match(r"TASK-(\d+)", p.name)
            if m:
                fs_max = max(fs_max, int(m.group(1)))

    next_num = max(db_max, fs_max) + 1
    return f"TASK-{next_num:03d}"


def _render_lean_frontmatter(fields: dict) -> str:
    # Stable key order matches the template.
    order = [
        "id",
        "title",
        "swimlane",
        "kind",
        "epic",
        "labels",
        "status",
        "priority",
        "appetite",
        "created",
        "started",
        "completed",
        "agent_session",
        "depends_on",
        "blocked_by",
        "references",
    ]
    lines = ["---"]
    for key in order:
        if key not in fields:
            continue
        val = fields[key]
        if val is None:
            lines.append(f"{key}: null")
        elif isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                inner = ", ".join(str(v) for v in val)
                lines.append(f"{key}: [{inner}]")
        elif isinstance(val, str):
            lines.append(
                f'{key}: "{val}"' if " " in val or key in {"title", "appetite"} else f"{key}: {val}"
            )
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines)


def _render_kind_aware_body(
    *,
    task_id: str,
    title: str,
    kind: str,
    outcome: str | None,
    read_first_block: str,
) -> str:
    """Render the task body with placeholders that match the kind's DoR.

    Phase L.10 / TASK-110+111. Sections that the kind explicitly opts
    out of (e.g. chore drops Acceptance + Read First) are not emitted,
    so the agent doesn't see prompts for fields that won't be required.

    The DoR rules come from `transition-gates.yaml`; if the config is
    unavailable (loader fails, edge case in fresh install), we fall back
    to the historical full template so we never produce an empty body.
    """
    sections_to_render: dict[str, str] = {}

    try:
        # Lazy import — keeps this module loadable in environments where
        # pydantic/yaml haven't been installed yet (fresh `cos init`).
        from board_os.transition_gates import load_gates_config

        config = load_gates_config()
        rules = config.definition_of_ready.for_kind(kind)
        active_sections = set(rules.sections.keys())
    except Exception:
        active_sections = {"Outcome", "Read First", "Acceptance"}

    # Outcome is always rendered — it's the one universal anchor.
    outcome_line = outcome or _kind_outcome_placeholder(kind)
    sections_to_render["Outcome"] = f"**Outcome (one sentence):** {outcome_line}"

    if "Read First" in active_sections:
        sections_to_render["Read First"] = f"## Read First\n{read_first_block}"

    if "Repro Steps" in active_sections:
        sections_to_render["Repro Steps"] = (
            "## Repro Steps\n"
            "1. (fill in: exact steps to reproduce)\n"
            "2. ...\n"
            "Expected: ...\n"
            "Actual: ..."
        )

    if "Threat Model" in active_sections:
        sections_to_render["Threat Model"] = (
            "## Threat Model\n(fill in: attacker, asset, attack vector, mitigation)"
        )

    if "Acceptance" in active_sections:
        sections_to_render["Acceptance"] = (
            "## Acceptance (G/W/T) — *this IS the Definition of Done*\n"
            "- **Given** ...\n- **When** ...\n- **Then** ..."
        )

    sections_to_render["Work Log"] = "## Work Log"

    body_parts = [f"\n\n# {task_id}: {title}", ""]
    # Stable ordering: Outcome → Read First → Repro Steps → Threat Model →
    # Acceptance → Work Log. Mirrors the natural read order.
    order = ["Outcome", "Read First", "Repro Steps", "Threat Model", "Acceptance", "Work Log"]
    for name in order:
        if name in sections_to_render:
            body_parts.append(sections_to_render[name])
            body_parts.append("")
    return "\n".join(body_parts)


def _kind_outcome_placeholder(kind: str) -> str:
    """Outcome placeholder text tuned to the kind so the agent sees an
    example shaped like the kind's expected content."""
    by_kind = {
        "feature": "(fill in: one-sentence measurable outcome — e.g. 'Add OAuth login that issues 24h JWTs.')",
        "bug": "(fill in: one-sentence outcome — e.g. 'Stop double-charging users on retry of failed payments.')",
        "chore": "(fill in: one-sentence outcome — e.g. 'Bump dependency X to v2.3 for security patch.')",
        "spike": "(fill in: one-sentence question — e.g. 'Investigate whether kuzu can replace sqlite for graph layer.')",
        "docs": "(fill in: one-sentence outcome — e.g. 'Document the override-audit policy in docs/governance/.')",
        "refactor": "(fill in: one-sentence outcome — e.g. 'Extract retry logic into a shared decorator with backoff.')",
        "test": "(fill in: one-sentence outcome — e.g. 'Cover the OAuth refresh-token edge case at integration level.')",
        "security": "(fill in: one-sentence outcome — e.g. 'Rotate all signing keys and tighten cookie SameSite.')",
    }
    return by_kind.get(kind, "(fill in: one-sentence measurable outcome)")


def _next_steps_for_kind(kind: str) -> dict:
    """Return the structured next-steps payload for cos_task_create.

    Phase L.10 / TASK-110. Mirrors the active DoR rules so the agent
    sees exactly what to fill before `cos task-start TASK-NN`.
    """
    try:
        from board_os.transition_gates import load_gates_config

        config = load_gates_config()
        rules = config.definition_of_ready.for_kind(kind)
    except Exception:
        return {
            "kind": kind,
            "required_for_in_progress": [],
            "command_after_fill": None,
        }

    required: list[dict] = []
    for name, rule in rules.sections.items():
        if rule is None:
            continue
        spec: dict = {"section": name, "required": rule.required}
        if rule.min_chars:
            spec["min_chars"] = rule.min_chars
        if rule.min_items:
            spec["min_items"] = rule.min_items
        if rule.required_subitems:
            spec["required_subitems"] = list(rule.required_subitems)
        if rule.forbid_substrings:
            spec["forbid_substrings"] = list(rule.forbid_substrings)
        required.append(spec)
    return {
        "kind": kind,
        "required_for_in_progress": required,
        "command_after_fill": "cos task-start <TASK-ID>",
        "preview_command": "cos task-validate <TASK-ID>",
    }


def _task_card(row: sqlite3.Row | tuple) -> dict:
    """Shape a DB row into a board card."""
    return {
        "id": row[0],
        "title": row[1],
        "swimlane": row[2] or "",
        "kind": row[3] or "",
        "epic": row[4],
        "labels": json.loads(row[5] or "[]"),
        "status": row[6],
        "priority": row[7] or "P2",
        "appetite": row[8] or "1d",
        "agent_session": row[9],
        "last_log_line": _last_log_line(row[10]),
    }


def _last_log_line(work_log_json: str | None) -> str | None:
    if not work_log_json:
        return None
    try:
        lines = json.loads(work_log_json)
    except json.JSONDecodeError:
        return None
    return lines[-1] if lines else None


def _agent_label(agent_session: str | None) -> str:
    """Normalize work-log actor label to a readable agent name.

    Detection logic lives in ``core.board_os._agent_runtime.detect_agent``
    so cli/board_commands.py and this module share one code path (Wave 0
    audit fix E2). The shell counterpart is core/hooks/cos-env.sh.
    """
    from ._agent_runtime import detect_agent

    return detect_agent(agent_session)


def _resolve_attribution(agent_session: str | None) -> str | None:
    """Auto-fill agent_session for board mutators when caller passes None.

    Without this, ``task_status_history.agent_session`` lands as NULL
    and the board UI renders the green ``H`` glyph (human) for tasks
    that were actually created by an MCP-driven agent. The resolver
    reads ``$COS_SESSION_FILE`` (populated by every adapter via
    ``core/hooks/session-context.sh``) so the fix is adapter-agnostic.
    """
    from ._agent_runtime import resolve_agent_session

    return resolve_agent_session(agent_session)


_BOARD_SELECT = (
    "SELECT task_id, title, swimlane, kind, epic, labels_json, "
    "       status, priority, appetite, agent_session, work_log_last_5, "
    "       started_at, completed_at "
    "FROM tasks"
)


# ---------- cos_task_create ----------


@safe_tool
def cos_task_create(
    conn: sqlite3.Connection,
    *,
    title: str,
    swimlane: str,
    kind: str,
    priority: str = "P2",
    appetite: str = "1d",
    epic: str | None = None,
    labels: list[str] | None = None,
    outcome: str | None = None,
    read_first: list[str] | None = None,
    depends_on: list[str] | None = None,
    status: str = "icebox",
    agent_session: str | None = None,
) -> str:
    """Create a new task MD file + sync into DB. Returns envelope."""
    config = _current_config()
    if config is not None and swimlane not in config.swimlane_ids:
        return fail(
            "validation",
            f"swimlane {swimlane!r} not in config; valid: {sorted(config.swimlane_ids)}",
        )
    if kind not in KIND_ENUM:
        return fail("validation", f"kind {kind!r} not in {sorted(KIND_ENUM)}")
    if priority not in PRIORITY_ENUM:
        return fail("validation", f"priority {priority!r} not in {sorted(PRIORITY_ENUM)}")
    if not APPETITE_RE.match(appetite):
        return fail("validation", f"appetite {appetite!r} bad shape")
    if status not in STATUS_ENUM:
        return fail("validation", f"status {status!r} not in {sorted(STATUS_ENUM)}")

    labels = labels or []
    for lbl in labels:
        if lbl in KIND_ENUM:
            return fail(
                "validation",
                f"label {lbl!r} collides with KIND_ENUM — use kind, not labels",
            )

    # Auto-attribute the create event to the running agent's session
    # when the caller didn't pass one. Skipping this leaves NULL in
    # task_status_history.agent_session, which the board UI maps to
    # the green "H" glyph — making MCP-driven creates look human-led.
    agent_session = _resolve_attribution(agent_session)

    project_root = _project_root()
    tasks_dir = project_root / "docs" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)

    task_id = _next_task_id(conn, project_root)
    slug = _slugify(title)
    file_path = tasks_dir / f"{task_id}-{slug}.md"
    if file_path.exists():
        return fail("validation", f"file already exists: {file_path.name}")

    today = datetime.utcnow().strftime("%Y-%m-%d")
    fm = {
        "id": task_id,
        "title": title,
        "swimlane": swimlane,
        "kind": kind,
        "epic": epic,
        "labels": labels,
        "status": status,
        "priority": priority,
        "appetite": appetite,
        "created": today,
        "started": None,
        "completed": None,
        "agent_session": None,
        "depends_on": depends_on or [],
        "blocked_by": [],
        "references": [],
    }
    frontmatter = _render_lean_frontmatter(fm)

    rf_lines = "\n".join(f"- {p}" for p in (read_first or ["(no doc yet — exploratory)"]))
    body = _render_kind_aware_body(
        task_id=task_id,
        title=title,
        kind=kind,
        outcome=outcome,
        read_first_block=rf_lines,
    )
    file_path.write_text(frontmatter + body, encoding="utf-8")

    sync_one(conn, file_path, project_root=project_root)

    # Emit a canonical creation event into task_status_history so the
    # live-agents panel and retro queries can attribute WHO created the
    # task and WHEN.  Shape: old_status=NULL signals "created" to the
    # stream renderer (see core/web/ui/.../useBoardStream.ts).  Any
    # sqlite error here must NOT fail the create — the task is already
    # on disk + synced; history is an audit signal, not a gate.
    try:
        import time as _time

        # old_status uses '' (empty string) as the "nothing to transition
        # from" sentinel — the task_status_history.old_status column is
        # NOT NULL (migration v13 schema).  The stream renderer normalises
        # '' back to null/creation in both history + SSE paths so the UI
        # distinguishes "create" from "move" without a schema migration.
        conn.execute(
            """
            INSERT INTO task_status_history
                (task_id, old_status, new_status, agent_session,
                 reason, transitioned_at)
            VALUES (?, '', ?, ?, ?, ?)
            """,
            (task_id, status, agent_session, "created", int(_time.time())),
        )
        conn.commit()
    except sqlite3.Error as exc:
        import logging as _logging

        _logging.getLogger("coding_os.board_os").debug(
            "create-history insert failed for %s: %s",
            task_id,
            exc,
        )
        # Also persist the agent session onto the tasks row so the UI
        # can still attribute this task even without a history row.
        try:
            conn.execute(
                "UPDATE tasks SET agent_session = COALESCE(?, agent_session) WHERE task_id = ?",
                (agent_session, task_id),
            )
            conn.commit()
        except sqlite3.Error as exc2:
            _logging.getLogger("coding_os.board_os").debug(
                "create-history agent_session fallback failed: %s",
                exc2,
            )
    else:
        # History row landed; also stamp the tasks row so board_list can
        # render the creator badge without re-joining history.
        try:
            conn.execute(
                "UPDATE tasks SET agent_session = COALESCE(?, agent_session) WHERE task_id = ?",
                (agent_session, task_id),
            )
            conn.commit()
        except sqlite3.Error as exc_stamp:
            import logging as _logging

            _logging.getLogger("coding_os.board_os").debug(
                "create stamp on tasks.agent_session failed: %s",
                exc_stamp,
            )

    return ok(
        {
            "task_id": task_id,
            "file_path": str(file_path.relative_to(project_root)),
            "swimlane": swimlane,
            "kind": kind,
            "status": status,
            "next_steps": _next_steps_for_kind(kind),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_create"},
    )


# ---------- cos_task_board ----------


@safe_tool
def cos_task_board(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    kind: str | None = None,
    epic: str | None = None,
    status_filter: list[str] | None = None,
    include_archive: bool = False,
    limit: int = 50,
) -> str:
    config = _current_config()
    clauses: list[str] = []
    params: list = []
    if swimlane:
        clauses.append("swimlane = ?")
        params.append(swimlane)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if epic:
        clauses.append("epic = ?")
        params.append(epic)
    if status_filter:
        placeholders = ",".join("?" for _ in status_filter)
        clauses.append(f"status IN ({placeholders})")
        params.extend(status_filter)
    elif not include_archive:
        clauses.append("status != 'archive'")
        clauses.append("status != 'complete'")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"{_BOARD_SELECT} {where} ORDER BY swimlane, status, priority LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    cards = [_task_card(r) for r in rows]

    # Group by (swimlane, status) for UX.
    grouped: dict[str, dict[str, list[dict]]] = {}
    for card in cards:
        lane = card["swimlane"] or "(none)"
        grouped.setdefault(lane, {}).setdefault(card["status"], []).append(card)

    wip_state = None
    if config is not None:
        state = check_wip(conn, config)
        wip_state = {
            "counts": state.counts,
            "caps": state.caps,
            "violations": list(state.violations),
        }

    return ok(
        {
            "grouped": grouped,
            "cards": cards,
            "count": len(cards),
            "wip": wip_state,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_board"},
    )


# ---------- cos_task_move ----------


@safe_tool
def cos_task_move(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    to: str,
    reason: str | None = None,
    bypass_wip: bool = False,
    bypass_gates: bool = False,
    force: bool = False,
    agent_session: str | None = None,
) -> str:
    config = _current_config()

    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    file_path = None
    if row and row[0]:
        candidate = _project_root() / row[0]
        if candidate.exists():
            file_path = candidate

    result = transition(
        conn,
        task_id,
        to,
        reason=reason,
        agent_session=agent_session,
        bypass_wip=bypass_wip,
        bypass_gates=bypass_gates,
        force=force,
        config=config,
        file_path=file_path,
    )
    if not result.ok:
        return fail(result.error_category or "internal", result.error or "transition failed")

    data: dict = {
        "task_id": result.task_id,
        "previous_status": result.previous_status,
        "new_status": result.new_status,
        "warnings": list(result.warnings),
        "wip": result.wip_state,
    }
    if result.new_status == "complete":
        hint = _reviewer_hint_if_required(task_id)
        if hint is not None:
            data["reviewer_check_required"] = True
            data["reviewer_hint"] = hint

    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_move"})


def _reviewer_hint_if_required(task_id: str) -> dict | None:
    """Build a reviewer-subagent hint when the agent should auto-spawn one.

    Returns None when the conditions for an auto-reviewer don't hold —
    no exhaustive intent in the active prompt, or no active audit
    artifact bound to this task. When all conditions hold, returns a
    dict the main agent passes to Agent(subagent_type="Explore", ...).
    """
    intent = _read_intent_safe()
    if not intent or not intent.get("exhaustive"):
        return None

    audit_path = _active_audit_for_task(task_id)
    if audit_path is None:
        return None

    predicates = intent.get("predicates") or []
    template_path = "docs/_meta/reviewer-subagent-prompt.md"
    return {
        "subagent_type": "Explore",
        "description": f"Independent reviewer for {task_id} audit",
        "prompt_template": template_path,
        "substitutions": {
            "TASK_ID": task_id,
            "AUDIT_FILE": str(audit_path),
            "PREDICATES": predicates,
        },
        "expected_output_schema": "ExhaustiveEvidence.reviewer_check",
        "post_action": (
            "Submit reviewer findings via cos_supervise_record_output "
            "(formula_id='exhaustive_evidence') with reviewer_check set "
            "to 'pass' or 'fail'."
        ),
    }


def _read_intent_safe() -> dict | None:
    base = os.environ.get("COS_AGENT_DIR")
    if not base:
        state = os.environ.get("COS_STATE_DIR") or ".coding-os"
        agent = os.environ.get("COS_AGENT") or "claude"
        base = str(Path(state) / agent)
    intent_path = Path(base) / ".intent.json"
    if not intent_path.exists():
        return None
    try:
        return json.loads(intent_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("intent read failed: %s", exc)
        return None


def _active_audit_for_task(task_id: str) -> Path | None:
    """First active audit-*.md whose frontmatter task_id matches."""
    repo = _project_root()
    audit_dir = repo / "docs" / "tasks" / "audits"
    if not audit_dir.is_dir():
        return None
    pattern = re.compile(r"^task_id:\s*([\w-]+)", re.MULTILINE)
    status_re = re.compile(r"^status:\s*in_progress\b", re.MULTILINE)
    for path in sorted(audit_dir.glob("audit-*.md")):
        try:
            text = path.read_text()
        except OSError:
            continue
        if not status_re.search(text):
            continue
        m = pattern.search(text)
        if m and m.group(1) == task_id:
            return path.relative_to(repo)
    return None


# ---------- cos_task_reposition ----------


@safe_tool
def cos_task_reposition(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    swimlane: str | None = None,
    to: str | None = None,
    reason: str | None = None,
    bypass_wip: bool = False,
    force: bool = False,
    agent_session: str | None = None,
) -> str:
    """Change task status and/or swimlane (YAML frontmatter + sync).

    Status changes use the same state machine + WIP rules as ``cos_task_move``.
    Swimlane-only changes patch the task MD file then ``sync_one``.
    When both are supplied, status transition runs first, then swimlane patch.
    """
    to_eff = (to or "").strip() or None
    swim_eff = (swimlane or "").strip() or None
    if not to_eff and not swim_eff:
        return fail(
            "validation",
            "at least one of `to` (status) or `swimlane` must be provided",
        )

    row = conn.execute(
        "SELECT status, swimlane, file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    current_status = str(row[0])
    cur_sl_raw = row[1]
    cur_sl = (str(cur_sl_raw).strip() if cur_sl_raw else "") or ""
    rel_path = row[2]
    project_root = _project_root()
    file_path: Path | None = None
    if rel_path:
        candidate = project_root / rel_path
        if candidate.exists():
            file_path = candidate

    config = _current_config()
    if swim_eff is not None:
        if config is None:
            return fail(
                "unavailable",
                "scrumban-config.yaml not found — run `cos board-config --init`",
            )
        if swim_eff not in config.swimlane_ids:
            return fail(
                "validation",
                f"swimlane {swim_eff!r} not in config; valid: {sorted(config.swimlane_ids)}",
            )

    wants_status = to_eff is not None and to_eff != current_status
    wants_swim = swim_eff is not None and swim_eff != cur_sl

    if not wants_status and not wants_swim:
        return ok(
            {
                "task_id": task_id,
                "previous_status": current_status,
                "new_status": current_status,
                "previous_swimlane": cur_sl or None,
                "new_swimlane": cur_sl or None,
                "warnings": ["no-op (already at requested status and swimlane)"],
            },
            meta={"layer": "tasks", "source": "board_os.cos_task_reposition"},
        )

    prev_status = current_status
    new_status = current_status
    warnings: list[str] = []

    if wants_status:
        result = transition(
            conn,
            task_id,
            to_eff,  # type: ignore[arg-type]
            reason=reason,
            agent_session=agent_session,
            bypass_wip=bypass_wip,
            force=force,
            config=config,
            file_path=file_path,
        )
        if not result.ok:
            return fail(
                result.error_category or "internal",
                result.error or "transition failed",
            )
        new_status = result.new_status
        warnings.extend(list(result.warnings))
        row2 = conn.execute(
            "SELECT swimlane FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        cur_sl = (str(row2[0]).strip() if row2 and row2[0] else "") or ""

    new_sl = cur_sl
    if wants_swim:
        if file_path is None:
            return fail(
                "unavailable",
                f"task {task_id} has no on-disk file — cannot change swimlane",
            )
        try:
            patch_task_frontmatter_scalars(file_path, {"swimlane": swim_eff})
        except (OSError, ValueError) as exc:
            return fail("validation", f"swimlane patch failed: {exc}")
        sync_one(conn, file_path, project_root=project_root)
        new_sl = swim_eff

    return ok(
        {
            "task_id": task_id,
            "previous_status": prev_status,
            "new_status": new_status,
            "previous_swimlane": cur_sl if wants_swim else None,
            "new_swimlane": new_sl if wants_swim else None,
            "warnings": warnings,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_reposition"},
    )


# ---------- cos_task_pick ----------


_PRIORITY_WEIGHT = {"P0": 100, "P1": 50, "P2": 20, "P3": 5}


@safe_tool
def cos_task_pick(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    priority_min: str = "P2",
    max_candidates: int = 5,
) -> str:
    pm_weight = _PRIORITY_WEIGHT.get(priority_min, 20)
    # "ready" is no longer a column — candidates now live in icebox with
    # a 'ready' label, plus the emergency column.  LIKE on labels_json
    # is cheap (<200 chars) and avoids a JSON1 dependency.
    clauses = ["(status = 'emergency' OR (status = 'icebox' AND labels_json LIKE '%\"ready\"%'))"]
    params: list = []
    if swimlane:
        clauses.append("swimlane = ?")
        params.append(swimlane)
    query = f"{_BOARD_SELECT} WHERE {' AND '.join(clauses)}"
    rows = conn.execute(query, params).fetchall()

    scored: list[tuple[int, dict]] = []
    for row in rows:
        card = _task_card(row)
        p = _PRIORITY_WEIGHT.get(card["priority"], 0)
        if p < pm_weight:
            continue
        score = p + (30 if card["status"] == "emergency" else 0)
        scored.append((score, card))

    scored.sort(key=lambda x: -x[0])
    top = [c for _, c in scored[:max_candidates]]
    return ok(
        {"candidates": top, "count": len(top)},
        meta={"layer": "tasks", "source": "board_os.cos_task_pick"},
    )


# ---------- cos_task_daily ----------


@safe_tool
def cos_task_daily(
    conn: sqlite3.Connection,
    *,
    since: str = "24h",
    agent_session: str | None = None,
) -> str:
    hours = _parse_since(since)
    threshold = int(time.time() - hours * 3600)

    recent = conn.execute(
        "SELECT task_id, old_status, new_status, reason, transitioned_at "
        "FROM task_status_history "
        "WHERE transitioned_at >= ? "
        "ORDER BY transitioned_at",
        (threshold,),
    ).fetchall()

    in_progress = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'in_progress' ORDER BY priority"
    ).fetchall()
    blocked = conn.execute(f"{_BOARD_SELECT} WHERE status = 'blocked' ORDER BY priority").fetchall()

    config = _current_config()
    wip = None
    if config is not None:
        state = check_wip(conn, config)
        wip = {"counts": state.counts, "caps": state.caps}

    return ok(
        {
            "yesterday": [
                {
                    "task_id": r[0],
                    "old_status": r[1],
                    "new_status": r[2],
                    "reason": r[3],
                    "transitioned_at": r[4],
                }
                for r in recent
            ],
            "in_progress": [_task_card(r) for r in in_progress],
            "blockers": [_task_card(r) for r in blocked],
            "wip": wip,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_daily"},
    )


# ---------- cos_task_retro ----------


@safe_tool
def cos_task_retro(conn: sqlite3.Connection, *, since: str = "7d") -> str:
    hours = _parse_since(since)
    threshold = int(time.time() - hours * 3600)

    completed = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'complete' AND completed_at >= ?",
        (threshold,),
    ).fetchall()
    cards = [_task_card(r) for r in completed]

    cycle_times_min = []
    for r in completed:
        started = r[11]
        done = r[12]
        if started and done:
            cycle_times_min.append((done - started) / 60.0)
    avg_cycle = (sum(cycle_times_min) / len(cycle_times_min)) if cycle_times_min else None

    emergency_count = conn.execute(
        "SELECT COUNT(*) FROM task_status_history "
        "WHERE new_status = 'emergency' AND transitioned_at >= ?",
        (threshold,),
    ).fetchone()[0]

    per_lane: dict[str, int] = {}
    for c in cards:
        per_lane[c["swimlane"] or "(none)"] = per_lane.get(c["swimlane"] or "(none)", 0) + 1

    return ok(
        {
            "completed": cards,
            "completed_count": len(cards),
            "cycle_time_avg_minutes": avg_cycle,
            "emergency_count": emergency_count,
            "swimlane_throughput": per_lane,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_retro"},
    )


# ---------- cos_task_wip_check ----------


@safe_tool
def cos_task_wip_check(conn: sqlite3.Connection) -> str:
    config = _current_config()
    if config is None:
        return fail(
            "unavailable",
            "scrumban-config.yaml not found — run `cos board-config --init`",
        )
    state = check_wip(conn, config)
    return ok(
        {
            "counts": state.counts,
            "caps": state.caps,
            "violations": list(state.violations),
            "over_cap": bool(state.violations),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_wip_check"},
    )


# ---------- cos_work_log_append ----------


@safe_tool
def cos_work_log_append(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    summary: str,
    agent_session: str | None = None,
    source: str = "manual",
) -> str:
    """Append one line to a task's Work Log section in the MD file."""
    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None or not row[0]:
        return fail("not_found", f"task {task_id} has no file_path")
    file_path = _project_root() / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")

    date = datetime.utcnow().strftime("%Y-%m-%d")
    agent_label = _agent_label(agent_session)
    summary_trunc = summary.strip().replace("\n", " ")[:120]
    line = f"- {date} [{agent_label}]: {summary_trunc}"

    content = file_path.read_text(encoding="utf-8")
    marker = "## Work Log"
    idx = content.find(marker)
    if idx == -1:
        # Append a Work Log section at the end.
        new_content = content.rstrip() + f"\n\n{marker}\n{line}\n"
    else:
        # Insert the line at the end of the Work Log section
        # (before the next H2 if any, else at EOF).
        next_h2 = content.find("\n## ", idx + len(marker))
        insert_at = next_h2 if next_h2 != -1 else len(content)
        before = content[:insert_at].rstrip()
        after = content[insert_at:]
        new_content = f"{before}\n{line}\n{after}"
    file_path.write_text(new_content, encoding="utf-8")

    # Re-sync to pick up the new log line.
    sync_one(conn, file_path, project_root=_project_root())

    return ok(
        {
            "task_id": task_id,
            "line_appended": line,
            "source": source,
        },
        meta={"layer": "tasks", "source": "board_os.cos_work_log_append"},
    )


# ---------- Helpers ----------


def _parse_since(since: str) -> float:
    """Convert since='24h', '7d', '30m' into hours (float)."""
    m = re.match(r"^(\d+)([mhdw])$", since)
    if not m:
        return 24.0
    n, unit = int(m.group(1)), m.group(2)
    return {"m": n / 60.0, "h": float(n), "d": n * 24.0, "w": n * 24.0 * 7.0}[unit]


# ---------- Cycle validation tool (exposed for hooks) ----------


def check_cycle(conn: sqlite3.Connection, task_id: str, new_deps: list[str]) -> list[str]:
    """Thin passthrough to workflow.validate_dependencies_no_cycle."""
    return validate_dependencies_no_cycle(conn, task_id, new_deps)
