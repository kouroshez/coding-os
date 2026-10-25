"""The composed role chain an agent is running, read from its state files.

The live-agent cards (`presence.py`) show it; nothing else in the Hub does.
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

from ._bounded_read import safe_segment


def _newest_marker(agent_dir: Path, basename: str) -> str | None:
    """Newest copy of a per-panel marker across agent_dir + every panels/*/.

    Role markers (.roles, .role) live under panels/<id>/, and the panel id is
    not stable across hook subprocesses, so one session's markers scatter and
    the agent-level copy is a stale fossil. The newest mtime is the live value.
    """
    candidates = [agent_dir / basename]
    panels = agent_dir / "panels"
    if panels.is_dir():
        with contextlib.suppress(OSError):
            candidates.extend(p / basename for p in panels.iterdir() if p.is_dir())
    best_text: str | None = None
    best_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            try:
                best_text = path.read_text(encoding="utf-8")
                best_mtime = mtime
            except OSError:
                continue
    return best_text


def _read_trace_events(state: Path, agent: str, session_id: str) -> list[dict[str, Any]]:
    # Both arguments become path segments, so a '../' in either would read
    # outside the state dir.
    if not safe_segment(agent) or not safe_segment(session_id):
        return []
    path = state / agent / "traces" / f"{session_id}.jsonl"
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return events


def resolve_chain(state: Path, agent: str) -> tuple[list[str], str | None]:
    """The agent's composed role chain + active role — trace-first, marker fallback."""
    if not safe_segment(agent):
        return [], None
    agent_dir = state / agent
    # Active role is the freshest per-panel signal (what the agent is DOING).
    active_raw = _newest_marker(agent_dir, ".role")
    active_formula = (active_raw.strip() or None) if active_raw else None

    # Chain: prefer the newest agent-level compose_done trace; scattered
    # per-panel .roles markers can be stale under concurrent panels.
    chain: list[str] = []
    traces_dir = agent_dir / "traces"
    if traces_dir.exists():
        for path in sorted(traces_dir.glob("*.jsonl"), reverse=True):
            for event in reversed(_read_trace_events(state, agent, path.stem)):
                if event.get("kind") == "compose_done":
                    chain = [str(x) for x in (event.get("data", {}) or {}).get("chain", [])]
                    break
            if chain:
                break

    if not chain:
        raw = _newest_marker(agent_dir, ".roles")
        if raw:
            raw = raw.strip()
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    chain = [str(x) for x in parsed]
            except json.JSONDecodeError:
                chain = [x.strip() for x in raw.split(",") if x.strip()]
    return chain, active_formula
