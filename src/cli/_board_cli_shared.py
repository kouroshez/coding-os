"""Shared plumbing for the `cos board`/`cos task-*` family: paths, DB handle, envelopes."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import click

# Bootstrap so imports work whether invoked via `cos` entry-point or bare python.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _project_root() -> Path:
    from thinking_os.database import project_root

    return project_root()


def _db_conn() -> sqlite3.Connection:
    root = _project_root()
    db_path = os.environ.get(
        "COS_DB_PATH",
        str(root / ".coding-os" / "coding-os.db"),
    )
    if not Path(db_path).exists():
        click.echo(f"ERROR: DB not found at {db_path}. Run `cos setup` first.", err=True)
        sys.exit(1)
    return sqlite3.connect(db_path)


def _known_agent_ids() -> tuple[frozenset[str], dict[str, tuple[str, ...]]]:
    """Load adapter ids + their runtime env markers from adapter registry."""
    from cli._resources import adapters_dir as _adapters_root

    adapters_dir = _adapters_root()
    try:
        from cli.adapter_registry import load_adapter_registry

        reg = load_adapter_registry(adapters_dir)
    except Exception as exc:
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

    DRIFT WARNING: The same priority table is maintained in shell form
             at src/core/hooks/cos-env.sh.  Update both sides when changing
             priorities.  Only the adapter-id names are data-driven; the
             overall ordering (explicit override → vendor markers →
             marker file → legacy Claude alias) lives in both files.
    """
    known_ids, markers_by_id = _known_agent_ids()

    explicit = (os.environ.get("COS_AGENT") or "").strip().lower()
    if explicit and explicit in known_ids:
        return explicit

    # Alphabetical sort keeps detection deterministic.  The env-marker
    # sets declared by each adapter.yaml don't overlap (CODEX_* vs
    # CLAUDE_*) so order is irrelevant to correctness — and
    # we never hardcode adapter-name literals here (rule #11).  The
    # legacy CLAUDE_PROJECT_DIR fallback below is the only place
    # disambiguation matters, and it gates on "no stronger marker
    # fired" so a real vendor-marker match already short-circuited.
    for agent_id in sorted(known_ids):
        for env_key in markers_by_id.get(agent_id, ()):
            if os.environ.get(env_key):
                return agent_id

    marker = _project_root() / ".coding-os" / ".agent"
    if marker.is_file():
        try:
            raw = marker.read_text(encoding="utf-8", errors="ignore").strip().lower()
        except OSError:
            raw = ""
        if raw and raw in known_ids:
            return raw

    # Legacy compatibility marker: other IDEs also set CLAUDE_PROJECT_DIR, so
    # only trust it when no stronger signal fired.  The target adapter id
    # is looked up rather than hardcoded so the Claude rename never
    # strands this path.
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        for aid in known_ids:
            if any(env_key.startswith("CLAUDE") for env_key in markers_by_id.get(aid, ())):
                return aid
    return None


def _agent_session_id() -> str | None:
    """Best-effort agent session resolver for CLI-originated task transitions."""
    sid = os.environ.get("COS_AGENT_SESSION_ID")
    if sid:
        return sid.strip() or None

    def _first(p: Path) -> str | None:
        if not p.is_absolute():
            p = _project_root() / p
        if not p.is_file():
            return None
        try:
            raw = p.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return None
        return raw or None

    # Panel-first (most accurate when a hook set $COS_PANEL_DIR), then the
    # agent-level fresh `.active-session` pointer session-context.sh keeps
    # current, then the legacy flat session-id fossil. Mirrors the MCP
    # server's _detect_agent_session_default.
    panel_dir_env = os.environ.get("COS_PANEL_DIR")
    if panel_dir_env:
        raw = _first(Path(panel_dir_env) / "session-id")
        if raw:
            return raw
    agent_dir_env = os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        for _fname in (".active-session", "session-id"):
            raw = _first(Path(agent_dir_env) / _fname)
            if raw:
                return raw

    runtime = _detect_agent_runtime()
    if runtime is None:
        return None
    # Plain shells (no COS_* env) land here. Mirror the env'd branch above:
    # `.active-session` is refreshed every prompt by session-context.sh,
    # while the flat `session-id` is a legacy fossil frozen at its last
    # SessionStart — trusting it first mis-attributed weeks-old session ids
    # to fresh CLI mutations (TASK-341).
    runtime_dir = _project_root() / ".coding-os" / runtime
    for _fname in (".active-session", "session-id"):
        raw = _first(runtime_dir / _fname)
        if raw:
            return raw
    return None


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
