"""board_os MCP tools — `cos_task_*` surface.

Implements board MCP tools, including:
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
    READY_LABEL,
    STATUS_ENUM,
    load_config,
)
from board_os.parser import parse_task
from board_os.sync import sync_one
from board_os.workflow import (
    _format_yaml_scalar_token,
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
    # Allocate the next TASK-NNN atomically. The old code read SELECT MAX
    # then returned — two concurrent creators read the same max before
    # either wrote, producing a duplicate id. Here a single INSERT…SELECT
    # computes max(db, filesystem)+1 AND reserves the row in one
    # statement, so SQLite's write lock serializes contenders: the loser
    # blocks (busy_timeout=5s), then reads the winner's reserved row and
    # picks the next integer. sync_one's upsert later overwrites the stub
    # (title/file_path/content_hash/mtime) with the real task fields.
    tasks_dir = project_root / "docs" / "tasks"
    fs_max = 0
    if tasks_dir.exists():
        for p in tasks_dir.glob("TASK-*.md"):
            m = re.match(r"TASK-(\d+)", p.name)
            if m:
                fs_max = max(fs_max, int(m.group(1)))

    import time as _t

    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            cur = conn.execute(
                """
                INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime)
                SELECT printf('TASK-%03d', MAX(n) + 1),
                       '(reserving)', 'icebox',
                       printf('docs/tasks/.reserve-%d.tmp', MAX(n) + 1), '', 0
                FROM (
                    SELECT COALESCE(MAX(CAST(SUBSTR(task_id, 6) AS INTEGER)), 0) AS n
                    FROM tasks
                    WHERE task_id LIKE 'TASK-%' AND SUBSTR(task_id, 6) GLOB '[0-9]*'
                    UNION ALL SELECT ? AS n
                )
                """,
                (fs_max,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT task_id FROM tasks WHERE rowid = ?", (cur.lastrowid,)
            ).fetchone()
            if row and row[0]:
                return str(row[0])
            raise sqlite3.OperationalError("reservation row not found after insert")
        except sqlite3.OperationalError as exc:
            last_exc = exc
            if "locked" in str(exc).lower() and attempt < 7:
                _t.sleep(0.05 * (attempt + 1))
                continue
            raise
    raise last_exc or sqlite3.OperationalError("task id allocation failed")


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
            # Route every string scalar through the shared YAML-safe quoter so a
            # title/value containing " or : or other specials stays valid YAML.
            lines.append(f"{key}: {_format_yaml_scalar_token(val)}")
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
    acceptance: str | None = None,
) -> str:
    """Render the task body with placeholders that match the kind's DoR.

    TASK-110+111. Sections that the kind explicitly opts
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
        accept_body = (
            acceptance.strip()
            if acceptance and acceptance.strip()
            else "- **Given** ...\n- **When** ...\n- **Then** ..."
        )
        sections_to_render["Acceptance"] = (
            "## Acceptance (G/W/T) — *this IS the Definition of Done*\n" + accept_body
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

    TASK-110. Mirrors the active DoR rules so the agent
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


def _status_dwell_seconds(now: float, started_at, last_transition_at) -> int | None:
    """Seconds the card has rested in its current status.

    Reuses the reclaim derivation (max of started_at and the last
    status-history transition) so dwell, reclaim idle, and SLA staleness
    all agree on one "last activity" definition. None when no timestamp
    signal exists (never started, no history) — callers render "—".
    """
    last = max(int(started_at or 0), int(last_transition_at or 0))
    if last <= 0:
        return None
    return max(0, int(now - last))


def _humanize_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _task_card(row: sqlite3.Row | tuple) -> dict:
    """Shape a DB row into a board card."""
    started_at = row[11] if len(row) > 11 else None
    completed_at = row[12] if len(row) > 12 else None
    last_transition_at = row[13] if len(row) > 13 else None
    dwell = _status_dwell_seconds(time.time(), started_at, last_transition_at)
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
        "started_at": started_at,
        "completed_at": completed_at,
        "last_transition_at": last_transition_at,
        "status_dwell_seconds": dwell,
        "status_dwell_human": _humanize_duration(dwell),
    }


def _sla_threshold_seconds(status: str, config) -> int | None:
    """SLA dwell budget for a status in seconds, or None when unbounded/disabled."""
    if config is None:
        return None
    policy = config.workflow_policy
    hours = {
        "in_progress": policy.in_progress_sla_hours,
        "testing": policy.testing_sla_hours,
    }.get(status)
    if hours is not None:
        return hours * 3600 if hours > 0 else None
    if status == "icebox":
        return policy.icebox_stale_days * 86400 if policy.icebox_stale_days > 0 else None
    return None


def _flag_stale(card: dict, config) -> dict:
    """Annotate a card with stale=True + stale_reason when dwell exceeds its SLA.

    Observability only — never mutates board state. Mutates the card dict in
    place and returns it so callers can map over a list.
    """
    threshold = _sla_threshold_seconds(card.get("status", ""), config)
    dwell = card.get("status_dwell_seconds")
    if threshold is not None and dwell is not None and dwell > threshold:
        card["stale"] = True
        card["stale_reason"] = (
            f"{card['status']} {card.get('status_dwell_human')} > SLA "
            f"{_humanize_duration(threshold)}"
        )
    else:
        card["stale"] = False
        card["stale_reason"] = None
    return card


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


def _assign_guard(
    file_path: Path | None,
    agent_session: str | None,
    force: bool,
) -> str | None:
    """Block a move when the task's `assignee` frontmatter names someone else.

    Opt-in and backward-compatible: a task with no `assignee:` field — the
    default — is movable by anyone. When `assignee` IS set, only that
    session, or any session of the same agent, may move the card. This
    stops one agent silently driving a task another agent (or a human)
    parked. `force=True` or `COS_ASSIGN_OVERRIDE=1` bypasses. Returns an
    error message, or None when the move is allowed.
    """
    if force or os.environ.get("COS_ASSIGN_OVERRIDE") == "1":
        return None
    if file_path is None or not file_path.exists():
        return None
    try:
        head = file_path.read_text(encoding="utf-8")[:2000]
    except OSError:
        return None
    match = re.search(r"^assignee:[ \t]*(.+?)[ \t]*$", head, re.MULTILINE)
    if not match:
        return None
    assignee = match.group(1).strip().strip('"').strip("'")
    if assignee.lower() in ("", "any", "anyone", "unassigned", "null", "~"):
        return None

    from ._agent_runtime import detect_agent

    mover = (agent_session or "").strip()
    if assignee == mover:
        return None
    mover_agent = detect_agent(mover)
    if mover_agent != "agent" and detect_agent(assignee) == mover_agent:
        return None
    return (
        f"task is assigned to {assignee!r} — current mover is "
        f"{mover or 'unattributed'!r}. Re-assign the task (edit its "
        "`assignee:` frontmatter) or override with force=True / "
        "COS_ASSIGN_OVERRIDE=1."
    )


_BOARD_SELECT = (
    "SELECT task_id, title, swimlane, kind, epic, labels_json, "
    "       status, priority, appetite, agent_session, work_log_last_5, "
    "       started_at, completed_at, "
    # last_transition_at (row[13]): the most recent status-change time from
    # history. Correlated subquery keeps the column appended LAST so existing
    # positional readers (retro r[11]/r[12]) are unaffected. Powers the board
    # time dimension (status_dwell_seconds) — RC5 in
    # audit-task-lifecycle-integrity-2026-06-05.md.
    "       (SELECT MAX(h.transitioned_at) FROM task_status_history h "
    "        WHERE h.task_id = tasks.task_id) AS last_transition_at "
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
    acceptance: str | None = None,
    read_first: list[str] | None = None,
    depends_on: list[str] | None = None,
    status: str = "icebox",
    ready: bool = False,
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

    labels = list(labels or [])
    for lbl in labels:
        if lbl in KIND_ENUM:
            return fail(
                "validation",
                f"label {lbl!r} collides with KIND_ENUM — use kind, not labels",
            )
    # `ready=True` is the one-shot path: create a groomed task already
    # marked pullable, so the require_ready_label gate passes without a
    # separate cos_task_ready call.
    if ready and READY_LABEL not in labels:
        labels.append(READY_LABEL)

    # Force Definition of Ready when creating directly into in_progress —
    # parity with the icebox→in_progress transition gate (workflow.transition),
    # which the create-path otherwise bypasses. Validate BEFORE allocating a
    # TASK id so a rejected create never burns an id. Lean capture into
    # icebox/emergency stays unrestricted; complete stays a retro escape.
    if status == "in_progress":
        preview_rf = "\n".join(f"- {p}" for p in (read_first or ["(no doc yet — exploratory)"]))
        preview_body = _render_kind_aware_body(
            task_id="TASK-PENDING",
            title=title,
            kind=kind,
            outcome=outcome,
            read_first_block=preview_rf,
            acceptance=acceptance,
        )
        try:
            from board_os.transition_gates import GatesConfigError, load_gates_config
            from board_os.transition_gates_validator import (
                validate_transition as _gate_validate,
            )

            gate = _gate_validate(
                task_id="TASK-PENDING",
                kind=kind,
                body=preview_body,
                new_status="in_progress",
                config=load_gates_config(),
                override_reason=os.environ.get("COS_OVERRIDE_REASON"),
                override_actor=os.environ.get("COS_AGENT") or agent_session,
            )
        except GatesConfigError:
            gate = None
        if gate is not None and gate.blocked:
            return fail(
                "validation",
                "cannot create directly into in_progress — Definition of Ready not met: "
                + "; ".join(f"[{m.code}] {m.message}" for m in gate.messages)
                + ". Fix: create into icebox, fill Outcome + Acceptance, mark ready, "
                "then cos_task_start — or pass outcome= and acceptance= to one-shot it.",
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
        # F17 / TASK-029 task-lifecycle fix: when a task is created
        # directly into `in_progress`, stamp started + agent_session
        # so YAML and DB agree. F17b: narrowed to `in_progress` only
        # to match `workflow.transition`'s semantics — testing/emergency
        # are reached via transition, not create-path, so stamping them
        # at create would diverge from the transition convention.
        # `completed` stays stamp-on-create because creating a task
        # already-complete is a legitimate retro entry.
        "started": today if status == "in_progress" else None,
        "completed": today if status == "complete" else None,
        "agent_session": agent_session if status == "in_progress" else None,
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
        acceptance=acceptance,
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
    cards = [_flag_stale(_task_card(r), config) for r in rows]

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


# ---------- cos_task_show ----------


@safe_tool
def cos_task_show(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    include_body: bool = True,
) -> str:
    row = conn.execute(
        "SELECT task_id, title, status, swimlane, kind, priority, "
        "appetite, file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")
    data = {
        "id": row[0],
        "title": row[1],
        "status": row[2],
        "swimlane": row[3],
        "kind": row[4],
        "priority": row[5],
        "appetite": row[6],
        "file_path": row[7],
        "body": None,
    }
    if include_body and row[7]:
        full = _project_root() / row[7]
        if full.exists():
            data["body"] = full.read_text(encoding="utf-8")
    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_show"})


# ---------- cos_task_move ----------


def _record_completion_outcome_safe(conn: sqlite3.Connection, task_id: str) -> None:
    # Fire-and-forget: feed an MCP-driven completion into the learning loop,
    # mirroring the CLI task-done path. Without this, tasks closed via
    # cos_task_move never produced a task_outcome row.
    try:
        from thinking_os.record_outcome import record_outcome

        krow = conn.execute("SELECT kind FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        kind = (krow[0] if krow else "") or "feature"
        ttype = {
            "bug": "fix",
            "feature": "feat",
            "refactor": "refactor",
            "docs": "docs",
            "test": "test",
            "chore": "infra",
            "spike": "spike",
            "security": "security",
        }.get(kind, "feat")
        db_path = os.environ.get(
            "COS_DB_PATH", str(_project_root() / ".coding-os" / "coding-os.db")
        )
        record_outcome(task_id=task_id, task_type=ttype, outcome="success", db_path=db_path)
    except Exception as exc:
        logger.debug("MCP completion outcome failed for %s: %s", task_id, exc)


@safe_tool
def _auto_reclaim_zombies_safe(conn: sqlite3.Connection) -> None:
    """Best-effort zombie reclaim run before an in_progress pull. Frees idle
    in_progress tasks of inactive sessions so the board self-heals without a
    manual `cos task-reclaim`. Never raises (cos_task_reclaim is @safe_tool)."""
    try:
        cos_task_reclaim(conn)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("auto-reclaim before start skipped: %s", exc)


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

    agent_session = _resolve_attribution(agent_session)
    guard = _assign_guard(file_path, agent_session, force)
    if guard is not None:
        return fail("validation", guard)

    # Free zombie in_progress of dead/idle sessions before a pull, so a live
    # agent isn't blocked by a crashed peer and the board self-heals without a
    # manual `cos task-reclaim`. Conservative — only idle + owner-inactive
    # tasks qualify (see cos_task_reclaim). Best-effort; never blocks the move.
    if to == "in_progress" and not bypass_wip and not force:
        _auto_reclaim_zombies_safe(conn)

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
        _record_completion_outcome_safe(conn, task_id)
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
    agent_session = _resolve_attribution(agent_session)
    guard = _assign_guard(file_path, agent_session, force)
    if guard is not None:
        return fail("validation", guard)
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
    """Rewrite the frontmatter `labels:` flow-list in place (atomic)."""
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
                "warnings": [f"no-op (label '{READY_LABEL}' already {'set' if ready else 'absent'})"],
            },
            meta={"layer": "tasks", "source": "board_os.cos_task_ready"},
        )

    if ready:
        labels.append(READY_LABEL)
    else:
        labels = [lbl for lbl in labels if lbl != READY_LABEL]

    project_root = _project_root()
    rel_path = row[1]
    file_path = project_root / rel_path if rel_path else None
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

    return ok(
        {
            "task_id": task_id,
            "ready": ready,
            "labels": labels,
            "status": str(row[0]),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_ready"},
    )


# ---------- cos_task_reclaim (zombie in_progress recovery) ----------


def _active_session_ids(now: float, window: int = 1800) -> set[str]:
    """Session ids with presence activity inside `window` seconds.

    Reads the agent-presence JSON files under
    `$COS_STATE_DIR/<agent>/sessions/*.json` (written by agent-presence.sh).
    Missing / unreadable presence is treated as "no active sessions" so
    reclaim falls back to the idle-only signal.
    """
    ids: set[str] = set()
    state_dir = os.environ.get("COS_STATE_DIR") or str(_project_root() / ".coding-os")
    base = Path(state_dir)
    if not base.is_dir():
        return ids
    for sess_dir in base.glob("*/sessions"):
        for jf in sess_dir.glob("*.json"):
            try:
                d = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if d.get("ended_at"):
                continue
            last = 0
            for key in ("last_tool_at", "last_prompt_at", "started_at"):
                val = d.get(key)
                if isinstance(val, (int, float)):
                    last = max(last, int(val))
            if last and (now - last) < window:
                sid = d.get("session_id")
                if sid:
                    ids.add(str(sid))
    return ids


def _commits_referencing(task_id: str, project_root: Path) -> int | None:
    """Count git commits whose message references this TASK-ID — the strongest
    'work was actually done' signal for reconciliation.

    Returns None when the count CANNOT be verified (no git repo / git missing /
    error) so callers fail SAFE — they treat 'unverifiable' as 'has evidence'
    and never auto-reclaim a task on a signal we could not check. The grep is
    anchored with a trailing non-digit boundary so `TASK-215` does not also
    match `TASK-2155` (substring over-match)."""
    import subprocess

    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "log", "--all", "-E",
             "--grep", f"{task_id}([^0-9]|$)", "--oneline"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return sum(1 for line in out.stdout.splitlines() if line.strip())


def _has_work_log(work_log_json: object) -> bool:
    try:
        return bool(json.loads(work_log_json or "[]"))
    except (json.JSONDecodeError, TypeError):
        return False


def _classify_stranded(status: str, commits: int | None, has_work_log: bool) -> str:
    """Triage a stranded task by completion evidence (TASK-215).

    likely_complete  — reached `testing` AND has committed/logged work: almost
                       certainly finished, just never closed. Review -> done.
    likely_abandoned — `in_progress` with VERIFIED zero commits and no work-log:
                       nothing happened. Park or resume.
    needs_review     — everything ambiguous.

    `commits is None` means unverifiable (no git / error) — counted as evidence
    so a task is never called abandoned on a signal we could not check (TASK-217).
    """
    has_commit_evidence = commits is None or commits > 0
    if status == "testing" and (has_commit_evidence or has_work_log):
        return "likely_complete"
    if status == "in_progress" and commits == 0 and not has_work_log:
        return "likely_abandoned"
    return "needs_review"


def _reconcile_recommendation(task_id: str, classification: str, commits: int) -> str:
    n = "?" if commits is None else commits
    if classification == "likely_complete":
        return (
            f"Looks finished ({n} commit(s) reference it, reached testing). "
            f"Review acceptance, then `cos task-done {task_id}`; if not actually "
            f"done, `cos task-start {task_id}` to resume."
        )
    if classification == "likely_abandoned":
        return (
            f"No committed progress — `cos task-cancel {task_id} --park` to shelve, "
            f"or `cos task-start {task_id}` to resume."
        )
    return f"Review with `cos task-show {task_id}` -> complete, resume, or park."


@safe_tool
def cos_task_reclaim(
    conn: sqlite3.Connection,
    *,
    idle_hours: int | None = None,
    dry_run: bool = False,
    agent_session: str | None = None,
) -> str:
    """Reclaim zombie in_progress/testing/emergency tasks (idle + owner inactive); testing->in_progress, else->icebox."""
    config = _current_config()
    default_threshold_h = idle_hours if idle_hours is not None else (
        config.workflow_policy.reclaim_idle_hours if config is not None else 24
    )

    def _threshold_for(status: str) -> int:
        # Per-status idle window. `testing` is mid-flight work funneled there by
        # the testing-first protocol, so reclaim it sooner than a generic
        # in_progress zombie. An explicit idle_hours arg overrides all statuses.
        if idle_hours is not None or config is None:
            return default_threshold_h
        if status == "testing":
            t = config.workflow_policy.testing_reclaim_idle_hours
            return t if t > 0 else config.workflow_policy.reclaim_idle_hours
        return config.workflow_policy.reclaim_idle_hours

    now = time.time()
    active = _active_session_ids(now)
    project_root = _project_root()

    # Widened from in_progress-only (RC3): a `testing` zombie was previously
    # un-reclaimable by every path, which is exactly where the protocol parks
    # near-done work at the moment of session death.
    rows = conn.execute(
        "SELECT task_id, agent_session, started_at, file_path, status, work_log_last_5 "
        "FROM tasks WHERE status IN ('in_progress', 'testing', 'emergency')"
    ).fetchall()

    reclaimed: list[dict] = []
    skipped_for_review: list[dict] = []
    for task_id, owner, started_at, rel, status, work_log in rows:
        hist = conn.execute(
            "SELECT MAX(transitioned_at) FROM task_status_history WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        last_activity = max(
            int(started_at or 0),
            int(hist[0]) if hist and hist[0] else 0,
        )
        # No activity signal at all → too risky to reclaim; skip.
        if last_activity == 0:
            continue
        threshold_h = _threshold_for(status)
        idle_s = now - last_activity
        if idle_s < threshold_h * 3600:
            continue
        # Owner still actively present → never reclaim its work.
        if owner and owner in active:
            continue

        # Don't blindly recycle a probably-FINISHED task. A testing
        # zombie with committed/logged work is almost certainly done — the agent
        # just forgot task-done. Leave it in testing for review (cos_task_reconcile
        # surfaces it) instead of recycling it to in_progress.
        if status == "testing":
            commits = _commits_referencing(task_id, project_root)
            # None = unverifiable (no git) → counts as evidence so we never
            # recycle a testing card on a signal we could not check.
            if _has_work_log(work_log) or commits is None or commits > 0:
                skipped_for_review.append({"task_id": task_id, "previous_owner": owner})
                continue

        # Status-aware destination: a testing zombie is near-done, so return it
        # to in_progress (a legal unforced edge) to resume the work rather than
        # dumping it to the backlog; in_progress/emergency zombies go to icebox.
        dest = "in_progress" if status == "testing" else "icebox"
        idle_h = round(idle_s / 3600, 1)
        if dry_run:
            reclaimed.append({
                "task_id": task_id, "previous_owner": owner, "idle_hours": idle_h,
                "from_status": status, "to_status": dest,
            })
            continue

        file_path = project_root / rel if rel else None
        # Only a backlog-bound (icebox) reclaim needs the ready label so the
        # card stays pullable; a testing->in_progress reclaim keeps its labels.
        if dest == "icebox" and file_path is not None and file_path.exists():
            cur_labels = _labels_list_from_json(
                conn.execute(
                    "SELECT labels_json FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
            )
            if READY_LABEL not in cur_labels:
                cur_labels.append(READY_LABEL)
                try:
                    _patch_labels_line(file_path, cur_labels)
                    sync_one(conn, file_path, project_root=project_root)
                except (OSError, ValueError) as exc:
                    logger.debug("reclaim label patch failed for %s: %s", task_id, exc)

        result = transition(
            conn,
            task_id,
            dest,
            reason=f"reclaim: {status} idle {idle_h}h, owner session inactive -> {dest}",
            agent_session=agent_session,
            force=True,
            config=config,
            file_path=file_path,
        )
        if result.ok:
            reclaimed.append({
                "task_id": task_id, "previous_owner": owner, "idle_hours": idle_h,
                "from_status": status, "to_status": dest,
            })

    return ok(
        {
            "reclaimed": reclaimed,
            "count": len(reclaimed),
            "skipped_for_review": skipped_for_review,
            "dry_run": dry_run,
            "idle_hours_threshold": default_threshold_h,
            "active_sessions": len(active),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_reclaim"},
    )


@safe_tool
def cos_task_reconcile(conn: sqlite3.Connection, *, include_active: bool = False) -> str:
    """Triage stranded in_progress/testing tasks with completion evidence + a review recommendation (read-only)."""
    now = time.time()
    active = _active_session_ids(now)
    project_root = _project_root()
    rows = conn.execute(
        "SELECT task_id, agent_session, status, started_at, work_log_last_5, "
        "  (SELECT MAX(transitioned_at) FROM task_status_history h "
        "   WHERE h.task_id = tasks.task_id) "
        "FROM tasks WHERE status IN ('in_progress', 'testing', 'emergency') "
        "ORDER BY status DESC, task_id"
    ).fetchall()
    items: list[dict] = []
    for task_id, owner, status, started_at, work_log, last_tx in rows:
        owner_active = bool(owner and owner in active)
        # By default reconcile only the STRANDED (dead-owner) tasks; pass
        # include_active=True to review everything currently open.
        if owner_active and not include_active:
            continue
        commits = _commits_referencing(task_id, project_root)
        has_wl = _has_work_log(work_log)
        classification = _classify_stranded(status, commits, has_wl)
        dwell = _status_dwell_seconds(now, started_at, last_tx)
        items.append(
            {
                "task_id": task_id,
                "status": status,
                "previous_owner": owner,
                "owner_active": owner_active,
                "commits_referencing": commits,
                "has_work_log": has_wl,
                "status_dwell_seconds": dwell,
                "status_dwell_human": _humanize_duration(dwell),
                "classification": classification,
                "recommendation": _reconcile_recommendation(task_id, classification, commits),
            }
        )
    summary = {
        "likely_complete": sum(1 for i in items if i["classification"] == "likely_complete"),
        "likely_abandoned": sum(1 for i in items if i["classification"] == "likely_abandoned"),
        "needs_review": sum(1 for i in items if i["classification"] == "needs_review"),
    }
    return ok(
        {"stranded": items, "count": len(items), "summary": summary},
        meta={"layer": "tasks", "source": "board_os.cos_task_reconcile"},
    )


_KEEP_LABELS = ("keep", "parked")


def _archive_stale_sweep(conn: sqlite3.Connection, config) -> list[dict]:
    """Auto-archive aged icebox / complete cards — the icebox OUTFLOW (RC6).

    OFF by default: only runs for a status whose ``*_auto_archive_days`` knob is
    > 0, so a fresh project never silently deletes backlog. A ``keep``/``parked``
    label always exempts a card, and archive is reversible (archive->icebox is a
    legal edge). Idempotent + fail-soft per card.
    """
    if config is None:
        return []
    policy = config.workflow_policy
    plans: list[tuple[str, int]] = []
    if getattr(policy, "icebox_auto_archive_days", 0) > 0:
        plans.append(("icebox", policy.icebox_auto_archive_days * 86400))
    if getattr(policy, "complete_auto_archive_days", 0) > 0:
        plans.append(("complete", policy.complete_auto_archive_days * 86400))
    if not plans:
        return []

    now = time.time()
    project_root = _project_root()
    archived: list[dict] = []
    for status, threshold_s in plans:
        rows = conn.execute(
            "SELECT task_id, started_at, file_path, labels_json, "
            "  (SELECT MAX(transitioned_at) FROM task_status_history h "
            "   WHERE h.task_id = tasks.task_id) "
            "FROM tasks WHERE status = ?",
            (status,),
        ).fetchall()
        for task_id, started_at, rel, labels_json, last_tx in rows:
            dwell = _status_dwell_seconds(now, started_at, last_tx)
            if dwell is None or dwell < threshold_s:
                continue
            if any(lbl in _KEEP_LABELS for lbl in _labels_list_from_json(labels_json)):
                continue
            file_path = project_root / rel if rel else None
            result = transition(
                conn,
                task_id,
                "archive",
                reason=f"auto-archive: {status} idle {round(dwell / 86400, 1)}d",
                agent_session=None,
                force=True,
                config=config,
                file_path=file_path,
            )
            if result.ok:
                archived.append(
                    {"task_id": task_id, "from_status": status, "age_days": round(dwell / 86400, 1)}
                )
            else:
                # Surface per-task failures instead of silently dropping them so
                # the daily "N archived" count can't hide stranded cards.
                logger.warning("auto-archive transition failed for %s (%s)", task_id, status)
    return archived


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

    # Self-heal at the session-start ritual: reclaim zombie in_progress
    # tasks (idle + owner session inactive) before reporting state.
    # Fire-and-forget — daily must never fail on the reclaim path.
    config = _current_config()

    reclaimed: list[dict] = []
    try:
        rec_env = json.loads(cos_task_reclaim(conn, agent_session=agent_session))
        if rec_env.get("ok"):
            reclaimed = rec_env["data"]["reclaimed"]
    except Exception as exc:  # noqa: BLE001 - fire-and-forget
        logger.debug("daily reclaim skipped: %s", exc)

    # Icebox outflow — auto-archive aged backlog/complete cards when the project
    # opted in (default off). Runs before the status queries so archived cards
    # drop out of the report naturally. Fire-and-forget.
    auto_archived: list[dict] = []
    try:
        auto_archived = _archive_stale_sweep(conn, config)
    except Exception as exc:  # noqa: BLE001 - fire-and-forget
        logger.debug("daily archive sweep skipped: %s", exc)

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
    # `testing` was previously absent from daily — the protocol funnels work
    # there before completion, so an abandoned card most often rots in testing
    # (RC3). Report it so a stranded testing zombie is visible at standup.
    testing = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'testing' ORDER BY priority"
    ).fetchall()
    blocked = conn.execute(f"{_BOARD_SELECT} WHERE status = 'blocked' ORDER BY priority").fetchall()
    icebox = conn.execute(f"{_BOARD_SELECT} WHERE status = 'icebox'").fetchall()

    wip = None
    if config is not None:
        state = check_wip(conn, config)
        wip = {"counts": state.counts, "caps": state.caps}

    in_progress_cards = [_flag_stale(_task_card(r), config) for r in in_progress]
    testing_cards = [_flag_stale(_task_card(r), config) for r in testing]
    blocker_cards = [_flag_stale(_task_card(r), config) for r in blocked]
    icebox_cards = [_flag_stale(_task_card(r), config) for r in icebox]
    icebox_stale = [c for c in icebox_cards if c.get("stale")]
    icebox_summary = {
        "total": len(icebox_cards),
        "stale": len(icebox_stale),
        "stale_ids": [c["id"] for c in icebox_stale[:20]],
    }

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
            "in_progress": in_progress_cards,
            "testing": testing_cards,
            "blockers": blocker_cards,
            "icebox": icebox_summary,
            "wip": wip,
            "reclaimed": reclaimed,
            "auto_archived": auto_archived,
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
    summary: str | None = None,
    note: str | None = None,
    agent_session: str | None = None,
    source: str = "manual",
) -> str:
    """Append one line to a task's Work Log section in the MD file."""
    # G38: accept `note` as alias of `summary` — many task-driver
    # callers (and docs) pass `note=...`; the prior signature only
    # honoured `summary`, producing a 422 validation error.
    if summary is None and note is not None:
        summary = note
    if not isinstance(summary, str) or not summary.strip():
        return fail("validation", "summary (or note) is required")
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


# ---------- cos_task_history ----------


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _actor_view(agent_session: str | None) -> dict:
    """Structured actor for a stored agent_session string (agent | human)."""
    from ._agent_runtime import detect_agent

    if not agent_session:
        return {"type": "human", "id": "human", "label": "human"}
    label = detect_agent(agent_session)
    return {
        "type": "human" if label == "human" else "agent",
        "id": agent_session,
        "label": label,
    }


def _git_commits_for_path(rel_path: str, *, limit: int = 50) -> list[dict]:
    """Git log for one task file — the git-backed slice of task history. Fail-open."""
    import subprocess

    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"-n{limit}",
                "--format=%H%x1f%ct%x1f%s",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log failed for %s: %s", rel_path, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


@safe_tool
def cos_task_history(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    include_commits: bool = True,
    limit: int = 200,
) -> str:
    """Full actor-attributed task history — creation, status transitions, field edits, and git commits."""
    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    events: list[dict] = []

    for r in conn.execute(
        "SELECT old_status, new_status, agent_session, reason, transitioned_at, "
        "override_reason, override_actor FROM task_status_history "
        "WHERE task_id = ? ORDER BY transitioned_at",
        (task_id,),
    ).fetchall():
        old, new, sess, reason, at, ov_reason, ov_actor = r
        events.append(
            {
                "type": "created" if not old else "status",
                "from": old or None,
                "to": new,
                "actor": _actor_view(sess),
                "reason": reason,
                "override_reason": ov_reason,
                "override_actor": ov_actor,
                "at": at,
            }
        )

    if _has_table(conn, "task_edit_history"):
        for r in conn.execute(
            "SELECT field, old_value, new_value, actor_type, actor_id, source, edited_at "
            "FROM task_edit_history WHERE task_id = ? ORDER BY edited_at",
            (task_id,),
        ).fetchall():
            field, oldv, newv, atype, aid, src, at = r
            events.append(
                {
                    "type": "edit",
                    "field": field,
                    "old_value": oldv,
                    "new_value": newv,
                    "actor": {"type": atype, "id": aid, "label": aid or atype},
                    "source": src,
                    "at": at,
                }
            )

    commits: list[dict] = []
    if include_commits and row[0]:
        commits = _git_commits_for_path(row[0], limit=limit)
        for c in commits:
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )

    events.sort(key=lambda e: e.get("at") or 0)
    if len(events) > limit:
        events = events[-limit:]

    created = next((e for e in events if e["type"] == "created"), None)
    edits = [e for e in events if e["type"] == "edit"]
    contributors = sorted(
        {
            e["actor"]["label"]
            for e in events
            if e.get("type") in {"created", "status", "edit"} and isinstance(e.get("actor"), dict)
        }
    )
    summary = {
        "created_by": created["actor"]["label"] if created else None,
        "created_at": created["at"] if created else None,
        "last_edited_by": edits[-1]["actor"]["label"] if edits else None,
        "last_edited_at": edits[-1]["at"] if edits else None,
        "contributors": contributors,
        "commit_count": len(commits),
    }

    return ok(
        {"task_id": task_id, "events": events, "summary": summary, "count": len(events)},
        meta={"layer": "tasks", "source": "board_os.cos_task_history"},
    )


# ---------- cos_task_edit ----------


def _record_task_edit(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    field: str,
    old: str | None,
    new: str | None,
    actor_type: str,
    actor_id: str | None,
    source: str,
) -> None:
    """Append one actor-attributed field edit. Fail-open — never blocks the edit."""
    if not _has_table(conn, "task_edit_history"):
        return
    try:
        conn.execute(
            "INSERT INTO task_edit_history "
            "(task_id, field, old_value, new_value, actor_type, actor_id, source, edited_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, field, old, new, actor_type, actor_id, source, int(time.time())),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.debug("task_edit_history insert failed for %s.%s: %s", task_id, field, exc)


@safe_tool
def cos_task_edit(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    title: str | None = None,
    priority: str | None = None,
    swimlane: str | None = None,
    appetite: str | None = None,
    epic: str | None = None,
    labels: list[str] | None = None,
    body: str | None = None,
    actor_type: str = "agent",
    actor_id: str | None = None,
    source: str = "mcp",
) -> str:
    """Edit a task's frontmatter fields and/or body, recording each change to the actor-attributed edit history."""
    from board_os.parser import _FRONTMATTER_RE, extract_frontmatter

    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None or not row[0]:
        return fail("not_found", f"task {task_id} not found")
    file_path = _project_root() / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(content)
    fm = extract_frontmatter(content)
    if m is None or fm is None:
        return fail("validation", f"{task_id} is not in lean frontmatter format")
    current_body = m.group("body")

    config = _current_config()
    if swimlane is not None and config is not None and swimlane not in config.swimlane_ids:
        return fail(
            "validation",
            f"swimlane {swimlane!r} not in config; valid: {sorted(config.swimlane_ids)}",
        )
    if priority is not None and priority not in PRIORITY_ENUM:
        return fail("validation", f"priority {priority!r} not in {sorted(PRIORITY_ENUM)}")
    if appetite is not None and not APPETITE_RE.match(appetite):
        return fail("validation", f"appetite {appetite!r} bad shape")
    if title is not None and not title.strip():
        return fail("validation", "title must be non-empty")
    if labels is not None:
        for lbl in labels:
            if lbl in KIND_ENUM:
                return fail(
                    "validation",
                    f"label {lbl!r} collides with KIND_ENUM — use kind, not labels",
                )

    resolved_actor = actor_id or _resolve_attribution(None)
    changed: list[str] = []

    def _maybe(field: str, new_val: object) -> None:
        if new_val is None or new_val == fm.get(field):
            return
        old_val = fm.get(field)
        fm[field] = new_val
        _record_task_edit(
            conn,
            task_id=task_id,
            field=field,
            old=None if old_val is None else str(old_val),
            new=str(new_val),
            actor_type=actor_type,
            actor_id=resolved_actor,
            source=source,
        )
        changed.append(field)

    _maybe("title", title)
    _maybe("priority", priority)
    _maybe("swimlane", swimlane)
    _maybe("appetite", appetite)
    _maybe("epic", epic)

    if labels is not None and list(labels) != list(fm.get("labels") or []):
        old_labels = fm.get("labels") or []
        fm["labels"] = list(labels)
        _record_task_edit(
            conn,
            task_id=task_id,
            field="labels",
            old=", ".join(str(x) for x in old_labels),
            new=", ".join(labels),
            actor_type=actor_type,
            actor_id=resolved_actor,
            source=source,
        )
        changed.append("labels")

    new_body = current_body
    if body is not None and body.strip() != current_body.strip():
        import hashlib

        new_body = body
        _record_task_edit(
            conn,
            task_id=task_id,
            field="body",
            old=hashlib.sha1(current_body.encode("utf-8")).hexdigest()[:12],
            new=hashlib.sha1(body.encode("utf-8")).hexdigest()[:12],
            actor_type=actor_type,
            actor_id=resolved_actor,
            source=source,
        )
        changed.append("body")

    if not changed:
        return ok(
            {"task_id": task_id, "changed": []},
            meta={"layer": "tasks", "source": "board_os.cos_task_edit"},
        )

    # Normalise the canonical H1 (`# TASK-NNN: <title>`) from the current
    # frontmatter title: a panel body edit arrives H1-stripped (the drawer
    # removes it for display) and a title change must propagate to the H1.
    # Strip any leading H1 from the incoming body, then prepend the canonical.
    title_now = str(fm.get("title") or task_id)
    body_inner = re.sub(r"^\s*#\s+.+\n+", "", new_body.lstrip("\n"))
    new_content = (
        _render_lean_frontmatter(fm)
        + f"\n\n# {task_id}: {title_now}\n\n"
        + body_inner.strip("\n")
        + "\n"
    )
    file_path.write_text(new_content, encoding="utf-8")
    sync_one(conn, file_path, project_root=_project_root())

    return ok(
        {
            "task_id": task_id,
            "changed": changed,
            "actor": {"type": actor_type, "id": resolved_actor},
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_edit"},
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
