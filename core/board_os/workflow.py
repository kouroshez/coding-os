"""board-os workflow engine — Phase L.2 state machine + WIP enforcement.

One module, one SSOT for:
- Valid status transitions (8-state machine, plan §6.4)
- WIP cap enforcement (plan §3 P-L-3, config-driven)
- Atomic frontmatter writes (temp file + rename)
- task_status_history auditing
- Optimistic concurrency (plan §17, R-L-29 DFS cycle check)

Public API:
    transition(conn, task_id, to_status, *, reason, agent_session,
               expected_from=None, bypass_wip=False) -> TransitionResult
    check_wip(conn, config) -> WipState
    validate_dependencies_no_cycle(conn, task_id, new_deps) -> list[str]
    patch_task_frontmatter_scalars(path, updates) -> None
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
import yaml

from core.board_os.config import STATUS_ENUM, ScrumbanConfig

logger = logging.getLogger("coding_os.board_os.workflow")


# Valid transition edges: {from_status: {to_statuses}}
# "ready" was a dedicated column in earlier versions — it has been folded
# into an `icebox + "ready" label` combination so the board has one less
# queue and "ready" becomes something the agent tags rather than a
# destination to drag tasks into.  Any legacy task still carrying
# status='ready' is migrated to 'icebox' via _migrate_v19_drop_ready_status.
# archive is *soft-terminal*: the only way out is back to icebox or complete,
# which is how a user recovers from an accidental archive.  Any other target
# requires an explicit --force flag (workflow.transition(..., force=True)) so
# mis-clicks still surface an error, but a human can always self-correct.
_VALID_TRANSITIONS: dict[str, set[str]] = {
    "icebox": {"in_progress", "emergency", "archive"},
    "emergency": {"in_progress", "icebox"},
    "in_progress": {"testing", "blocked", "icebox", "emergency", "complete"},
    "testing": {"complete", "in_progress", "blocked"},
    "complete": {"archive"},
    "blocked": {"in_progress", "emergency", "icebox"},
    "archive": {"icebox", "complete"},  # un-archive paths (see note above)
}

# Statuses that count toward the WIP cap for a given column.
_WIP_COLUMN_MAP: dict[str, str] = {
    "in_progress": "in_progress",
    "testing": "testing",
    "emergency": "emergency",
}


@dataclass(frozen=True)
class TransitionResult:
    ok: bool
    task_id: str
    previous_status: str | None
    new_status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)
    wip_state: dict[str, int] = field(default_factory=dict)
    error: str | None = None
    error_category: str | None = None


@dataclass(frozen=True)
class WipState:
    """Current WIP counts vs. configured caps per column."""

    counts: dict[str, int]
    caps: dict[str, int]
    violations: tuple[str, ...]

    def violates(self, column: str) -> bool:
        cap = self.caps.get(column)
        return cap is not None and self.counts.get(column, 0) >= cap


class TransitionError(ValueError):
    """Raised on invalid transitions. Carries suggested paths."""

    def __init__(
        self,
        message: str,
        *,
        task_id: str,
        from_status: str,
        to_status: str,
        suggested: list[str] | None = None,
    ) -> None:
        self.task_id = task_id
        self.from_status = from_status
        self.to_status = to_status
        self.suggested = suggested or []
        super().__init__(message)


# ---------- Public API ----------


def check_wip(conn: sqlite3.Connection, config: ScrumbanConfig) -> WipState:
    counts: dict[str, int] = {}
    for status in _WIP_COLUMN_MAP.values():
        row = conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)
        ).fetchone()
        counts[status] = int(row[0]) if row else 0
    caps = {
        "in_progress": config.wip_limits.in_progress,
        "testing": config.wip_limits.testing,
        "emergency": config.wip_limits.emergency,
    }
    violations = tuple(col for col in caps if counts.get(col, 0) > caps[col])
    return WipState(counts=counts, caps=caps, violations=violations)


def validate_dependencies_no_cycle(
    conn: sqlite3.Connection, task_id: str, new_deps: list[str]
) -> list[str]:
    """DFS on existing dependency graph + proposed new deps. R-L-29.

    Returns a list of cycle paths (empty if no cycle). Caller decides
    whether to reject the edit (hook does).
    """
    deps_by_task: dict[str, list[str]] = {}
    for row in conn.execute("SELECT task_id, dependencies FROM tasks"):
        if row[0] == task_id:
            continue
        raw = row[1] or ""
        # Dependencies may be stored as JSON (new style) or as a
        # newline/comma-separated string (legacy). Handle both.
        parsed_deps: list[str] = []
        if isinstance(raw, str) and raw.strip():
            text = raw.strip()
            if text.startswith("["):
                try:
                    parsed_deps = [str(d) for d in json.loads(text)]
                except json.JSONDecodeError:
                    parsed_deps = []
            else:
                import re as _re
                parsed_deps = _re.findall(r"TASK-\d+", text)
        deps_by_task[row[0]] = parsed_deps
    deps_by_task[task_id] = list(new_deps)

    cycles: list[str] = []
    visited: set[str] = set()
    stack: list[str] = []

    def dfs(node: str) -> None:
        if node in stack:
            cycle = stack[stack.index(node):] + [node]
            cycles.append(" → ".join(cycle))
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for dep in deps_by_task.get(node, []):
            dfs(dep)
        stack.pop()

    dfs(task_id)
    return cycles


def transition(
    conn: sqlite3.Connection,
    task_id: str,
    to_status: str,
    *,
    reason: str | None = None,
    agent_session: str | None = None,
    expected_from: str | None = None,
    bypass_wip: bool = False,
    force: bool = False,
    config: ScrumbanConfig | None = None,
    file_path: Path | None = None,
) -> TransitionResult:
    """
    PURPOSE:      Central state machine for every Scrumban transition.
    INPUT:        open DB conn; task_id; target status; optional reason,
                  agent_session, expected_from (optimistic concurrency),
                  bypass_wip flag, force (skip state-machine validation for
                  human self-correction), ScrumbanConfig, and explicit
                  file_path.
    OUTPUT:       TransitionResult with ok + previous_status + new_status.
                  On validation/WIP/cycle errors → ok=False with
                  error_category ∈ {validation, transient, unavailable}.
                  `warnings` includes a `forced-transition` line whenever
                  force=True skipped a rule so the audit trail is explicit.
    DEPENDENCIES: tasks table (v6 + v13 cols), task_status_history table,
                  core.board_os.config.ScrumbanConfig.
    NOTES:        Writes MD frontmatter via atomic rename (temp + rename).
                  If file_path is None, the DB-level status is updated
                  but no MD write happens — used by tests + migrations.
                  force also implies bypass_wip so a single flag covers
                  "just let me drag this where I want".
    """
    if force:
        bypass_wip = True
    if to_status not in STATUS_ENUM:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=None,
            new_status=to_status,
            error=f"unknown status {to_status!r}; must be one of {sorted(STATUS_ENUM)}",
            error_category="validation",
        )

    row = conn.execute(
        "SELECT status, file_path, agent_session FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=None,
            new_status=to_status,
            error=f"task {task_id} not found",
            error_category="not_found",
        )

    current_status = str(row[0])
    current_file_path = row[1]

    # Optimistic concurrency — R-L-29.
    if expected_from and current_status != expected_from:
        return TransitionResult(
            ok=False,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            error=(
                f"status changed under us: expected {expected_from!r}, "
                f"current {current_status!r}"
            ),
            error_category="transient",
        )

    if to_status == current_status:
        return TransitionResult(
            ok=True,
            task_id=task_id,
            previous_status=current_status,
            new_status=to_status,
            warnings=("no-op (already in that status)",),
        )

    valid_next = _VALID_TRANSITIONS.get(current_status, set())
    forced_warning: str | None = None
    if to_status not in valid_next:
        if not force:
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error=(
                    f"invalid transition {current_status!r} → {to_status!r}; "
                    f"valid: {sorted(valid_next) or ['(terminal)']}. "
                    "Pass force=True (or `cos task-move --force`) to override."
                ),
                error_category="validation",
            )
        forced_warning = (
            f"forced-transition {current_status!r} → {to_status!r} "
            f"(state machine disallows this; recorded in history)"
        )

    # WIP enforcement
    wip_state: dict[str, int] = {}
    if config is not None and not bypass_wip:
        target_col = _WIP_COLUMN_MAP.get(to_status)
        if target_col:
            state = check_wip(conn, config)
            wip_state = dict(state.counts)
            cap = state.caps.get(target_col)
            if cap is not None and state.counts.get(target_col, 0) >= cap:
                env_bypass = os.environ.get("COS_WIP_OVERRIDE") == "1"
                if not env_bypass:
                    return TransitionResult(
                        ok=False,
                        task_id=task_id,
                        previous_status=current_status,
                        new_status=to_status,
                        error=(
                            f"WIP cap reached for {target_col}: "
                            f"{state.counts.get(target_col)}/{cap}. "
                            f"Complete another task first or set "
                            f"COS_WIP_OVERRIDE=1 to force."
                        ),
                        error_category="validation",
                        wip_state=wip_state,
                    )

    # MD file write (atomic).
    target_file = file_path or (Path(current_file_path) if current_file_path else None)
    warnings: list[str] = []
    if forced_warning is not None:
        warnings.append(forced_warning)
    if target_file is not None:
        try:
            _write_status_to_frontmatter(
                target_file,
                to_status,
                agent_session=agent_session,
            )
        except FileNotFoundError:
            warnings.append(f"MD file missing: {target_file} — DB-only transition")
        except Exception as exc:  # pragma: no cover
            return TransitionResult(
                ok=False,
                task_id=task_id,
                previous_status=current_status,
                new_status=to_status,
                error=f"MD write failed: {exc}",
                error_category="unavailable",
            )
    else:
        warnings.append("no file_path — DB-only transition")

    # DB write — atomic via BEGIN/COMMIT on the one conn.
    now_epoch = int(time.time())
    conn.execute(
        "UPDATE tasks SET status = ?, agent_session = ?, "
        "started_at = CASE WHEN ? = 'in_progress' AND started_at IS NULL "
        "                  THEN ? ELSE started_at END, "
        "completed_at = CASE WHEN ? = 'complete' THEN ? "
        "                    WHEN ? IN ('ready','in_progress','testing','emergency') "
        "                    THEN NULL ELSE completed_at END "
        "WHERE task_id = ?",
        (
            to_status, agent_session,
            to_status, now_epoch,
            to_status, now_epoch,
            to_status,
            task_id,
        ),
    )
    conn.execute(
        "INSERT INTO task_status_history "
        "(task_id, old_status, new_status, agent_session, reason, transitioned_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (task_id, current_status, to_status, agent_session, reason, now_epoch),
    )
    conn.commit()

    return TransitionResult(
        ok=True,
        task_id=task_id,
        previous_status=current_status,
        new_status=to_status,
        warnings=tuple(warnings),
        wip_state=wip_state,
    )


# ---------- Helpers ----------


def _patch_fm_field(fm_text: str, key: str, value: str) -> str:
    """Replace a scalar field in raw YAML text without touching comments or key order.

    If the key already exists, its value is updated in-place.
    If it is absent, the key is appended on a new line (handles tasks
    created before a field was added to the template).
    """
    import re as _re
    pattern = _re.compile(rf"^({_re.escape(key)}:)[ \t]*.*$", _re.MULTILINE)
    if pattern.search(fm_text):
        return pattern.sub(rf"\1 {value}", fm_text, count=1)
    return fm_text + f"\n{key}: {value}"


def _write_status_to_frontmatter(
    path: Path,
    new_status: str,
    *,
    agent_session: str | None,
) -> None:
    """Atomically update status (+ started/completed timestamps) in frontmatter.

    Uses targeted regex field-patching instead of YAML round-trip so that
    inline comments (e.g. ``# always start here``) are preserved verbatim.
    """
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re
    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)

    # Validate YAML is parseable before touching anything.
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    today = time.strftime("%Y-%m-%d")
    fm_raw = _patch_fm_field(fm_raw, "status", new_status)
    if agent_session is not None:
        fm_raw = _patch_fm_field(fm_raw, "agent_session", agent_session)
    if new_status == "in_progress" and not fm_parsed.get("started"):
        fm_raw = _patch_fm_field(fm_raw, "started", today)
    if new_status == "complete" and not fm_parsed.get("completed"):
        fm_raw = _patch_fm_field(fm_raw, "completed", today)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end():]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".task-", suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _format_yaml_scalar_token(value: str) -> str:
    """Format a scalar for YAML frontmatter (unquoted id vs JSON-quoted string)."""
    import re as _re
    if _re.match(r"^[a-z0-9][a-z0-9-]*$", value, _re.I):
        return value
    return json.dumps(value)


def patch_task_frontmatter_scalars(path: Path, updates: dict[str, str]) -> None:
    """
    PURPOSE:      Atomically patch one or more scalar keys in task frontmatter.
    INPUT:        path to TASK-*.md; updates maps YAML key -> string value.
    OUTPUT:       none; raises on missing file / broken YAML.
    DEPENDENCIES: same regex/YAML rules as _write_status_to_frontmatter.
    NOTES:        Used for swimlane edits without a status transition; preserves
                  comments and key order via _patch_fm_field.
    """
    if not updates:
        return
    if not path.exists():
        raise FileNotFoundError(str(path))

    content = path.read_text(encoding="utf-8")
    import re as _re
    fm_re = _re.compile(r"^---\s*\n(.*?)\n---\s*\n", _re.DOTALL)
    m = fm_re.match(content)
    if not m:
        raise ValueError(f"{path}: no frontmatter to update")

    fm_raw = m.group(1)
    try:
        fm_parsed = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: frontmatter YAML broken: {exc}") from exc
    if not isinstance(fm_parsed, dict):
        raise ValueError(f"{path}: frontmatter is not a mapping")

    for key, raw_val in updates.items():
        token = _format_yaml_scalar_token(raw_val)
        fm_raw = _patch_fm_field(fm_raw, key, token)

    new_content = f"---\n{fm_raw}\n---\n" + content[m.end():]

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent), prefix=".task-", suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(new_content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
