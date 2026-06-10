"""core.web.routes.board — /api/board/* HTTP wrappers for cos_task_* tools."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

logger = logging.getLogger("coding_os.web.board")
router = APIRouter(prefix="/api/board", tags=["board"], responses=ENVELOPE_ERROR_RESPONSES)


def _db_conn() -> sqlite3.Connection:
    """Open the project SQLite DB for one request."""
    from web._project_context import current_db_path

    return sqlite3.connect(str(current_db_path()), check_same_thread=False)


def _board_tools():
    """Lazy import for board_os mcp_tools."""
    try:
        from board_os import mcp_tools  # type: ignore

        return mcp_tools
    except ImportError:
        return None


def _unavailable():
    import json

    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": "unavailable",
                "retryable": False,
                "message": "board_os package not importable",
            },
        }
    )


# Presence windows + state-rank live in board_os.presence (SSOT).  Re-
# export the constants the tests still reference.
from board_os.presence import (  # noqa: E402  (after sys.path bootstrap above)
    ACTIVE_WINDOW_SECS as _ACTIVE_WINDOW_SECS,
    PRESENT_WINDOW_SECS as _PRESENT_WINDOW_SECS,
    WORKING_WINDOW_SECS as _WORKING_WINDOW_SECS,
    agent_state as _agent_state_fs,
    pid_alive as _pid_alive_fn,
    session_inventory as _session_inventory_fs,
    session_presence as _session_presence_fn,
)

_DB_FALLBACK_WINDOW_SECS = 300  # legacy DB-only signal window


# `_pid_alive` is re-exported from board_os.presence so legacy callers
# inside this module keep working unchanged.
_pid_alive = _pid_alive_fn


def _presence_dir(agent: str) -> Path:
    from web._project_context import current_project_root

    return current_project_root() / ".coding-os" / agent / "sessions"


def _presence_files(agent: str) -> list[Path]:
    """Return the per-session presence JSON files for this agent."""
    from board_os.presence import session_files

    return session_files(_presence_dir(agent))


# Per-agent / per-session presence math lives in board_os.presence.
# Thin filesystem-bound wrappers below resolve the per-project
# .coding-os/<agent>/sessions/ directory and delegate.
def _presence_state(agent: str) -> str:
    return _agent_state_fs(_presence_dir(agent))


def _session_inventory(agent: str) -> list[dict]:
    return _session_inventory_fs(agent, _presence_dir(agent))


# `_session_presence` is preserved as a stable name for any in-tree
# tests that imported it directly.
_session_presence = _session_presence_fn


def _cursor_model_display() -> str | None:
    """Optional display-only line from .coding-os/cursor/.model (not presence)."""
    from web._project_context import current_project_root

    p = current_project_root() / ".coding-os" / "cursor" / ".model"
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    # One-line display; avoid huge env dumps in JSON.
    line = raw.splitlines()[0].strip()
    return line[:160] if line else None


def _agent_active_from_db(conn: sqlite3.Connection, agent: str) -> bool:
    """Legacy signal: recent task transition or in-progress task ownership.

    Retained as a fallback so projects that pre-date the presence hook
    (no .coding-os/<agent>/sessions/ directory) still get SOMETHING
    useful on the board.  New deployments should rely on _presence_state.
    """
    session_like = f"%{agent}%"
    recent_transition = conn.execute(
        """
        SELECT 1
        FROM task_status_history
        WHERE agent_session LIKE ?
          AND transitioned_at >= CAST(strftime('%s','now') AS INTEGER) - ?
        LIMIT 1
        """,
        (session_like, _DB_FALLBACK_WINDOW_SECS),
    ).fetchone()
    if recent_transition:
        return True

    active_owned_task = conn.execute(
        """
        SELECT 1
        FROM tasks
        WHERE status IN ('in_progress', 'testing', 'emergency')
          AND agent_session LIKE ?
        LIMIT 1
        """,
        (session_like,),
    ).fetchone()
    return bool(active_owned_task)


def _agent_state(conn: sqlite3.Connection, agent: str) -> str:
    """Preferred signal: presence files.  Falls back to DB for legacy."""
    state = _presence_state(agent)
    if state != "offline":
        return state
    if _agent_active_from_db(conn, agent):
        return "present"
    return "offline"


@router.get("/task/{task_id}")
def board_task_detail(
    task_id: str,
    _rl=Depends(make_rate_limit_dep("board.task.detail")),
    _m=Depends(make_metrics_dep("board.task.detail")),
):
    """Return the full markdown content + resolved metadata for one task."""
    if not task_id or not task_id.startswith("TASK-"):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid task_id"}},
        )
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT task_id, title, status, swimlane, kind, priority, "
            "appetite, epic, labels_json, file_path FROM tasks "
            "WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"{task_id} not found"}},
        )

    import json as _json

    try:
        labels = _json.loads(row[8] or "[]")
    except (TypeError, ValueError):
        labels = []

    file_rel = row[9] or ""
    from web._project_context import current_project_root

    project_root = current_project_root()
    file_abs = (project_root / file_rel).resolve() if file_rel else None

    # Sandbox: the path must live under <project_root>/docs/tasks/.
    # Block traversal and arbitrary reads.
    tasks_dir = (project_root / "docs" / "tasks").resolve()
    exists = False
    content = ""
    size = 0
    mtime = 0
    truncated = False
    if file_abs is not None:
        try:
            file_abs.relative_to(tasks_dir)
        except ValueError:
            return JSONResponse(
                status_code=410,
                content={
                    "error": {
                        "category": "validation",
                        "message": f"task file outside docs/tasks/: {file_rel}",
                    }
                },
            )
        if file_abs.exists() and file_abs.is_file():
            exists = True
            stat = file_abs.stat()
            size = int(stat.st_size)
            mtime = int(stat.st_mtime)
            # 256 KB cap — task files rarely exceed 20 KB in practice.
            MAX_BYTES = 256 * 1024
            raw = file_abs.read_bytes()
            if len(raw) > MAX_BYTES:
                content = raw[:MAX_BYTES].decode("utf-8", errors="replace")
                content += (
                    "\n\n<!-- truncated: file is "
                    f"{len(raw):,} bytes, showing first {MAX_BYTES:,} -->\n"
                )
                truncated = True
            else:
                content = raw.decode("utf-8", errors="replace")

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "task_id": row[0],
                "file_path": file_rel,
                "exists": exists,
                "content": content,
                "size": size,
                "mtime": mtime,
                "truncated": truncated,
                "row": {
                    "title": row[1],
                    "status": row[2],
                    "swimlane": row[3],
                    "kind": row[4],
                    "priority": row[5],
                    "appetite": row[6],
                    "epic": row[7],
                    "labels": labels,
                },
            },
            "meta": {"layer": "tasks", "source": "web.board_task_detail"},
        },
    )


@router.get("/list")
def board_list(
    swimlane: str | None = Query(None),
    kind: str | None = Query(None),
    epic: str | None = Query(None),
    include_archive: bool = Query(False),
    limit: int = Query(500),
    status: str | None = Query(None),
    page_size: int = Query(50),
    cursor: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.list")),
    _m=Depends(make_metrics_dep("board.list")),
):
    """Return the board state grouped by (swimlane, status).

    Active columns return in full (capped); complete/archive are keyset-paged.
    A per-column "load more" passes `status=<complete|archive>&cursor=<next>`
    to fetch that column's next page (TASK-223).
    """
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_board(
            conn,
            swimlane=swimlane,
            kind=kind,
            epic=epic,
            status_filter=[status] if status else None,
            include_archive=include_archive,
            limit=limit,
            page_size=page_size,
            cursor=cursor,
            # The browser is not token-limited, so skip the 32KB agent-context
            # slice. Safe now that every column is bounded per-column (active
            # capped, complete/archive keyset-paged) — no return-all.
            apply_budget=False,
        )
    finally:
        conn.close()

    env = json.loads(result)
    if env.get("ok"):
        # agent_states is the new, richer shape: {agent: "active"|"present"|"offline"}.
        # active_agents preserves the v0.5 contract ("list of ids that are not
        # offline") so older UI builds keep working during the rollout.
        from board_os._agent_runtime import human_actor
        from board_os.hub_adapter_manifest import list_agent_manifest_rows

        adapter_rows = list_agent_manifest_rows()
        agent_ids = [str(r["id"]) for r in adapter_rows]
        human = human_actor()
        # Human operator is always considered present. Identity is resolved
        # (not hard-coded) so a future auth layer supplies the real user.
        states: dict[str, str] = {human["id"]: "active"}
        session_states: list[dict] = []
        session_counts: dict[str, int] = {}
        conn = _db_conn()
        try:
            for agent in agent_ids:
                states[agent] = _agent_state(conn, agent)
                inv = _session_inventory(agent)
                session_states.extend(inv)
                if inv:
                    session_counts[agent] = len(inv)
        finally:
            conn.close()
        env["data"]["agent_states"] = states
        env["data"]["active_agents"] = [a for a, st in states.items() if st != "offline"]
        # P2 — surface live sessions per agent so the UI can render
        # "Cl·3" badges and a session-detail tooltip instead of
        # collapsing N parallel sessions into one verdict.
        env["data"]["session_states"] = session_states
        env["data"]["session_counts"] = session_counts
        # T19.3 — surface dispatcher sub-session count so the live-agents
        # panel can show "Claude (+ N sub-agents)". Sub-sessions are written
        # by adapters/claude/sdk_dispatcher.py::_presence_write() with
        # session_id prefix `ses-claude-sdk-`.
        sub_counts: dict[str, int] = {}
        for agent in agent_ids:
            try:
                files = _presence_files(agent)
                count = 0
                import time as _time

                now = _time.time()
                for path in files:
                    if not path.stem.startswith(f"ses-{agent}-sdk-"):
                        continue
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    if data.get("ended_at") is not None:
                        continue
                    last_tool = data.get("last_tool_at") or 0
                    if isinstance(last_tool, int) and now - last_tool <= _ACTIVE_WINDOW_SECS:
                        count += 1
                if count:
                    sub_counts[agent] = count
            except Exception as exc:
                logger.debug("sub-session count failed for %s: %s", agent, exc)
        env["data"]["sub_session_counts"] = sub_counts
        human_row = {
            "id": human["id"],
            "label": human["label"],
            "glyph": (human["label"][:1] or "H").upper(),
            "color": "#16a34a",
            "session": human["id"],
        }
        env["data"]["agent_manifest"] = [*adapter_rows, human_row]
        env["data"]["presence_scope"] = "per_project"
        cm = _cursor_model_display()
        if cm is not None:
            env["data"]["cursor_model"] = cm

    return JSONResponse(status_code=200 if env.get("ok") else 400, content=env)


@router.post("/create")
def board_create(
    title: str = Body(...),
    swimlane: str = Body(...),
    kind: str = Body(...),
    priority: str = Body("P2"),
    appetite: str = Body("1d"),
    epic: str | None = Body(None),
    labels: list[str] | None = Body(None),
    outcome: str | None = Body(None),
    read_first: list[str] | None = Body(None),
    depends_on: list[str] | None = Body(None),
    status: str = Body("icebox"),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.create")),
    _m=Depends(make_metrics_dep("board.create")),
):
    """Create a new Scrumban task file + sync to DB."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    # Manual panel creates are human-INITIATED. Only attribute to an agent
    # session when the caller explicitly provides one (agent-mode authoring,
    # /T12) — otherwise _resolve_attribution would tag the create to
    # whatever agent panel is active (the .active-session pointer), making a
    # human-made task look agent-led.
    if not agent_session:
        from board_os._agent_runtime import human_actor

        agent_session = human_actor()["id"]
    conn = _db_conn()
    try:
        result = bt.cos_task_create(
            conn,
            title=title,
            swimlane=swimlane,
            kind=kind,
            priority=priority,
            appetite=appetite,
            epic=epic,
            labels=labels or [],
            outcome=outcome,
            read_first=read_first or [],
            depends_on=depends_on or [],
            status=status,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/move")
def board_move(
    task_id: str = Body(...),
    to: str = Body(...),
    reason: str | None = Body(None),
    bypass_wip: bool = Body(False),
    force: bool = Body(False),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.move")),
    _m=Depends(make_metrics_dep("board.move")),
):
    """Transition a task through the Scrumban state machine."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason,
            bypass_wip=bypass_wip,
            force=force,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.patch("/task/{task_id}")
def board_task_edit(
    task_id: str,
    title: str | None = Body(None),
    priority: str | None = Body(None),
    swimlane: str | None = Body(None),
    appetite: str | None = Body(None),
    epic: str | None = Body(None),
    labels: list[str] | None = Body(None),
    body: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.task.edit")),
    _m=Depends(make_metrics_dep("board.task.edit")),
):
    """Edit a task's frontmatter fields and/or body from the panel (human actor)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    from board_os._agent_runtime import human_actor

    actor = human_actor()
    conn = _db_conn()
    try:
        result = bt.cos_task_edit(
            conn,
            task_id=task_id,
            title=title,
            priority=priority,
            swimlane=swimlane,
            appetite=appetite,
            epic=epic,
            labels=labels,
            body=body,
            actor_type="human",
            actor_id=actor["id"],
            source="web",
        )
    finally:
        conn.close()
    return unwrap(result)


@router.post("/task/{task_id}/ready")
def board_task_ready(
    task_id: str,
    ready: bool = Body(True, embed=True),
    _rl=Depends(make_rate_limit_dep("board.task.ready")),
    _m=Depends(make_metrics_dep("board.task.ready")),
):
    """Toggle the 'ready' label on a task from the panel (human actor)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    from board_os._agent_runtime import human_actor

    actor = human_actor()
    conn = _db_conn()
    try:
        result = bt.cos_task_ready(conn, task_id=task_id, ready=ready, agent_session=actor["id"])
    finally:
        conn.close()
    return unwrap(result)


@router.get("/task/{task_id}/history")
def board_task_history(
    task_id: str,
    include_commits: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("board.task.history")),
    _m=Depends(make_metrics_dep("board.task.history")),
):
    """Return the actor-attributed history (create + status + edits + commits) for a task."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_history(conn, task_id=task_id, include_commits=include_commits)
    finally:
        conn.close()
    return unwrap(result)


_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_TASK_FILE_RE = re.compile(r"docs/tasks/(TASK-\d+)-")


def _is_other_task_file(path: str, for_task: str) -> bool:
    # A docs/tasks/TASK-NNN-*.md belonging to a DIFFERENT task than for_task — so
    # one task's HISTORY never shows a batched commit's sibling-task files.
    m = _TASK_FILE_RE.search(path)
    return bool(m) and m.group(1) != for_task


def _run_git(args: list[str], cwd: Path, timeout: float = 8.0) -> tuple[int, str]:
    """Run a read-only git command; fail-open to (1, '') — never 500 the panel."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout or ""
    except Exception as exc:  # noqa: BLE001 — fail-open
        logging.getLogger("coding_os.web.board").debug("git %s failed: %s", args[:2], exc)
        return 1, ""


@router.get("/commit/{sha}")
def board_commit(
    sha: str,
    for_task: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.commit")),
    _m=Depends(make_metrics_dep("board.commit")),
):
    """List the files changed in one commit (numstat) — read-only."""
    if not _SHA_RE.match(sha):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid sha"}},
        )
    from web._project_context import current_project_root

    root = current_project_root()
    rc, out = _run_git(
        ["show", "--no-color", "--numstat", "--format=%H%x00%an%x00%aI%x00%s", sha], root
    )
    if rc != 0 or not out.strip():
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"commit {sha} not found"}},
        )
    header, _, body = out.partition("\n")
    parts = (header.split("\x00") + ["", "", "", ""])[:4]
    full_sha, author, date, subject = parts
    files = []
    for line in body.splitlines():
        cols = line.strip().split("\t")
        if len(cols) != 3:
            continue
        added, removed, path = cols
        files.append(
            {
                "path": path,
                "added": None if added == "-" else int(added),
                "removed": None if removed == "-" else int(removed),
                "binary": added == "-" and removed == "-",
            }
        )
    # Under one task's HISTORY, drop OTHER tasks' TASK-*.md so a batched commit
    # doesn't leak sibling-task files into this task's view (keeps own + code).
    if for_task and re.fullmatch(r"TASK-\d+", for_task):
        files = [f for f in files if not _is_other_task_file(f["path"], for_task)]
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "sha": full_sha or sha,
                "subject": subject,
                "author": author,
                "date": date,
                "files": files,
            },
            "meta": {"layer": "tasks", "source": "web.board_commit"},
        },
    )


@router.get("/diff")
def board_diff(
    sha: str = Query(...),
    file: str = Query(...),
    _rl=Depends(make_rate_limit_dep("board.diff")),
    _m=Depends(make_metrics_dep("board.diff")),
):
    """Unified diff for one file at one commit — read-only, repo-sandboxed."""
    if not _SHA_RE.match(sha):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid sha"}},
        )
    from web._project_context import current_project_root

    root = current_project_root().resolve()
    try:
        rel = (root / file).resolve().relative_to(root)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "file outside repo"}},
        )
    rc, out = _run_git(["show", "--no-color", "--format=", sha, "--", str(rel)], root)
    if rc != 0:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"commit {sha} not found"}},
        )
    max_bytes = 200 * 1024
    truncated = len(out) > max_bytes
    diff_text = out[:max_bytes] if truncated else out
    lines = diff_text.splitlines()
    added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "sha": sha,
                "file": str(rel),
                "diff": diff_text,
                "added": added,
                "removed": removed,
                "truncated": truncated,
            },
            "meta": {"layer": "tasks", "source": "web.board_diff"},
        },
    )


@router.get("/task/{task_id}/chat-ref")
def board_task_chat_ref(
    task_id: str,
    _rl=Depends(make_rate_limit_dep("board.task.chatref")),
    _m=Depends(make_metrics_dep("board.task.chatref")),
):
    """Resolve a task's originating chat: live SDK uuid + snapshot availability."""
    if not task_id or not task_id.startswith("TASK-"):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid task_id"}},
        )
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT agent_session FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"{task_id} not found"}},
        )

    import glob as _glob

    from web._project_context import current_project_root

    agent_session = (row[0] or "").strip()
    sdk_uuid = None
    has_snapshot = False
    # Only resolve a real, filename-safe agent session (never 'human').
    if agent_session and agent_session != "human" and re.match(r"^[A-Za-z0-9_-]+$", agent_session):
        root = current_project_root()
        for pf in _glob.glob(str(root / ".coding-os" / "*" / "sessions" / f"{agent_session}.json")):
            try:
                rec = json.loads(Path(pf).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rec.get("sdk_uuid"):
                sdk_uuid = rec["sdk_uuid"]
                break
        snaps = _glob.glob(
            str(root / ".coding-os" / "*" / "sessions" / "transcripts" / f"{agent_session}.jsonl")
        )
        has_snapshot = bool(snaps)

    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "task_id": task_id,
                "agent_session": agent_session or None,
                "sdk_uuid": sdk_uuid,
                "has_snapshot": has_snapshot,
            },
            "meta": {"layer": "tasks", "source": "web.board_task_chat_ref"},
        },
    )


# NOTE: the per-task session-transcript preview (board_task_transcript +
# _tail_transcript) was removed — surfacing the agent's full chat transcript
# under every task was unwanted noise + a privacy leak. The snapshot file
# (cognition trace-replay) stays on disk; it is no longer exposed via the API.


@router.get("/config")
def board_config(
    _rl=Depends(make_rate_limit_dep("board.config")),
    _m=Depends(make_metrics_dep("board.config")),
):
    """Return scrumban-config swimlanes + WIP caps + status column ids for the SPA."""
    try:
        from board_os.config import STATUS_ENUM, load_config
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={"error": {"category": "unavailable", "message": "board_os not importable"}},
        )
    from web._project_context import current_project_root

    project_root = current_project_root()
    try:
        cfg = load_config(project_root)
    except FileNotFoundError:
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "category": "unavailable",
                    "message": "scrumban-config.yaml not found — run `cos board-config --init`",
                },
            },
        )
    swimlanes = [
        {
            "id": sl.id,
            "label": sl.label,
            "color": sl.color,
            "accent": sl.effective_accent(),
            "description": sl.description,
        }
        for sl in cfg.swimlanes
    ]
    columns = [{"id": sid, "label": sid.replace("_", " ").upper()} for sid in STATUS_ENUM]
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "swimlanes": swimlanes,
                "columns": columns,
                "wip_limits": {
                    "in_progress": cfg.wip_limits.in_progress,
                    "testing": cfg.wip_limits.testing,
                    "emergency": cfg.wip_limits.emergency,
                },
            },
            "meta": {"layer": "tasks", "source": "web.board_config"},
        },
    )


@router.post("/reposition")
def board_reposition(
    task_id: str = Body(...),
    swimlane: str | None = Body(None),
    to: str | None = Body(None),
    reason: str | None = Body(None),
    bypass_wip: bool = Body(False),
    force: bool = Body(False),
    agent_session: str | None = Body(None),
    _rl=Depends(make_rate_limit_dep("board.reposition")),
    _m=Depends(make_metrics_dep("board.reposition")),
):
    """HTTP wrapper for cos_task_reposition (status and/or swimlane)."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_reposition(
            conn,
            task_id=task_id,
            swimlane=swimlane,
            to=to,
            reason=reason,
            bypass_wip=bypass_wip,
            force=force,
            agent_session=agent_session,
        )
    finally:
        conn.close()
    return unwrap(result)


@router.get("/daily")
def board_daily(
    since: str = Query("24h"),
    agent_session: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.daily")),
    _m=Depends(make_metrics_dep("board.daily")),
):
    """Daily standup summary."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_daily(conn, since=since, agent_session=agent_session)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/retro")
def board_retro(
    since: str = Query("7d"),
    _rl=Depends(make_rate_limit_dep("board.retro")),
    _m=Depends(make_metrics_dep("board.retro")),
):
    """Weekly retrospective metrics."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_retro(conn, since=since)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/wip")
def board_wip(
    _rl=Depends(make_rate_limit_dep("board.wip")),
    _m=Depends(make_metrics_dep("board.wip")),
):
    """WIP cap health check."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_wip_check(conn)
    finally:
        conn.close()
    return unwrap(result)


@router.get("/pick")
def board_pick(
    swimlane: str | None = Query(None),
    priority_min: str = Query("P2"),
    max_candidates: int = Query(5),
    _rl=Depends(make_rate_limit_dep("board.pick")),
    _m=Depends(make_metrics_dep("board.pick")),
):
    """Top candidate tasks to start next."""
    bt = _board_tools()
    if bt is None:
        return unwrap(_unavailable())
    conn = _db_conn()
    try:
        result = bt.cos_task_pick(
            conn,
            swimlane=swimlane,
            priority_min=priority_min,
            max_candidates=max_candidates,
        )
    finally:
        conn.close()
    return unwrap(result)
