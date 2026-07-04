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

import base64
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
    TASK_ID_FORMAT_RE,
    load_config,
)
from board_os.parser import parse_task
from board_os.sync import sync_one
from board_os.workflow import (
    _format_yaml_scalar_token,
    _has_task_dependencies_table,
    check_wip,
    dependents_of,
    incomplete_dependencies,
    patch_task_frontmatter_scalars,
    transition,
    validate_dependencies_no_cycle,
)
from thinking_os.tools._shared import TOKEN_BUDGET_CHARS, _budget_size, fail, ok, safe_tool

logger = logging.getLogger("coding_os.board_os.mcp_tools")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------- Internal helpers ----------


def _project_root() -> Path:
    from thinking_os.database import project_root

    return project_root()


def _current_config():
    try:
        return load_config(_project_root())
    except FileNotFoundError:
        return None


def _slugify(title: str, *, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


def _derive_ns_from_git(project_root: Path) -> str:
    # Stable, low-collision uppercase NS from git user.email — the zero-config
    # fallback for the namespaced scheme. 4 base36 chars of a sha1: readable
    # enough as a namespace, collision-rare; docs recommend an explicit prefix.
    import hashlib
    import string
    import subprocess

    try:
        email = subprocess.run(
            ["git", "-C", str(project_root), "config", "user.email"],
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        email = ""
    if not email:
        return ""
    alphabet = string.ascii_uppercase + string.digits
    n = int(hashlib.sha1(email.encode()).hexdigest()[:12], 16)
    out = ""
    for _ in range(4):
        out += alphabet[n % len(alphabet)]
        n //= len(alphabet)
    return ("T" + out[1:]) if not out[0].isalpha() else out


def _namespace_segment(project_root: Path) -> str:
    # '' when no valid namespace → caller degrades to plain TASK-NNN. The scheme
    # gate lives in the dispatcher, not here.
    try:
        from board_os.config import load_config

        cfg = load_config(project_root)
    except Exception as exc:
        logger.debug("namespace segment resolve failed: %s", exc)
        return ""
    ns = (getattr(cfg, "task_id_prefix", "") or "").strip().upper()
    if not ns:
        ns = _derive_ns_from_git(project_root)
    if not re.match(r"^[A-Z][A-Z0-9]{1,7}$", ns):
        return ""
    return f"{ns}-"


def _allocate_with_prefix(conn: sqlite3.Connection, project_root: Path, id_prefix: str) -> str:
    # Atomic per-prefix counter: one INSERT…SELECT computes max(db, fs)+1 for
    # THIS id_prefix AND reserves the row, so SQLite's write lock serializes
    # concurrent local creators. The per-prefix max keeps each namespace an
    # independent sequence (un-synced contributors never collide). id_prefix is
    # validated safe chars (TASK- + uppercase NS + dash) → safe to interpolate.
    substr_start = len(id_prefix) + 1  # 1-indexed SQL SUBSTR past the prefix
    like_pat = id_prefix + "%"

    tasks_dir = project_root / "docs" / "tasks"
    num_re = re.compile(re.escape(id_prefix) + r"(\d+)")
    fs_max = 0
    if tasks_dir.exists():
        for p in tasks_dir.glob(f"{id_prefix}*.md"):
            m = num_re.match(p.name)
            if m:
                fs_max = max(fs_max, int(m.group(1)))

    import time as _t

    sql = f"""
        INSERT INTO tasks (task_id, title, status, file_path, content_hash, mtime)
        SELECT printf('{id_prefix}%03d', MAX(n) + 1),
               '(reserving)', 'icebox',
               printf('docs/tasks/.reserve-{id_prefix}%d.tmp', MAX(n) + 1), '', 0
        FROM (
            SELECT COALESCE(MAX(CAST(SUBSTR(task_id, {substr_start}) AS INTEGER)), 0) AS n
            FROM tasks
            WHERE task_id LIKE ? AND SUBSTR(task_id, {substr_start}) GLOB '[0-9]*'
            UNION ALL SELECT ? AS n
        )
    """

    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            cur = conn.execute(sql, (like_pat, fs_max))
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


# Task-id allocator seam (ADR adr-task-id-allocator-seam). Each allocator mints
# the next id behind one interface; the id format stays TASK-<token>, so a future
# `forge` / `service` allocator drops in via the registry with zero migration and
# zero caller change. local + namespaced are offline; both reuse the atomic
# per-prefix counter, differing only in the prefix.
class _LocalAllocator:
    def allocate(self, conn: sqlite3.Connection, project_root: Path) -> str:
        return _allocate_with_prefix(conn, project_root, "TASK-")


class _NamespacedAllocator:
    def allocate(self, conn: sqlite3.Connection, project_root: Path) -> str:
        return _allocate_with_prefix(conn, project_root, "TASK-" + _namespace_segment(project_root))


_TASK_ID_ALLOCATORS: dict[str, object] = {
    "sequential": _LocalAllocator(),
    "local": _LocalAllocator(),
    "namespaced": _NamespacedAllocator(),
}


def _resolve_task_id_allocator(project_root: Path):
    try:
        from board_os.config import load_config

        scheme = getattr(load_config(project_root), "task_id_scheme", "sequential")
    except Exception as exc:
        logger.debug("allocator resolve fell back to local: %s", exc)
        scheme = "sequential"
    return _TASK_ID_ALLOCATORS.get(scheme, _TASK_ID_ALLOCATORS["sequential"])


def _next_task_id(conn: sqlite3.Connection, project_root: Path) -> str:
    return _resolve_task_id_allocator(project_root).allocate(conn, project_root)


# external_ref — optional bidirectional link to a forge issue/PR. Metadata only;
# never the task's canonical id (ADR adr-task-id-allocator-seam). Host is detected
# from the origin remote, so the kernel hardcodes no forge (P2).
def _detect_forge(project_root: Path) -> str:
    import subprocess

    try:
        url = (
            subprocess.run(
                ["git", "-C", str(project_root), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            .stdout.strip()
            .lower()
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    if "bitbucket" in url:
        return "bitbucket"
    return ""


def _normalize_external_ref(raw: str, project_root: Path) -> str | None:
    # Accepts a bare number, '#42', 'github#42', or a full issue/PR URL → returns
    # '<forge>#<n>' ('!' for a merge/pull request). Forge is taken from the ref
    # when explicit, else detected from origin; None when unparseable.
    import re as _re

    raw = (raw or "").strip()
    if not raw:
        return None
    m = _re.search(
        r"(github|gitlab|bitbucket)\.[^/]+/.+?/(?:issues|pull|-/issues|-/merge_requests|merge_requests)/(\d+)",
        raw,
    )
    if m:
        sep = "!" if "merge_request" in raw or "/pull/" in raw else "#"
        return f"{m.group(1)}{sep}{m.group(2)}"
    m = _re.match(r"^(github|gitlab|bitbucket)\s*([#!])\s*(\d+)$", raw, _re.IGNORECASE)
    if m:
        return f"{m.group(1).lower()}{m.group(2)}{m.group(3)}"
    m = _re.match(r"^([#!]?)(\d+)$", raw)
    if m:
        forge = _detect_forge(project_root)
        if not forge:
            return None
        sep = "!" if m.group(1) == "!" else "#"
        return f"{forge}{sep}{m.group(2)}"
    return None


def cos_task_link(conn: sqlite3.Connection, task_id: str, ref: str) -> dict:
    """Link a task to a forge issue/PR via the optional external_ref field."""
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return fail("not_found", f"task {task_id} not found")
    project_root = _project_root()
    file_path = project_root / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")
    normalized = _normalize_external_ref(ref, project_root)
    if not normalized:
        return fail(
            "validation",
            f"could not parse a forge ref from {ref!r} — use e.g. 42, github#42, or an issue URL",
        )
    patch_task_frontmatter_scalars(file_path, {"external_ref": normalized})
    return ok({"task_id": task_id, "external_ref": normalized, "meta": {"layer": "tasks"}})


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


def _status_dwell_seconds(now: float, started_at, last_transition_at) -> int | None:
    # Reuse the reclaim derivation (max of started_at and last transition) so
    # dwell, reclaim idle, and SLA staleness share one "last activity" definition.
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
    if config is None:
        return None
    policy = config.workflow_policy
    hours = {
        "in_progress": policy.in_progress_sla_hours,
        "testing": policy.testing_sla_hours,
        "blocked": policy.blocked_sla_hours,
    }.get(status)
    if hours is not None:
        return hours * 3600 if hours > 0 else None
    if status == "icebox":
        return policy.icebox_stale_days * 86400 if policy.icebox_stale_days > 0 else None
    return None


def _flag_stale(card: dict, config) -> dict:
    # Observability only — never mutates board state. Mutates the card dict in
    # place and returns it so callers can map over a list.
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
    # Detection lives in _agent_runtime.detect_agent so cli/board_commands.py and
    # this module share one code path; shell counterpart is core/hooks/cos-env.sh.
    from ._agent_runtime import detect_agent

    return detect_agent(agent_session)


def _resolve_attribution(agent_session: str | None) -> str | None:
    # Without this, task_status_history.agent_session is NULL and the board UI
    # renders the human "H" glyph for agent-driven creates. Reads $COS_SESSION_FILE
    # (set by every adapter via session-context.sh), so the fix is adapter-agnostic.
    from ._agent_runtime import resolve_agent_session

    return resolve_agent_session(agent_session)


def _assign_guard(
    file_path: Path | None,
    agent_session: str | None,
    force: bool,
) -> str | None:
    # Opt-in + backward-compatible: no `assignee:` field → movable by anyone.
    # When set, only that session (or any session of the same agent) may move it;
    # force=True or COS_ASSIGN_OVERRIDE=1 bypasses. Returns an error msg or None.
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
    # time dimension (status_dwell_seconds) — RC5 of the 2026-06-05
    # task-lifecycle review (TASK-210).
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
_BOARD_BUDGET_HEADROOM = 256


def _cap_board_to_budget(cards: list[dict], *, budget: int) -> tuple[list[dict], bool]:
    # Drop the lowest-priority cards (P9 last) until the serialized board body
    # fits `budget` (agent path only — the browser opts out via apply_budget=False).
    # The kept set preserves original display order. `cards` is outside the
    # envelope trim ladder, so without this cap a large board produced an
    # unshrinkable >32KB envelope (TASK-209). Returns (kept, capped). The board no
    # longer emits a duplicate `grouped` view (TASK-259) — clients group cards by
    # swimlane×status themselves, halving the payload on both the agent and wire.
    def _fits(subset: list[dict]) -> bool:
        # Mirror ok(): pretty-printed full envelope, measured with the same
        # _budget_size the trimmer uses (inflates non-Latin), so the cap holds
        # for Persian/Arabic titles too — not just ASCII.
        probe = json.dumps(
            {
                "ok": True,
                "data": {
                    "cards": subset,
                    "count": len(subset),
                    "total_count": len(cards),
                    "truncated": True,
                    "wip": {"counts": {}, "caps": {}, "violations": []},
                    "meta": {
                        "layer": "tasks",
                        "source": "board_os.cos_task_board",
                        "tokens_estimated": 0,
                        "truncated": True,
                    },
                },
            },
            indent=2,
            default=str,
        )
        return _budget_size(probe) <= budget

    if _fits(cards):
        return cards, False

    total = len(cards)
    ranked = sorted(range(total), key=lambda i: (str(cards[i].get("priority", "P9")), i))
    keep = total
    while keep > 0:
        keep = keep - 1 if keep <= 12 else int(keep * 0.85)
        keep_idx = set(ranked[:keep])
        subset = [c for i, c in enumerate(cards) if i in keep_idx]
        if _fits(subset):
            return subset, True
    return [], True


# Columns whose row count grows without bound (finished work accumulates
# forever). These are keyset-paginated; every other column is "active" and
# returned in full up to a safety cap. TASK-223.
_PAGED_STATUSES = ("complete", "archive")
# Safety cap on each active board read so even a runaway icebox can't OOM the
# response. Honest truncation is signalled via columns["_active"].
_ACTIVE_COLUMN_HARD_MAX = 2000
# Hard ceiling on one keyset page of a paged column.
_PAGE_SIZE_HARD_MAX = 200


# Cursor schema version — bump when the keyset key changes. A versioned
# cursor from an older schema decodes to None (page 1) instead of silently
# slicing the wrong key (TASK-399).
_BOARD_CURSOR_VERSION = "v1"


def _encode_board_cursor(completed_at: int | None, task_id: str) -> str:
    raw = json.dumps([_BOARD_CURSOR_VERSION, completed_at, task_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_board_cursor(cursor: str | None) -> tuple[int | None, str] | None:
    if not cursor:
        return None
    try:
        version, completed_at, task_id = json.loads(
            base64.urlsafe_b64decode(cursor.encode("ascii"))
        )
        if version != _BOARD_CURSOR_VERSION:
            return None
        return completed_at, str(task_id)
    except Exception:
        return None


def _keyset_filter(cursor: str | None) -> tuple[str, list]:
    # Rows strictly AFTER the cursor in (completed_at DESC, task_id DESC) order;
    # NULL completed_at (archive rows) sort last.
    decoded = _decode_board_cursor(cursor)
    if decoded is None:
        return "", []
    completed_at, task_id = decoded
    if completed_at is None:
        # Inside the NULL-completed tail (archive): tiebreak by task_id only.
        return "completed_at IS NULL AND task_id < ?", [task_id]
    # Lower completed_at, or same completed_at + lower task_id, or the NULL tail.
    return (
        "(completed_at < ? OR (completed_at = ? AND task_id < ?) OR completed_at IS NULL)",
        [completed_at, completed_at, task_id],
    )


def _keyset_column_page(
    conn: sqlite3.Connection,
    status: str,
    base_clauses: list[str],
    base_params: list,
    cursor: str | None,
    page_size: int,
    config,
) -> tuple[list[dict], str | None, int]:
    page_size = max(1, min(int(page_size), _PAGE_SIZE_HARD_MAX))
    col_clauses = list(base_clauses) + ["status = ?"]
    col_params = list(base_params) + [status]

    total = conn.execute(
        f"SELECT COUNT(*) FROM tasks WHERE {' AND '.join(col_clauses)}", col_params
    ).fetchone()[0]

    ks_clause, ks_params = _keyset_filter(cursor)
    where = " AND ".join(col_clauses + ([ks_clause] if ks_clause else []))
    query = f"{_BOARD_SELECT} WHERE {where} ORDER BY completed_at DESC, task_id DESC LIMIT ?"
    rows = conn.execute(query, col_params + ks_params + [page_size + 1]).fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    cards = [_flag_stale(_task_card(r), config) for r in rows]

    next_cursor = None
    if has_more and cards:
        # Read the keyset key from the shaped card (named fields) instead of
        # positional row indexes — a _BOARD_SELECT column shuffle can no
        # longer silently corrupt pagination.
        last = cards[-1]
        next_cursor = _encode_board_cursor(last.get("completed_at"), last["id"])
    return cards, next_cursor, total


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
    page_size: int = 50,
    cursor: str | None = None,
    apply_budget: bool = True,
) -> str:
    config = _current_config()

    base_clauses: list[str] = []
    base_params: list = []
    for col, val in (("swimlane", swimlane), ("kind", kind), ("epic", epic)):
        if val:
            base_clauses.append(f"{col} = ?")
            base_params.append(val)

    # Split requested columns into ACTIVE (returned in full, capped) and PAGED
    # (complete/archive — keyset-paginated so a 50K-deep column never floods the
    # payload). Supersedes the interim apply_budget return-all (TASK-220/223).
    paged_set = set(_PAGED_STATUSES)
    if status_filter:
        active_statuses = [s for s in status_filter if s not in paged_set]
        paged_statuses = [s for s in status_filter if s in paged_set]
        want_active = bool(active_statuses)
    else:
        active_statuses = None  # all non-paged statuses, single query
        paged_statuses = list(_PAGED_STATUSES) if include_archive else []
        want_active = True

    columns_meta: dict = {}
    cards: list[dict] = []

    # ---- Active columns: full, bounded by a safety cap ----
    if want_active:
        active_cap = max(1, min(int(limit), _ACTIVE_COLUMN_HARD_MAX))
        a_clauses = list(base_clauses)
        a_params = list(base_params)
        if active_statuses:
            ph = ",".join("?" for _ in active_statuses)
            a_clauses.append(f"status IN ({ph})")
            a_params.extend(active_statuses)
        else:
            a_clauses.append("status NOT IN ('complete', 'archive')")
        where = f"WHERE {' AND '.join(a_clauses)}" if a_clauses else ""
        query = f"{_BOARD_SELECT} {where} ORDER BY swimlane, status, priority LIMIT ?"
        a_rows = conn.execute(query, a_params + [active_cap + 1]).fetchall()
        active_truncated = len(a_rows) > active_cap
        a_rows = a_rows[:active_cap]
        cards.extend(_flag_stale(_task_card(r), config) for r in a_rows)
        if active_truncated:
            columns_meta["_active"] = {"truncated": True, "cap": active_cap}

    # ---- Paged columns: one keyset page each (cursor + per-column total) ----
    for status in paged_statuses:
        page_cards, next_cursor, col_total = _keyset_column_page(
            conn, status, base_clauses, base_params, cursor, page_size, config
        )
        cards.extend(page_cards)
        columns_meta[status] = {
            "total_count": col_total,
            "returned": len(page_cards),
            "next_cursor": next_cursor,
            "truncated": next_cursor is not None,
        }

    # Per-column queries make the payload inherently bounded. apply_budget still
    # applies the 32KB agent-context cap (a board read must never flood an
    # agent's context); the browser passes apply_budget=False and is safe now
    # that no single column returns more than its cap/page.
    total_count = len(cards)
    if apply_budget:
        # Account for the columns meta (not in _cap_board_to_budget's probe) so
        # the 32KB agent-envelope guarantee (TASK-209) holds even with paging.
        columns_overhead = len(json.dumps(columns_meta, default=str)) if columns_meta else 0
        cards, board_truncated = _cap_board_to_budget(
            cards, budget=TOKEN_BUDGET_CHARS - _BOARD_BUDGET_HEADROOM - columns_overhead
        )
    else:
        board_truncated = False

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
            "cards": cards,
            "columns": columns_meta,
            "count": len(cards),
            "total_count": total_count,
            "truncated": board_truncated,
            "wip": wip_state,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_board"},
        # Browser path (apply_budget=False) opts out of the 32KB agent cap in
        # ok() too — not just _cap_board_to_budget above — so a large board never
        # trips envelope_unshrinkable on the wire. The agent path keeps the cap.
        apply_budget=apply_budget,
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
        "SELECT task_id, title, status, swimlane, kind, priority, appetite, "
        "file_path, epic, labels_json, agent_session, started_at, completed_at "
        "FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")
    try:
        labels = json.loads(row[9] or "[]")
    except (TypeError, json.JSONDecodeError):
        labels = []
    data = {
        "id": row[0],
        "title": row[1],
        "status": row[2],
        "swimlane": row[3],
        "kind": row[4],
        "priority": row[5],
        "appetite": row[6],
        "file_path": row[7],
        # Fields the DB already stores but the tool used to drop, forcing callers
        # to re-parse the raw body. depends_on/blocked_by/references stay
        # frontmatter-only and remain available in `body`.
        "epic": row[8],
        "labels": labels,
        "agent_session": row[10],
        "started_at": row[11],
        "completed_at": row[12],
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


_TERMINAL_DEP_STATES = ("archive",)


def cascade_ready_dependents(
    conn: sqlite3.Connection,
    completed_task_id: str,
    *,
    agent_session: str | None = None,
) -> dict[str, list]:
    """Auto-ready every dependent of `completed_task_id` now unblocked + DoR-complete.

    Run after a task transitions to `complete`. Each dependent is classified:
    `readied` (all deps complete AND body DoR met — the ready label is added,
    moving blocked→icebox first), `needs_authoring` (all deps complete but the
    body DoR is incomplete — surfaced, not silently hidden), or `still_blocked`
    (another dep is open, or a dep is archived/cancelled — left blocked with a
    reason instead of hanging). Already-ready or active dependents are skipped.
    """
    report: dict[str, list] = {"readied": [], "needs_authoring": [], "still_blocked": []}
    project_root = _project_root()
    for dependent_id in dependents_of(conn, completed_task_id):
        row = conn.execute(
            "SELECT status, file_path, labels_json FROM tasks WHERE task_id = ?",
            (dependent_id,),
        ).fetchone()
        if row is None:
            continue
        status = str(row[0])
        # Only backlog cards are cascade targets; an active/done card is the
        # owning session's concern, never auto-mutated here.
        if status not in ("icebox", "blocked"):
            continue
        if READY_LABEL in _labels_list_from_json(row[2]):
            continue

        pending = incomplete_dependencies(conn, dependent_id)
        if pending:
            terminal = [
                dep
                for dep in pending
                if (
                    conn.execute("SELECT status FROM tasks WHERE task_id = ?", (dep,)).fetchone()
                    or (None,)
                )[0]
                in _TERMINAL_DEP_STATES
            ]
            reason = (
                f"dependency terminal-failed (archived): {', '.join(terminal)}"
                if terminal
                else f"still waiting on: {', '.join(pending)}"
            )
            report["still_blocked"].append({"task_id": dependent_id, "reason": reason})
            continue

        # All deps complete. Gate on the body DoR before auto-readying so the
        # cascade never marks an unauthored stub pullable.
        file_path = project_root / row[1] if row[1] else None
        dor_gaps: list[dict[str, str]] = []
        if file_path is not None and file_path.exists():
            dor_gaps, _ = _ready_dor_check(file_path, agent_session)
        if dor_gaps:
            report["needs_authoring"].append({"task_id": dependent_id, "dor": dor_gaps})
            continue

        # blocked must return to icebox before it can carry the ready label and
        # be pulled (blocked→in_progress skips the icebox ready gate otherwise).
        if status == "blocked":
            move_env = json.loads(
                cos_task_move(conn, task_id=dependent_id, to="icebox", agent_session=agent_session)
            )
            if not move_env.get("ok"):
                report["still_blocked"].append(
                    {"task_id": dependent_id, "reason": "could not unblock to icebox"}
                )
                continue
        ready_env = json.loads(
            cos_task_ready(conn, task_id=dependent_id, agent_session=agent_session)
        )
        if ready_env.get("ok"):
            report["readied"].append(dependent_id)
        else:
            report["still_blocked"].append(
                {"task_id": dependent_id, "reason": "ready label add failed"}
            )
    return report


def _cascade_ready_dependents_safe(
    conn: sqlite3.Connection, task_id: str, agent_session: str | None
) -> dict[str, list]:
    # Fire-and-forget: the completion itself already committed; a cascade
    # failure must never turn a successful close into an error.
    try:
        return cascade_ready_dependents(conn, task_id, agent_session=agent_session)
    except Exception as exc:  # noqa: BLE001 - fire-and-forget
        logger.debug("dependent cascade after %s complete failed: %s", task_id, exc)
        return {"readied": [], "needs_authoring": [], "still_blocked": []}


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
        elif to == "complete" and not bypass_gates and not force:
            # Fail CLOSED when the file is gone: the DoD gate can't run, and a
            # silent skip would close an unverifiable task (TASK-532).
            return fail(
                "validation",
                f"task file not found — cannot verify DoD: {row[0]}. Re-materialize "
                "the task file before closing (it desynced from the DB).",
            )

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
        cascade = _cascade_ready_dependents_safe(conn, task_id, agent_session)
        if any(cascade.values()):
            data["cascade"] = cascade

    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_move"})


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


# ---------- cos_task_reclaim (zombie in_progress recovery) ----------


def _active_session_ids(now: float, window: int = 1800) -> set[str]:
    # Reads agent-presence JSON under $COS_STATE_DIR/<agent>/sessions/*.json
    # (written by agent-presence.sh). Missing/unreadable presence → "no active
    # sessions", so reclaim falls back to the idle-only signal.
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
    # None = unverifiable (no git / error) so callers fail SAFE — treat as "has
    # evidence", never auto-reclaim on a signal we couldn't check. Trailing
    # non-digit boundary stops TASK-215 also matching TASK-2155.
    import subprocess

    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "log",
                "--all",
                "-E",
                f"--max-count={_COMMIT_SCAN_CAP}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--oneline",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return sum(1 for line in out.stdout.splitlines() if line.strip())


# Cap on how many matching commits git enumerates per scan — bounds the history
# walk at 1M+ commits. Reconciliation only needs "0 vs >0" evidence, so a count
# capped at this value is sufficient (and reported as "at least N"). TASK-227.
_COMMIT_SCAN_CAP = 500
# Cap on a single reclaim/reconcile sweep — the rest drains on the next run.
_STRANDED_SCAN_LIMIT = 1000


def _commits_referencing_batch(task_ids: list[str], project_root: Path) -> dict[str, int | None]:
    # One history walk for many ids — replaces N per-task subprocesses. All-None
    # when git is unavailable so callers fail SAFE (unverifiable = has evidence).
    import re
    import subprocess

    ids = [t for t in dict.fromkeys(task_ids) if t]
    if not ids:
        return {}
    counts: dict[str, int | None] = {tid: 0 for tid in ids}
    grep_args: list[str] = []
    for tid in ids:
        grep_args += ["--grep", f"{tid}([^0-9]|$)"]
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "log",
                "--all",
                "-E",
                f"--max-count={_COMMIT_SCAN_CAP}",
                *grep_args,
                "--format=%s",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return {tid: None for tid in ids}
    if out.returncode != 0:
        return {tid: None for tid in ids}
    patterns = {tid: re.compile(re.escape(tid) + r"([^0-9]|$)") for tid in ids}
    for line in out.stdout.splitlines():
        for tid, pat in patterns.items():
            if pat.search(line):
                counts[tid] += 1
    return counts


def _has_work_log(work_log_json: object) -> bool:
    try:
        return bool(json.loads(work_log_json or "[]"))
    except (json.JSONDecodeError, TypeError):
        return False


def _classify_stranded(status: str, commits: int | None, has_work_log: bool) -> str:
    # commits is None = unverifiable (no git / error) — counted AS evidence so a
    # task is never called abandoned on a signal we couldn't check.
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
    default_threshold_h = (
        idle_hours
        if idle_hours is not None
        else (config.workflow_policy.reclaim_idle_hours if config is not None else 24)
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
        "FROM tasks WHERE status IN ('in_progress', 'testing', 'emergency') "
        "ORDER BY started_at LIMIT ?",
        (_STRANDED_SCAN_LIMIT,),
    ).fetchall()
    # Batch the per-testing-task git lookup into ONE history walk (was N
    # subprocesses, each O(history) at 1M commits). TASK-227.
    commits_by_task = _commits_referencing_batch(
        [r[0] for r in rows if r[4] == "testing"], project_root
    )

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
            commits = commits_by_task.get(task_id)
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
            reclaimed.append(
                {
                    "task_id": task_id,
                    "previous_owner": owner,
                    "idle_hours": idle_h,
                    "from_status": status,
                    "to_status": dest,
                }
            )
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
            reclaimed.append(
                {
                    "task_id": task_id,
                    "previous_owner": owner,
                    "idle_hours": idle_h,
                    "from_status": status,
                    "to_status": dest,
                }
            )

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
        "ORDER BY status DESC, task_id LIMIT ?",
        (_STRANDED_SCAN_LIMIT,),
    ).fetchall()
    # Pre-filter to the rows we'll actually triage (default = stranded only),
    # then batch the git lookup into ONE history walk instead of one subprocess
    # per row. TASK-227.
    triaged = [r for r in rows if include_active or not (r[1] and r[1] in active)]
    commits_by_task = _commits_referencing_batch([r[0] for r in triaged], project_root)
    items: list[dict] = []
    for task_id, owner, status, started_at, work_log, last_tx in triaged:
        owner_active = bool(owner and owner in active)
        commits = commits_by_task.get(task_id)
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
    # OFF by default: runs only when a status's *_auto_archive_days knob is > 0,
    # so a fresh project never silently deletes backlog. keep/parked labels exempt
    # a card; archive is reversible (archive->icebox is legal). Fail-soft per card.
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
            "FROM tasks WHERE status = ? "
            "ORDER BY started_at ASC LIMIT ?",  # oldest first; rest drains next run
            (status, _STRANDED_SCAN_LIMIT),
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
    #
    # Dependency filter: a ready icebox card with any prerequisite that is not
    # `complete` isn't runnable now, so it's excluded via NOT EXISTS over the
    # indexed task_dependencies junction (a missing dep row — never synced —
    # has no status and counts as incomplete). emergency cards are unaffected.
    # Guarded on the junction existing so a pre-v35 DB still returns candidates.
    if _has_task_dependencies_table(conn):
        ready_clause = (
            "(status = 'icebox' AND labels_json LIKE '%\"ready\"%' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM task_dependencies d "
            "  LEFT JOIN tasks dep ON dep.task_id = d.depends_on "
            "  WHERE d.task_id = tasks.task_id "
            "    AND (dep.status IS NULL OR dep.status != 'complete')))"
        )
    else:
        ready_clause = "(status = 'icebox' AND labels_json LIKE '%\"ready\"%')"
    clauses = [f"(status = 'emergency' OR {ready_clause})"]
    params: list = []
    if swimlane:
        clauses.append("swimlane = ?")
        params.append(swimlane)
    # Bounded: highest-priority candidates first, capped — pick only needs the
    # top max_candidates, and the cap keeps a 10K-ready icebox from a full load.
    query = f"{_BOARD_SELECT} WHERE {' AND '.join(clauses)} ORDER BY priority LIMIT 1000"
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


# ---------- cos_task_claim_next ----------


@safe_tool
def cos_task_claim_next(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    priority_min: str = "P2",
    agent_session: str | None = None,
) -> str:
    """Atomically claim the highest-priority runnable task for this session.

    Select + claim in ONE step so N racing sessions each get a DISTINCT task or
    ``{claimed: null}`` — never the same task twice, never an exception. Reuses
    cos_task_pick (dependency-filtered, priority-ordered) for candidates, then
    walks them attempting an atomic ``→ in_progress`` move: transition's
    BEGIN IMMEDIATE + CAS ``WHERE status = <expected>`` lets exactly one session
    win each row; a loser's CAS-miss (category `transient`) is skipped to the
    next candidate. A per-session WIP-cap rejection stops the walk — this session
    is already at its focus limit — and returns ``{claimed: null}``.
    """
    agent_session = _resolve_attribution(agent_session)
    config = _current_config()

    # A wider window than max_candidates: under contention the top few rows may
    # all be claimed by peers before this session wins one, so scan deeper.
    pick_env = json.loads(
        cos_task_pick(conn, swimlane=swimlane, priority_min=priority_min, max_candidates=50)
    )
    if not pick_env.get("ok"):
        return fail("internal", "claim-next could not enumerate candidates")
    candidates = pick_env["data"]["candidates"]

    for card in candidates:
        expected_from = card["status"]  # 'icebox' (ready) or 'emergency'
        result = transition(
            conn,
            card["id"],
            "in_progress",
            reason="claim-next",
            agent_session=agent_session,
            expected_from=expected_from,
            config=config,
            file_path=_resolve_task_file(conn, card["id"]),
        )
        if result.ok:
            claimed = json.loads(cos_task_show(conn, task_id=card["id"]))
            return ok(
                {"claimed": claimed.get("data") if claimed.get("ok") else {"id": card["id"]}},
                meta={"layer": "tasks", "source": "board_os.cos_task_claim_next"},
            )
        # A peer beat us to this row (CAS miss / status changed) — try the next.
        if result.error_category == "transient":
            continue
        # WIP cap or a hard gate: this session can't take on more work now.
        break

    return ok(
        {"claimed": None},
        meta={"layer": "tasks", "source": "board_os.cos_task_claim_next"},
    )


def _resolve_task_file(conn: sqlite3.Connection, task_id: str) -> Path | None:
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row or not row[0]:
        return None
    candidate = _project_root() / row[0]
    return candidate if candidate.exists() else None


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

    # Bounded standup queries (TASK-227): a 24h window or a runaway icebox must
    # not fetchall unboundedly. Active columns are WIP-small; icebox uses an
    # accurate COUNT + a bounded oldest-first sample for the stale preview.
    # Standup highlights only — most-recent N transitions, not the full window
    # (an unbounded list both OOMs at scale and blows the 32KB agent envelope).
    recent = conn.execute(
        "SELECT task_id, old_status, new_status, reason, transitioned_at "
        "FROM task_status_history "
        "WHERE transitioned_at >= ? "
        "ORDER BY transitioned_at DESC LIMIT 50",
        (threshold,),
    ).fetchall()

    in_progress = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'in_progress' ORDER BY priority LIMIT 200"
    ).fetchall()
    # `testing` was previously absent from daily — the protocol funnels work
    # there before completion, so an abandoned card most often rots in testing
    # (RC3). Report it so a stranded testing zombie is visible at standup.
    testing = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'testing' ORDER BY priority LIMIT 200"
    ).fetchall()
    blocked = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'blocked' ORDER BY priority LIMIT 200"
    ).fetchall()
    icebox_total = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'icebox'").fetchone()[0]
    icebox = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'icebox' ORDER BY last_transition_at ASC LIMIT 500"
    ).fetchall()

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
        "total": icebox_total,  # accurate count; cards below are a bounded sample
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
def cos_task_retro(
    conn: sqlite3.Connection,
    *,
    since: str = "7d",
    page_size: int = 25,
    cursor: str = "",
) -> str:
    hours = _parse_since(since)
    threshold = int(time.time() - hours * 3600)

    # Aggregates over the WHOLE window via a slim projection — serializing
    # every full card blew the 32k envelope budget at ~270 completions
    # (observed 178k, envelope_unshrinkable).
    window_rows = conn.execute(
        "SELECT swimlane, started_at, completed_at FROM tasks "
        "WHERE status = 'complete' AND completed_at >= ?",
        (threshold,),
    ).fetchall()

    cycle_times_min = [
        (done - started) / 60.0 for _, started, done in window_rows if started and done
    ]
    avg_cycle = (sum(cycle_times_min) / len(cycle_times_min)) if cycle_times_min else None

    per_lane: dict[str, int] = {}
    for lane, _, _ in window_rows:
        per_lane[lane or "(none)"] = per_lane.get(lane or "(none)", 0) + 1

    emergency_count = conn.execute(
        "SELECT COUNT(*) FROM task_status_history "
        "WHERE new_status = 'emergency' AND transitioned_at >= ?",
        (threshold,),
    ).fetchone()[0]

    # Highlights page — same keyset machinery as the board's complete column,
    # trimmed to digest fields (the long tail rides the cursor).
    cards, next_cursor, total = _keyset_column_page(
        conn,
        "complete",
        ["completed_at >= ?"],
        [threshold],
        cursor or None,
        page_size,
        _current_config(),
    )
    digest_fields = ("id", "title", "swimlane", "kind", "priority", "completed_at")
    completed = [{k: c.get(k) for k in digest_fields} for c in cards]

    return ok(
        {
            "completed": completed,
            "completed_count": total,
            "cycle_time_avg_minutes": avg_cycle,
            "emergency_count": emergency_count,
            "swimlane_throughput": per_lane,
            "next_cursor": next_cursor,
        },
        meta={
            "layer": "tasks",
            "source": "board_os.cos_task_retro",
            "truncated": bool(next_cursor),
        },
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


_WORKLOG_SUMMARY_CAP = 120


def _truncate_summary(text: str, cap: int = _WORKLOG_SUMMARY_CAP) -> str:
    # Trim at the last word boundary within the cap and mark the loss with a
    # single ellipsis, so a long note reads as deliberately shortened rather
    # than silently chopped mid-word. The ellipsis counts toward the cap, so
    # the returned string is always <= cap (the documented Work Log contract).
    flat = text.strip().replace("\n", " ")
    if len(flat) <= cap:
        return flat
    clipped = flat[: cap - 1].rstrip()
    boundary = clipped.rfind(" ")
    if boundary > 0:
        clipped = clipped[:boundary].rstrip()
    return f"{clipped}…"


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
    summary_trunc = _truncate_summary(summary)
    line = f"- {date} [{agent_label}]: {summary_trunc}"

    content = file_path.read_text(encoding="utf-8")
    marker = "## Work Log"
    # Match the heading anchored at line start, not a `## Work Log` mention
    # inside prose (e.g. an Acceptance bullet) which a plain substring search
    # would hit first — landing the entry ABOVE the real section.
    head = re.search(r"(?m)^## Work Log[ \t]*$", content)
    if head is None:
        # Append a Work Log section at the end.
        new_content = content.rstrip() + f"\n\n{marker}\n{line}\n"
    else:
        # Insert at the end of the Work Log section (before the next H2
        # heading if any, else at EOF), both anchored at line start.
        nxt = re.search(r"(?m)^## ", content[head.end() :])
        insert_at = head.end() + nxt.start() if nxt else len(content)
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


def _git_commits_by_task_id(task_id: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Actor-agnostic retroactive link: matches commits by message regardless of
    # source (Hub/terminal/human), without session state or a touch of the .md.
    # The `([^0-9]|$)` guard stops TASK-5 matching TASK-50.
    import subprocess

    if not task_id:
        return []
    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--all",
                "-E",
                f"-n{limit}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--format=%H%x1f%ct%x1f%s",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --grep failed for %s: %s", task_id, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        if sha[:10] in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


def _git_commits_from_worklog(rel_path: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Links work-log SHAs that never touched the .md. Validated in ONE indexed
    # `git cat-file` batch (only type `commit` survives) instead of a per-token
    # `git show` that can stall the loop and false-match a date↔short-sha collision.
    import re as _re
    import subprocess

    root = _project_root()
    try:
        text = (Path(root) / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    cands: list[str] = []
    seen: set[str] = set()
    for cand in _re.findall(r"\b[0-9a-f]{7,40}\b", text):
        if cand in seen:
            continue
        seen.add(cand)
        cands.append(cand)
        if len(cands) >= limit:
            break
    if not cands:
        return []

    try:
        batch = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch-check"],
            input="\n".join(cands),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git cat-file failed for %s: %s", rel_path, exc)
        return []
    if batch.returncode != 0:
        return []

    # Hit line: "<full-objectname> <type> <size>". Miss/ambiguous line:
    # "<input> missing" / "<input> ambiguous" — type slot is not "commit".
    commit_shas = [
        parts[0]
        for parts in (line.split() for line in batch.stdout.splitlines())
        if len(parts) >= 2 and parts[1] == "commit"
    ]
    if not commit_shas:
        return []

    try:
        res = subprocess.run(
            ["git", "-C", str(root), "log", "--no-walk", "--format=%H%x1f%ct%x1f%s", *commit_shas],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --no-walk failed for %s: %s", rel_path, exc)
        return []
    if res.returncode != 0:
        return []

    out: list[dict] = []
    for raw in res.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        full, ct, subject = parts
        short = full[:10]
        if short in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        out.append({"sha": short, "subject": subject, "at": at})
        exclude.add(short)
    return out


def _worklog_events(rel_path: str) -> list[dict]:
    # Parse Work Log bullets into timeline events so History and Work Log read as
    # one chronological story instead of two overlapping surfaces.
    import re as _re
    from datetime import datetime, timezone

    root = _project_root()
    try:
        text = (Path(root) / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    parsed = parse_task(text)
    if parsed is None:
        return []
    line_re = _re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*\[([^\]]+)\]:\s*(.*)$")
    out: list[dict] = []
    for i, ln in enumerate(parsed.work_log_lines):
        m = line_re.match(ln.strip())
        if not m:
            continue
        date_s, actor, note = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            # +i keeps same-day bullets in file order under the chronological sort.
            at = (
                int(datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
                + i
            )
        except ValueError:
            at = 0
        out.append(
            {
                "type": "worklog",
                "at": at,
                "actor": {
                    "type": "human" if actor == "human" else "agent",
                    "id": actor,
                    "label": actor,
                },
                "text": note,
            }
        )
    return out


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

    if row[0]:
        events.extend(_worklog_events(row[0]))

    commits: list[dict] = []
    if include_commits and row[0]:
        commits = _git_commits_for_path(row[0], limit=limit)
        seen_shas = {c["sha"] for c in commits}
        for c in commits:
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )
        # Also surface commits referenced in the Work Log (the code commits that
        # did the work but never touched the md file) so they link WITHOUT a task
        # id in the commit message — the file-path link only catches md touches.
        for c in _git_commits_from_worklog(row[0], exclude=seen_shas, limit=limit):
            seen_shas.add(c["sha"])
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )
        # The robust, retroactive, actor-agnostic source: commits whose MESSAGE
        # names this task id (git log --all --grep). Catches Hub/terminal/human
        # commits the path + work-log sources miss when the id is in the subject.
        for c in _git_commits_by_task_id(task_id, exclude=seen_shas, limit=limit):
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


def _extract_worklog_section(body: str) -> str:
    head = re.search(r"(?m)^## Work Log[ \t]*$", body)
    if head is None:
        return ""
    nxt = re.search(r"(?m)^## ", body[head.end() :])
    end = head.end() + nxt.start() if nxt else len(body)
    return body[head.start() : end].rstrip("\n")


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
    if body is not None:
        incoming = body
        # The board editor strips the system-managed "## Work Log" section (it
        # renders in the History timeline) before PATCHing the body, so a
        # wholesale replace would silently delete it. Preserve it: if the
        # incoming body omits the section but the current one has it, re-append.
        if not _extract_worklog_section(incoming) and current_body:
            preserved = _extract_worklog_section(current_body)
            if preserved:
                incoming = incoming.rstrip("\n") + "\n\n" + preserved + "\n"
        if incoming.strip() != current_body.strip():
            import hashlib

            new_body = incoming
            _record_task_edit(
                conn,
                task_id=task_id,
                field="body",
                old=hashlib.sha1(current_body.encode("utf-8")).hexdigest()[:12],
                new=hashlib.sha1(incoming.encode("utf-8")).hexdigest()[:12],
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
    m = re.match(r"^(\d+)([mhdw])$", since)
    if not m:
        return 24.0
    n, unit = int(m.group(1)), m.group(2)
    return {"m": n / 60.0, "h": float(n), "d": n * 24.0, "w": n * 24.0 * 7.0}[unit]


# ---------- Cycle validation tool (exposed for hooks) ----------


def check_cycle(conn: sqlite3.Connection, task_id: str, new_deps: list[str]) -> list[str]:
    """Thin passthrough to workflow.validate_dependencies_no_cycle."""
    return validate_dependencies_no_cycle(conn, task_id, new_deps)
