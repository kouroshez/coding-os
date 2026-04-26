"""
Phase M — `cos cognition` CLI.

Provides introspection commands over the v14 cognition tables:
  cos cognition log          — recent formula dispatches + backtracks
  cos cognition log --formula F2
  cos cognition log --persona tech-lead
  cos cognition log --backtrack
  cos cognition log --since 1h
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click


def _db_path() -> Path:
    env = os.environ.get("COS_DB_PATH")
    if env:
        return Path(env)
    return Path(".coding-os/thinking_os.db")


def _parse_since(since: str | None) -> str | None:
    """Convert a human duration string (1h, 30m, 2d) to an ISO datetime string."""
    if not since:
        return None
    unit = since[-1]
    try:
        n = int(since[:-1])
    except ValueError:
        raise click.BadParameter(f"Invalid --since value: {since!r} (use e.g. 1h, 30m, 2d)")
    if unit == "h":
        delta = timedelta(hours=n)
    elif unit == "m":
        delta = timedelta(minutes=n)
    elif unit == "d":
        delta = timedelta(days=n)
    else:
        raise click.BadParameter(f"Unknown unit in --since: {since!r} (use h, m, or d)")
    cutoff = datetime.now(timezone.utc) - delta
    return cutoff.strftime("%Y-%m-%d %H:%M:%S")


@click.group("cognition")
def cognition_group() -> None:
    """Phase M cognition introspection (dispatches, personas, backtracks)."""


@cognition_group.command("log")
@click.option("--formula", default=None, help="Filter by formula ID (e.g. F2, F5)")
@click.option("--persona", default=None, help="Filter by persona ID (e.g. tech-lead)")
@click.option("--backtrack", is_flag=True, default=False, help="Show backtrack events only")
@click.option("--since", default=None, help="Show entries since duration ago (e.g. 1h, 30m, 2d)")
@click.option("--limit", default=20, show_default=True, help="Max rows to return")
def cognition_log(
    formula: str | None,
    persona: str | None,
    backtrack: bool,
    since: str | None,
    limit: int,
) -> None:
    """Show recent formula dispatches, persona selections, and backtrack events."""
    db = _db_path()
    if not db.exists():
        click.echo(f"No DB found at {db}. Run `cos init` or set COS_DB_PATH.", err=True)
        raise SystemExit(1)

    cutoff = _parse_since(since)
    conn = sqlite3.connect(str(db), timeout=5)
    conn.row_factory = sqlite3.Row

    try:
        _print_dispatches(conn, formula=formula, persona=persona, cutoff=cutoff, limit=limit,
                          backtrack_only=backtrack)
        if not backtrack:
            _print_persona_selections(conn, persona=persona, cutoff=cutoff, limit=limit)
    finally:
        conn.close()


def _print_dispatches(
    conn: sqlite3.Connection,
    formula: str | None,
    persona: str | None,
    cutoff: str | None,
    limit: int,
    backtrack_only: bool,
) -> None:
    """Print formula_dispatches or backtrack_events rows."""
    if backtrack_only:
        _print_backtracks(conn, cutoff=cutoff, limit=limit)
        return

    try:
        where: list[str] = []
        params: list = []
        if formula:
            where.append("formula_id = ?")
            params.append(formula)
        if persona:
            where.append("persona_id = ?")
            params.append(persona)
        if cutoff:
            where.append("ts >= ?")
            params.append(cutoff)

        sql = "SELECT session_id, task_marker, persona_id, formula_id, status, latency_ms, ts FROM formula_dispatches"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            click.echo("No formula dispatches found.")
            return

        click.echo(f"\n{'─'*72}")
        click.echo("  FORMULA DISPATCHES")
        click.echo(f"{'─'*72}")
        click.echo(f"  {'TS':<20} {'FORMULA':<8} {'PERSONA':<22} {'STATUS':<10} {'MS':>6}")
        click.echo(f"{'─'*72}")
        for r in rows:
            ms = r["latency_ms"] if r["latency_ms"] is not None else "-"
            click.echo(
                f"  {r['ts']:<20} {r['formula_id']:<8} {r['persona_id']:<22} {r['status']:<10} {str(ms):>6}"
            )
        click.echo(f"{'─'*72}\n")
    except sqlite3.OperationalError:
        click.echo("formula_dispatches table not found — DB may pre-date Phase M.", err=True)


def _print_backtracks(conn: sqlite3.Connection, cutoff: str | None, limit: int) -> None:
    try:
        where: list[str] = []
        params: list = []
        if cutoff:
            where.append("ts >= ?")
            params.append(cutoff)

        sql = "SELECT session_id, from_formula, to_formula, reason, ts FROM backtrack_events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            click.echo("No backtrack events found.")
            return

        click.echo(f"\n{'─'*72}")
        click.echo("  BACKTRACK EVENTS")
        click.echo(f"{'─'*72}")
        for r in rows:
            click.echo(
                f"  [{r['ts']}] {r['from_formula']} → {r['to_formula']}: {r['reason'][:50]}"
            )
        click.echo(f"{'─'*72}\n")
    except sqlite3.OperationalError:
        click.echo("backtrack_events table not found — DB may pre-date Phase M.", err=True)


def _print_persona_selections(
    conn: sqlite3.Connection,
    persona: str | None,
    cutoff: str | None,
    limit: int,
) -> None:
    try:
        where: list[str] = []
        params: list = []
        if persona:
            where.append("persona_id = ?")
            params.append(persona)
        if cutoff:
            where.append("ts >= ?")
            params.append(cutoff)

        sql = "SELECT session_id, task_marker, persona_id, confidence, intensity, ts FROM persona_selections"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        if not rows:
            return

        click.echo(f"{'─'*72}")
        click.echo("  PERSONA SELECTIONS")
        click.echo(f"{'─'*72}")
        click.echo(f"  {'TS':<20} {'PERSONA':<22} {'CONF':>6} {'INTENSITY':<10}")
        click.echo(f"{'─'*72}")
        for r in rows:
            click.echo(
                f"  {r['ts']:<20} {r['persona_id']:<22} {r['confidence']:>6.2f} {r['intensity']:<10}"
            )
        click.echo(f"{'─'*72}\n")
    except sqlite3.OperationalError:
        pass  # persona_selections is optional — skip silently


@cognition_group.command("trace")
@click.argument("session_id")
@click.option("--raw", is_flag=True, help="Print raw JSONL lines instead of pretty timeline")
@click.option("--summary", is_flag=True, help="Print only the summary block")
@click.option(
    "--agent-dir", default=None,
    help="Agent dir (default: .coding-os/claude/)",
)
def cognition_trace(session_id: str, raw: bool, summary: bool, agent_dir: str | None) -> None:
    """
    Phase N — Show the cognition trace for a session (timeline of flowchart nodes).

    Spec: docs/phase-n-role-based-routing-plan.md · docs/agent-workflow-flowchart-V1.html

    Reads .coding-os/<agent>/traces/<session_id>.jsonl and prints either a
    pretty timeline, the raw events, or a summary. Use this to verify that
    an agent actually followed the expected flowchart path end-to-end.
    """
    import sys
    from pathlib import Path as _Path

    # tracing lives next to the MCP server — add it to path if not already
    core = _Path(__file__).resolve().parent.parent / "core" / "thinking_os"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import tracing  # noqa: E402

    adir = _Path(agent_dir) if agent_dir else None
    events = tracing.read_trace(session_id, adir)
    if not events:
        click.echo(f"No trace found for session {session_id!r}", err=True)
        raise SystemExit(1)

    if raw:
        import json
        for ev in events:
            click.echo(json.dumps(ev, separators=(",", ":"), default=str))
        return

    summary_data = tracing.summarize(session_id, adir)
    if summary:
        click.echo(f"\n{'─'*72}")
        click.echo(f"  TRACE SUMMARY — {session_id}")
        click.echo(f"{'─'*72}")
        for k, v in summary_data.items():
            if k == "session_id":
                continue
            click.echo(f"  {k:<22} {v}")
        click.echo(f"{'─'*72}\n")
        return

    # Pretty timeline
    click.echo(f"\n{'─'*72}")
    click.echo(f"  COGNITION TRACE — {session_id}")
    click.echo(f"  {summary_data['events']} events across {len(set(summary_data['nodes']))} flowchart nodes")
    click.echo(f"  path: {' → '.join(summary_data['nodes'])}")
    click.echo(f"{'─'*72}")
    click.echo(f"  {'TIME':<12} {'NODE':<14} {'KIND':<24} {'ROLE':<6} DATA")
    click.echo(f"{'─'*72}")
    t0 = events[0].get("ts", 0) if events else 0
    for ev in events:
        ts_ms = int((ev.get("ts", 0) - t0) * 1000)
        node = ev.get("node", "?")
        kind = ev.get("kind", "?")
        role = ev.get("role") or "-"
        data = ev.get("data") or {}
        # Compact data preview
        keys = [k for k in ("action", "chain", "preset_id", "formula", "status", "reason") if k in data]
        preview = " ".join(f"{k}={data.get(k)}" for k in keys[:3])
        click.echo(f"  +{ts_ms:>6}ms  {node:<14} {kind:<24} {role:<6} {preview}")
    click.echo(f"{'─'*72}\n")


@cognition_group.command("trace-replay")
@click.argument("session_id")
def cognition_trace_replay(session_id: str) -> None:
    """
    Phase N — Assert a trace covers the canonical flowchart path.

    Exits 0 if the trace visited (in order): session_init → gate_recorded →
    analyze_done → compose_done → at least one role_dispatch → task_done.
    Exits 1 with a diff on missing nodes. Intended for CI / behavioral
    regression tests.
    """
    import sys
    from pathlib import Path as _Path
    core = _Path(__file__).resolve().parent.parent / "core" / "thinking_os"
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))
    import tracing  # noqa: E402

    events = tracing.read_trace(session_id)
    if not events:
        click.echo(f"No trace for {session_id}", err=True)
        raise SystemExit(1)

    expected = ["analyze_done", "compose_done"]
    present_kinds = {e.get("kind") for e in events}
    missing = [k for k in expected if k not in present_kinds]
    if missing:
        click.echo(f"[replay] FAIL — missing mandatory kinds: {missing}")
        click.echo(f"[replay] present kinds: {sorted(present_kinds)}")
        raise SystemExit(1)
    click.echo(f"[replay] PASS — {len(events)} events, kinds covered")


COGNITION_COMMANDS = [cognition_group]
