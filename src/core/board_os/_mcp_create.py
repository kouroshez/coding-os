"""Private sibling of board_os.mcp_tools — import via the kernel, never directly."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    READY_LABEL,
    STATUS_ENUM,
    TASK_ID_FORMAT_RE,
)
from board_os.sync import sync_one
from board_os.workflow import (
    _format_yaml_scalar_token,
)
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_shared import (  # noqa: F401
    _BOARD_SELECT,
    _COMMIT_SCAN_CAP,
    _COMPLETION_EVIDENCE_RE,
    _SLUG_RE,
    _STRANDED_SCAN_LIMIT,
    _TASK_ID_ALLOCATORS,
    _actor_view,
    _agent_label,
    _allocate_with_prefix,
    _assign_guard,
    _commits_referencing,
    _completion_evidence,
    _current_config,
    _derive_ns_from_git,
    _detect_forge,
    _flag_stale,
    _has_table,
    _humanize_duration,
    _last_log_line,
    _LocalAllocator,
    _namespace_segment,
    _NamespacedAllocator,
    _next_task_id,
    _normalize_external_ref,
    _parse_since,
    _project_root,
    _resolve_attribution,
    _resolve_task_id_allocator,
    _sla_threshold_seconds,
    _slugify,
    _status_dwell_seconds,
    _task_card,
    check_cycle,
    cos_task_link,
    logger,
)


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
        "external_ref",
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
                inner = ", ".join(
                    _format_yaml_scalar_token(v) if isinstance(v, str) else str(v) for v in val
                )
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
    repro: str | None = None,
) -> str:
    # Sections a kind opts out of (e.g. chore drops Acceptance + Read First) are
    # NOT emitted so the agent isn't prompted for fields it won't need. Config
    # unavailable (fresh install) → fall back to the full template, never empty.
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
        repro_body = (
            repro.strip()
            if repro and repro.strip()
            else ("1. (fill in: exact steps to reproduce)\n2. ...\nExpected: ...\nActual: ...")
        )
        sections_to_render["Repro Steps"] = "## Repro Steps\n" + repro_body

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
    repro: str | None = None,
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

    bad_deps = [d for d in (depends_on or []) if not TASK_ID_FORMAT_RE.match(str(d))]
    if bad_deps:
        return fail(
            "validation",
            f"depends_on entries not TASK-NNN shaped: {bad_deps} — the cycle "
            "detector and dependents queries match ids literally",
        )

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

    try:
        task_id = _next_task_id(conn, project_root)
    except sqlite3.OperationalError as exc:
        return fail(
            "unavailable",
            f"task-id allocation failed under DB lock contention: {exc} — retry the create",
        )
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
        # Task-lifecycle fix: when a task is created
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
        repro=repro,
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

    # Create-time DoR echo — the same validator the ready/start gates run,
    # surfaced NOW so a placeholder create is never silently "fine" and only
    # discovered turns later at task-start. Warn-only: lean capture into
    # icebox stays allowed; the gaps just ride the envelope.
    from ._mcp_lifecycle import _ready_dor_check

    dor_gaps, _ = _ready_dor_check(file_path, agent_session)
    is_ready = READY_LABEL in labels
    # `ready` must be HONEST: a block-severity gap means the task cannot
    # leave icebox, regardless of the ready label (the old shape echoed
    # ready=true next to block gaps — a self-contradiction).
    has_block_gap = any(g.get("severity") == "block" for g in dor_gaps)
    dor = {"ready": is_ready and not has_block_gap, "label_ready": is_ready, "gaps": dor_gaps}
    if dor_gaps or not is_ready:
        fixes = []
        if dor_gaps:
            fixes.append("fill the flagged sections (outcome=/acceptance=/repro=/read_first=)")
        if not is_ready:
            fixes.append(f"mark pullable: cos task-ready {task_id} (or create with ready=True)")
        dor["fix"] = "; ".join(fixes)

    return ok(
        {
            "task_id": task_id,
            "file_path": str(file_path.relative_to(project_root)),
            "swimlane": swimlane,
            "kind": kind,
            "status": status,
            "dor": dor,
            "next_steps": _next_steps_for_kind(kind),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_create"},
    )


# ---------- cos_task_board ----------

# TASK-209: tiny safety margin below the budget — the probe mirrors the real
# envelope closely, so only a few bytes of slack are needed.
