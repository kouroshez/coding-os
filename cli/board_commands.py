"""cos board-* CLI commands (Phase L.6).

16 commands:
    cos board [--web] [--port N] [--swimlane] [--kind] [--epic] [--priority]
    cos task-create
    cos task-move
    cos task-start / task-done / task-block / task-cancel
    cos task-pick
    cos task-archive
    cos daily / retro
    cos task-show / task-log / task-history / wip
    cos task-validate
    cos board-config --init

Thin click wrappers over core.board_os.{mcp_tools,workflow,parser,sync}.
All commands use the project's SQLite DB (.coding-os/coding-os.db)
unless COS_DB_PATH overrides.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import click

# Bootstrap so imports work whether invoked via `cos` entry-point or bare python.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _project_root() -> Path:
    return Path(os.environ.get("COS_PROJECT_ROOT") or os.getcwd()).resolve()


def _db_conn() -> sqlite3.Connection:
    root = _project_root()
    db_path = os.environ.get(
        "COS_DB_PATH", str(root / ".coding-os" / "coding-os.db"),
    )
    if not Path(db_path).exists():
        click.echo(f"ERROR: DB not found at {db_path}. Run `cos setup` first.", err=True)
        sys.exit(1)
    return sqlite3.connect(db_path)


def _known_agent_ids() -> tuple[frozenset[str], dict[str, tuple[str, ...]]]:
    """Load adapter ids + their runtime env markers from adapter registry.

    PURPOSE: Keep _detect_agent_runtime data-driven — the function does
             not hardcode agent-name string literals; it iterates over
             whatever adapters declare their markers in adapter.yaml.
    OUTPUT:  (set_of_ids, {id: tuple_of_env_var_names}).  When the
             adapters dir isn't reachable (e.g. a consumer install with
             no adapters/ tree), returns empty structures; callers fall
             back to the .coding-os/.agent marker.
    """
    adapters_dir = Path(__file__).resolve().parent.parent / "adapters"
    try:
        from cli.adapter_registry import load_adapter_registry
        reg = load_adapter_registry(adapters_dir)
    except Exception as exc:  # noqa: BLE001 — detection never fatal
        import logging as _logging
        _logging.getLogger("cli.board_commands").debug(
            "adapter registry unreachable, agent detection degrades to marker-only: %s",
            exc,
        )
        return frozenset(), {}
    ids = frozenset(reg.keys())
    markers = {aid: tuple(p.runtime_env_markers) for aid, p in reg.items()}
    return ids, markers


def _detect_agent_runtime() -> str | None:
    """Detect which agent runtime is invoking this CLI process.

    PURPOSE: Mirror core/hooks/cos-env.sh priority so agent_session
             attribution in the DB matches what the hook layer records.
    INPUT:   COS_AGENT override, runtime env vars declared in each
             adapter.yaml::runtime_env_markers, .coding-os/.agent marker,
             CLAUDE_PROJECT_DIR legacy fallback.
    OUTPUT:  One of the registered adapter ids (discovered at load time
             from adapters/<id>/adapter.yaml), or None.
    NOTES:   Vendor env vars (CURSOR_*, CLAUDE_*, CODEX_*) are declared
             in adapter.yaml — NOT hardcoded here — so adding a new agent
             is data-only (rule #11 compliance).
    DRIFT WARNING: The same priority table is maintained in shell form
             at core/hooks/cos-env.sh.  Update both sides when changing
             priorities.  Only the adapter-id names are data-driven; the
             overall ordering (explicit override → vendor markers →
             marker file → legacy Claude alias) lives in both files.
    """
    known_ids, markers_by_id = _known_agent_ids()

    explicit = (os.environ.get("COS_AGENT") or "").strip().lower()
    if explicit and explicit in known_ids:
        return explicit

    # Alphabetical sort keeps detection deterministic.  The env-marker
    # sets declared by each adapter.yaml don't overlap (CURSOR_* vs
    # CODEX_* vs CLAUDE_*) so order is irrelevant to correctness — and
    # we never hardcode adapter-name literals here (rule #11).  The
    # legacy CLAUDE_PROJECT_DIR fallback below is the only place
    # disambiguation matters, and it gates on "no stronger marker
    # fired" so a real CURSOR_* match already short-circuited.
    for agent_id in sorted(known_ids):
        for env_key in markers_by_id.get(agent_id, ()):
            if os.environ.get(env_key):
                return agent_id

    marker = _project_root() / ".coding-os" / ".agent"
    if marker.is_file():
        try:
            raw = marker.read_text(encoding="utf-8", errors="ignore").strip().lower()
        except OSError:  # noqa: BLE001 — fallback to env-only detection
            raw = ""
        if raw and raw in known_ids:
            return raw

    # Legacy compatibility marker: Cursor also sets CLAUDE_PROJECT_DIR, so
    # only trust it when no stronger signal fired.  The target adapter id
    # is looked up rather than hardcoded so the Claude rename never
    # strands this path.
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        for aid in known_ids:
            if any(
                env_key.startswith("CLAUDE")
                for env_key in markers_by_id.get(aid, ())
            ):
                return aid
    return None


def _agent_session_id() -> str | None:
    """Best-effort agent session resolver for CLI-originated task transitions.

    PURPOSE: Supply a stable agent-prefixed session id (ses-<agent>-...)
             so `task_status_history.agent_session` captures who moved
             each task. The stream / retro / active-agents surfaces all
             read from this column.
    INPUT:   COS_AGENT_SESSION_ID (explicit override); runtime env
             markers; per-agent session-id files under
             $COS_STATE_DIR/<agent>/session-id.
    OUTPUT:  The session id string or None (treated as "human action").
    DEPENDENCIES: _detect_agent_runtime, _project_root.
    """
    sid = os.environ.get("COS_AGENT_SESSION_ID")
    if sid:
        return sid.strip() or None

    runtime = _detect_agent_runtime()
    if runtime is None:
        return None
    p = _project_root() / ".coding-os" / runtime / "session-id"
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return None
    return raw or None


def _parse_envelope(envelope: str) -> dict:
    return json.loads(envelope)


def _print_envelope(envelope: str, *, format: str = "text") -> int:
    data = _parse_envelope(envelope)
    if format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return 0 if data.get("ok") else 1
    if not data.get("ok"):
        click.echo(f"ERROR [{data['error']['category']}]: {data['error']['message']}", err=True)
        return 1
    click.echo(json.dumps(data["data"], indent=2, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------------------
# cos board
# ---------------------------------------------------------------------------


def _launch_board_in_spa(*, host: str, port: int) -> None:
    """Open the unified SPA Board page; auto-start `cos web` if needed.

    PURPOSE: Opens http://{host}:{port}/board in the default browser.
             If the unified web server is already running on the given
             port, just opens the browser; otherwise spawns the server
             in-process and blocks until it is killed.
    INPUT:   host, port — overrideable web server bind.
    OUTPUT:  none.  Opens browser; blocks if it had to spawn the server.
    DEPENDENCIES: urllib (stdlib), webbrowser (stdlib),
                  core.web.server.run_server (lazy).
    """
    import urllib.error
    import urllib.request
    import webbrowser

    url = f"http://{host}:{port}/board"
    health_url = f"http://{host}:{port}/health"

    def _server_up() -> bool:
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, OSError):
            return False

    if _server_up():
        click.echo(f"Opening {url} (web server already running).")
        webbrowser.open(url)
        return

    click.echo(f"Starting Coding OS web server on {host}:{port} ... (Ctrl-C to stop)")
    click.echo(f"Once it is up, open {url} in your browser.")
    try:
        from web.server import run_server
    except ImportError as exc:
        click.echo(
            f"ERROR: could not import core.web.server: {exc}\n"
            "Install web extras: uv sync",
            err=True,
        )
        sys.exit(1)
    run_server(host=host, port=port)


@click.command("board", help="Show Scrumban board (ASCII or --web)")
@click.option("--web", is_flag=True, default=False, help="Open board in browser (redirects to unified SPA at /board)")
@click.option("--port", type=int, default=9188,
              help="Port for the unified web server when --web is used.")
@click.option("--host", default="127.0.0.1")
@click.option("--bind", default=None, help="Bind address (overrides --host)")
@click.option("--swimlane", default=None)
@click.option("--kind", default=None)
@click.option("--epic", default=None)
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--format", type=click.Choice(["text", "json"]), default="text")
def board_cmd(web, port, host, bind, swimlane, kind, epic, priority, format):
    from board_os import mcp_tools
    if web:
        _launch_board_in_spa(host=(bind or host), port=port)
        return
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_board(
            conn,
            swimlane=swimlane, kind=kind, epic=epic,
        )
    finally:
        conn.close()

    # Client-side priority filter (MCP tool doesn't expose it yet).
    if priority:
        allowed = {p.strip().upper() for p in priority.split(",") if p.strip()}
        parsed = _parse_envelope(envelope)
        if parsed.get("ok"):
            cards = parsed["data"].get("cards", [])
            parsed["data"]["cards"] = [c for c in cards if c.get("priority") in allowed]
            parsed["data"]["count"] = len(parsed["data"]["cards"])
            envelope = json.dumps(parsed)

    if format == "text":
        _render_board_ascii(envelope)
    else:
        click.echo(envelope)


def _render_board_ascii(envelope: str) -> None:
    env = _parse_envelope(envelope)
    if not env.get("ok"):
        click.echo(f"ERROR: {env['error']['message']}", err=True)
        return
    data = env["data"]
    grouped = data.get("grouped", {})
    wip = data.get("wip") or {}

    click.echo("\n  Scrumban Board")
    click.echo("  " + "─" * 60)
    if wip.get("counts"):
        parts = []
        for col in ("in_progress", "testing", "emergency"):
            n = wip["counts"].get(col, 0)
            c = wip["caps"].get(col, "?")
            mark = "🔴" if col in wip.get("violations", []) else "·"
            parts.append(f"{col} {n}/{c} {mark}")
        click.echo("  WIP: " + " | ".join(parts))
    click.echo()

    statuses = ["icebox", "ready", "emergency", "in_progress", "testing", "blocked"]
    for lane in sorted(grouped.keys()):
        click.echo(f"  ── {lane} ──")
        for status in statuses:
            cards = grouped[lane].get(status, [])
            if not cards:
                continue
            click.echo(f"    [{status}]")
            for card in cards:
                badge = {
                    "bug": "🔴", "feature": "🟡", "chore": "🟢", "spike": "🔵",
                    "docs": "🟣", "refactor": "🟦", "test": "🟧", "security": "🟠",
                }.get(card["kind"], "⚪")
                # READY overlay: icebox cards carrying the "ready" label are
                # pickup candidates (see board_os.config::READY_LABEL).  We
                # surface this as a "✓READY" prefix so the CLI matches the
                # green pill rendered by the web Board.
                labels = card.get("labels") or []
                ready_prefix = (
                    " ✓READY "
                    if status == "icebox" and "ready" in labels
                    else ""
                )
                click.echo(
                    f"      {badge}{ready_prefix} {card['id']} [{card['priority']}] {card['title']}"
                )
        click.echo()


# ---------------------------------------------------------------------------
# task-create / task-move / task-start / task-done / task-block / task-cancel
# ---------------------------------------------------------------------------


@click.command("task-create", help="Create a new Scrumban task (lean template).")
@click.option("--title", required=True)
@click.option("--swimlane", required=True)
@click.option("--kind", required=True,
              type=click.Choice(["feature", "bug", "chore", "spike", "docs",
                                 "refactor", "test", "security"]))
@click.option("--priority", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--appetite", default="1d")
@click.option("--epic", default=None)
@click.option("--labels", default="", help="Comma-separated free tags")
@click.option("--outcome", default=None)
@click.option("--depends-on", default="", help="Comma-separated TASK-IDs")
def task_create_cmd(title, swimlane, kind, priority, appetite, epic, labels,
                    outcome, depends_on):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_create(
            conn,
            title=title, swimlane=swimlane, kind=kind,
            priority=priority, appetite=appetite,
            epic=epic,
            labels=[l.strip() for l in labels.split(",") if l.strip()],
            outcome=outcome,
            depends_on=[d.strip() for d in depends_on.split(",") if d.strip()],
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-move")
@click.argument("task_id")
@click.option("--to", required=True)
@click.option("--reason", default=None)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Override WIP caps AND state-machine validation "
         "(e.g. archive → in_progress after an accidental archive).",
)
def task_move_cmd(task_id, to, reason, force):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason,
            bypass_wip=force,
            force=force,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


def _simple_move(task_id: str, to: str, *, reason: str | None = None,
                 force: bool = False):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to=to,
            reason=reason,
            bypass_wip=force,
            agent_session=_agent_session_id(),
        )
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-start")
@click.argument("task_id")
@click.option("--force", is_flag=True, default=False)
def task_start_cmd(task_id, force):
    _simple_move(task_id, "in_progress", force=force)


_KIND_TO_OUTCOME_TYPE = {
    "bug": "fix",
    "feature": "feat",
    "refactor": "refactor",
    "docs": "docs",
    "test": "test",
    "chore": "infra",
}

_brain_logger = __import__("logging").getLogger("cli.board.brain")


def _record_brain_outcome_safe(conn: sqlite3.Connection, task_id: str) -> None:
    """Fire-and-forget: mirror task-done into the thinking_os learning loop.

    Writes task_outcomes + outcome_history, back-fills retrievals.outcome for
    every row that cited this task, and triggers learn_extract each 10th
    successful outcome. Any failure is logged at DEBUG — task-done must never
    surface a brain-pipeline failure to the user.
    """
    try:
        from thinking_os.record_outcome import record_outcome
        row = conn.execute(
            "SELECT kind, title FROM tasks WHERE task_id = ?", (task_id,),
        ).fetchone()
        kind = row[0] if row else "feature"
        msg = row[1] if row else ""
        task_type = _KIND_TO_OUTCOME_TYPE.get(kind, "feat")
        db_path = os.environ.get(
            "COS_DB_PATH", str(_project_root() / ".coding-os" / "coding-os.db"),
        )
        record_outcome(
            task_id=task_id,
            task_type=task_type,
            outcome="success",
            msg=msg,
            db_path=db_path,
        )
        # Stamp the model onto the fresh row so routing_weights has input.
        # COS_AGENT_MODEL is set by adapter startup; unknown → leave null.
        model = os.environ.get("COS_AGENT_MODEL") or os.environ.get("ANTHROPIC_MODEL")
        if model:
            try:
                conn.execute(
                    "UPDATE task_outcomes SET model = ? WHERE task_id = ? AND model IS NULL",
                    (model, task_id),
                )
                conn.commit()
            except Exception as exc:
                _brain_logger.debug("model stamp failed for %s: %s", task_id, exc)
    except Exception as exc:
        _brain_logger.debug("record_outcome failed for %s: %s", task_id, exc)
        return

    # retrievals.task_id is composite ("<session_id> <task_slug>") in some
    # writers, plain TASK-NNN in others — match both shapes defensively.
    try:
        conn.execute(
            "UPDATE retrievals SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
            "WHERE outcome IS NULL AND (task_id = ? OR task_id LIKE ?)",
            ("success", task_id, f"%{task_id}%"),
        )
        conn.commit()
    except Exception as exc:
        _brain_logger.debug("retrieval back-fill failed for %s: %s", task_id, exc)

    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.tools.learning import learn_extract
            result = learn_extract(conn)
            extracted = result.get("extracted", [])
            if extracted:
                click.echo(
                    f"\n🧠 Learning: {len(extracted)} new pattern(s) from "
                    f"{count} outcomes:",
                )
                for p in extracted:
                    click.echo(
                        f"   • {p.get('pattern')} "
                        f"(confidence: {p.get('confidence', 0):.2f})",
                    )
    except Exception as exc:
        _brain_logger.debug("learn_extract trigger failed: %s", exc)

    # Rebuild routing_weights every 10 outcomes so `cos_route_model` /
    # `cos_route_skill` have current empirical success rates. No-op until
    # task_outcomes has rows with non-null `model`.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.tools.routing import recalculate_weights
            recalculate_weights(conn)
    except Exception as exc:
        _brain_logger.debug("recalculate_weights failed: %s", exc)

    # Shift document_chunks.priority based on (retrieval, outcome) pairs
    # every 10 outcomes so docs that supported successful work get gently
    # boosted and failed ones decay.  Bounded by _DELTA_* constants inside
    # learn_from_retrievals; never cliff-jumps a single chunk.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.tools.retrieve import learn_from_retrievals
            learn_from_retrievals(conn, lookback_days=14)
    except Exception as exc:
        _brain_logger.debug("learn_from_retrievals failed: %s", exc)

    # Sweep dangling embeddings + concept-graph edges + trash observations
    # every 10 outcomes. Cheap because NOT EXISTS / LIKE globs are indexed
    # and the row counts are small in practice.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.memory_gc import gc_memory
            _db_path = os.environ.get(
                "COS_DB_PATH",
                str(_project_root() / ".coding-os" / "coding-os.db"),
            )
            gc_memory(db_path=_db_path)
    except Exception as exc:
        _brain_logger.debug("gc_memory failed: %s", exc)


@click.command("task-done")
@click.argument("task_id")
def task_done_cmd(task_id):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_move(
            conn,
            task_id=task_id,
            to="complete",
            agent_session=_agent_session_id(),
        )
        parsed = _parse_envelope(envelope)
        if parsed.get("ok"):
            # Codex/Cursor sessions can bypass Claude's post-write Work Log hook.
            # Record one deterministic completion line in the task markdown.
            mcp_tools.cos_work_log_append(
                conn,
                task_id=task_id,
                summary="Status transitioned to complete via cos task-done.",
                agent_session=_agent_session_id(),
                source="task-done",
            )
            _record_brain_outcome_safe(conn, task_id)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("task-block")
@click.argument("task_id")
@click.option("--reason", required=True)
def task_block_cmd(task_id, reason):
    _simple_move(task_id, "blocked", reason=reason)


@click.command("task-cancel")
@click.argument("task_id")
@click.option("--reason", default=None)
def task_cancel_cmd(task_id, reason):
    _simple_move(task_id, "icebox", reason=f"cancelled: {reason or 'no reason given'}")


# ---------------------------------------------------------------------------
# task-pick / daily / retro / wip
# ---------------------------------------------------------------------------


@click.command("task-pick", help="Print top candidate tasks to work on next.")
@click.option("--swimlane", default=None)
@click.option("--priority-min", default="P2", type=click.Choice(["P0", "P1", "P2", "P3"]))
@click.option("--max-candidates", default=3, type=int)
def task_pick_cmd(swimlane, priority_min, max_candidates):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_pick(
            conn, swimlane=swimlane, priority_min=priority_min,
            max_candidates=max_candidates,
        )
    finally:
        conn.close()
    env = _parse_envelope(envelope)
    if not env["ok"]:
        click.echo(f"ERROR: {env['error']['message']}", err=True)
        sys.exit(1)
    cands = env["data"]["candidates"]
    click.echo("\n  Top candidates:")
    for i, c in enumerate(cands, 1):
        click.echo(f"  {i}. {c['id']} [{c['priority']}] {c['title']}  ({c['swimlane']}/{c['kind']})")
    click.echo()


@click.command("daily", help="Morning standup — summary of last 24h.")
@click.option("--since", default="24h")
def daily_cmd(since):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_daily(conn, since=since)
    finally:
        conn.close()
    # Touch daily marker for remind-daily.sh.
    # $COS_AGENT_DIR is agent-scoped (.coding-os/<agent>/); default to generic
    # .coding-os/ to avoid hardcoding a specific adapter here.
    marker = Path(
        os.environ.get("COS_AGENT_DIR", str(_project_root() / ".coding-os")),
    ) / ".daily-last-run"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    sys.exit(_print_envelope(envelope))


@click.command("retro", help="Weekly retrospective — throughput + cycle time.")
@click.option("--since", default="7d")
def retro_cmd(since):
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_retro(conn, since=since)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


@click.command("wip", help="Current WIP counts vs. caps.")
def wip_cmd():
    from board_os import mcp_tools
    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_wip_check(conn)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


# ---------------------------------------------------------------------------
# task-show / task-log / task-history
# ---------------------------------------------------------------------------


@click.command(
    "task-show",
    help="Show a task's full content + frontmatter. Without TASK_ID, falls back to the current session task.",
)
@click.argument("task_id", required=False)
def task_show_cmd(task_id):
    if not task_id:
        agent_dir = os.environ.get("COS_AGENT_DIR")
        if agent_dir:
            current_file = Path(agent_dir) / ".task-current"
            if current_file.exists():
                # write-state.sh stores "<session-id> <value>" on one line.
                # Split off the session prefix and pull the first TASK-NNN
                # token out of the remainder (handles slugged values like
                # "TASK-096-some-slug").
                content = current_file.read_text(encoding="utf-8").strip()
                tokens = content.split()
                value = " ".join(tokens[1:]) if len(tokens) >= 2 else content
                import re as _re
                match = _re.search(r"TASK-\d+", value, _re.IGNORECASE)
                if match:
                    task_id = match.group(0).upper()
        if not task_id:
            click.echo(
                "ERROR: no TASK_ID and no active task in $COS_AGENT_DIR/.task-current.\n"
                "  Hint: cos task-start TASK-NNN  (or pass TASK-NNN explicitly).",
                err=True,
            )
            sys.exit(1)
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT task_id, title, status, swimlane, kind, priority, "
            "appetite, file_path FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)
    click.echo(f"  {row[0]}: {row[1]}")
    click.echo(f"  status={row[2]} swimlane={row[3]} kind={row[4]} priority={row[5]} appetite={row[6]}")
    click.echo(f"  file: {row[7]}")
    if row[7]:
        full_path = _project_root() / row[7]
        if full_path.exists():
            click.echo("\n" + full_path.read_text(encoding="utf-8"))


@click.command("task-log", help="Show a task's Work Log.")
@click.argument("task_id")
@click.option("--full", is_flag=True, default=False)
def task_log_cmd(task_id, full):
    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT file_path, work_log_last_5 FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)
    if full and row[0]:
        full_path = _project_root() / row[0]
        if full_path.exists():
            content = full_path.read_text(encoding="utf-8")
            idx = content.find("## Work Log")
            if idx != -1:
                click.echo(content[idx:])
                return
    last_5 = json.loads(row[1] or "[]")
    for line in last_5:
        click.echo("  " + line)


@click.command("task-history", help="Show task status transitions.")
@click.argument("task_id")
def task_history_cmd(task_id):
    conn = _db_conn()
    try:
        rows = conn.execute(
            "SELECT old_status, new_status, agent_session, reason, transitioned_at "
            "FROM task_status_history WHERE task_id = ? "
            "ORDER BY transitioned_at",
            (task_id,),
        ).fetchall()
    finally:
        conn.close()
    if not rows:
        click.echo(f"  (no transitions for {task_id})")
        return
    click.echo(f"\n  Transitions for {task_id}:")
    import time
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(r[4]))
        click.echo(f"  {ts}  {r[0]:>12} → {r[1]:<12}  {r[3] or ''}")


# ---------------------------------------------------------------------------
# task-validate / board-config
# ---------------------------------------------------------------------------


@click.command(
    "task-validate",
    help=(
        "Lint task files, OR pre-flight a transition without applying it.\n\n"
        "  cos task-validate                       lint all docs/tasks/*.md (default)\n"
        "  cos task-validate TASK-NN               preview DoR for in_progress on TASK-NN\n"
        "  cos task-validate TASK-NN --for complete  preview DoD for complete\n"
        "  cos task-validate TASK-NN --json        machine-readable ValidationResult"
    ),
)
@click.argument("task_id", required=False)
@click.option(
    "--for", "for_status",
    type=click.Choice(["in_progress", "complete"]),
    default="in_progress",
    help="Status to validate as the target. Default: in_progress (DoR check).",
)
@click.option("--json", "as_json", is_flag=True, default=False)
def task_validate_cmd(task_id, for_status, as_json):
    """Two modes:

    1. No TASK_ID → lint every TASK-*.md file (legacy behavior).
    2. TASK_ID given → run the Phase L.10 transition gate for the given
       target status WITHOUT applying it. Same validator as the live
       gate, so the verdict matches what `cos task-start` would do.
    """
    if not task_id:
        _task_validate_lint_all()
        return
    _task_validate_preflight(task_id, for_status, as_json)


def _task_validate_lint_all() -> None:
    from board_os.parser import parse_task
    root = _project_root()
    tasks_dir = root / "docs" / "tasks"
    if not tasks_dir.exists():
        click.echo(f"  (no {tasks_dir})")
        return
    errors = 0
    warnings = 0
    for p in sorted(tasks_dir.glob("TASK-*.md")):
        content = p.read_text(encoding="utf-8")
        parsed = parse_task(content, path=p)
        if parsed is None:
            click.echo(f"  ✗ {p.name}: unparseable", err=True)
            errors += 1
            continue
        if parsed.parse_warnings:
            for w in parsed.parse_warnings:
                click.echo(f"  ⚠ {p.name}: {w}")
                warnings += 1
        else:
            click.echo(f"  ✓ {p.name}")
    click.echo(f"\n  Total: {errors} errors, {warnings} warnings")
    sys.exit(1 if errors > 0 else 0)


def _task_validate_preflight(task_id: str, for_status: str, as_json: bool) -> None:
    """Run the transition gate validator without applying any change."""
    import json as _json
    from board_os.parser import extract_frontmatter
    from board_os.transition_gates import GatesConfigError, load_gates_config
    from board_os.transition_gates_cli import (
        _has_work_log_entries, _verify_state,
    )
    from board_os.transition_gates_validator import (
        Verdict, validate_transition,
    )

    conn = _db_conn()
    try:
        row = conn.execute(
            "SELECT file_path, kind FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        click.echo(f"ERROR: {task_id} not found", err=True)
        sys.exit(1)

    file_path = _project_root() / row[0] if row[0] else None
    body = ""
    kind = str(row[1] or "feature")
    if file_path and file_path.exists():
        body = file_path.read_text(encoding="utf-8")
        fm = extract_frontmatter(body) or {}
        if fm.get("kind"):
            kind = str(fm["kind"])

    try:
        config = load_gates_config()
    except GatesConfigError as exc:
        click.echo(f"ERROR: gates config: {exc}", err=True)
        sys.exit(2)

    has_recent, age = _verify_state()
    has_work_log = _has_work_log_entries(body)

    result = validate_transition(
        task_id=task_id,
        kind=kind,
        body=body,
        new_status=for_status,
        config=config,
        has_recent_verify=has_recent,
        verify_age_seconds=age,
        has_work_log=has_work_log,
        override_reason=os.environ.get("COS_OVERRIDE_REASON"),
        override_actor=os.environ.get("COS_AGENT"),
    )

    if as_json:
        click.echo(result.model_dump_json(indent=2))
        sys.exit(0 if result.verdict is not Verdict.BLOCK else 2)

    glyph = {
        Verdict.PASS: "✓ PASS",
        Verdict.WARN: "⚠ WARN",
        Verdict.BLOCK: "✗ BLOCK",
    }[result.verdict]
    click.echo(f"  {task_id} (kind={kind}, target={for_status}): {glyph}")
    for msg in result.messages:
        sev = msg.severity.value.upper()
        click.echo(f"    [{msg.code}] {sev}: {msg.message}")
    if result.verdict is Verdict.PASS:
        click.echo(f"  Run: cos task-start {task_id}" if for_status == "in_progress"
                   else f"  Run: cos task-done {task_id}")
    sys.exit(0 if result.verdict is not Verdict.BLOCK else 2)


def _discover_stacks() -> list[str]:
    """Data-driven — read templates/ to find available stack ids."""
    templates_dir = _REPO_ROOT / "templates"
    if not templates_dir.exists():
        return []
    return sorted(
        p.name for p in templates_dir.iterdir()
        if p.is_dir() and (p / "scaffold").exists()
    )


@click.command("board-config", help="Scaffold or inspect scrumban-config.yaml")
@click.option("--init", is_flag=True, default=False)
@click.option("--stack", default="_base")
def board_config_cmd(init, stack):
    valid_stacks = _discover_stacks() or ["_base"]
    if stack not in valid_stacks:
        click.echo(
            f"ERROR: stack {stack!r} not in {valid_stacks}", err=True,
        )
        sys.exit(1)
    root = _project_root()
    config_path = root / ".coding-os" / "scrumban-config.yaml"
    if init:
        if config_path.exists():
            click.echo(f"ERROR: {config_path} already exists", err=True)
            sys.exit(1)
        source = (
            _REPO_ROOT / "templates" / stack / "scaffold" / ".coding-os"
            / "scrumban-config.yaml"
        )
        if not source.exists():
            source = (
                _REPO_ROOT / "templates" / "_base" / "scaffold" / ".coding-os"
                / "scrumban-config.yaml"
            )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        click.echo(f"  Created {config_path} (from {stack})")
    else:
        if not config_path.exists():
            click.echo(f"ERROR: {config_path} not found; run --init", err=True)
            sys.exit(1)
        click.echo(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Commands bundle — register via cli.add_command(each)
# ---------------------------------------------------------------------------


BOARD_COMMANDS = [
    board_cmd,
    task_create_cmd, task_move_cmd,
    task_start_cmd, task_done_cmd, task_block_cmd, task_cancel_cmd,
    task_pick_cmd, daily_cmd, retro_cmd, wip_cmd,
    task_show_cmd, task_log_cmd, task_history_cmd,
    task_validate_cmd, board_config_cmd,
]
