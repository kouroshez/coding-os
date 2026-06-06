"""Behavioral tracing (Cognition Trace Stream).

Flowchart nodes emitted correspond to the node IDs in
`docs/agent-workflow-flowchart-V1.html` so a viewer can animate exactly which
node was hit and in which order.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)
_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB → rotate
_TRACE_SUBDIR = "traces"

# Canonical flowchart-node mapping. Keep in sync with V1.html `data-role` IDs.
# Any `kind` emitted by the system must map to a flowchart node so replay works.
FLOWCHART_NODES: dict[str, str] = {
    # Entry lifecycle
    "session_init": "n-sinit",
    "gate_recorded": "n-gate",
    # Cognition layer
    "analyze_start": "n-analyzer",
    "analyze_done": "n-analyzer",
    "compose_done": "n-router",
    "situation_override": "n-router",
    "preset_matched": "n-router",
    "composer_fallback": "n-router",
    "hard_fallback": "n-router",
    # Supervisor
    "supervise_action": "n-supervisor",
    "role_dispatch": "n-supervisor",
    "role_output_recorded": "n-supervisor",
    "parallel_dispatch": "n-supervisor",
    # Dispatcher (real SDK execution, not just supervisor decision)
    "dispatch_started": "n-supervisor",
    "dispatch_completed": "n-supervisor",
    # Gates
    "ambiguity_check": "n-ambi",
    "ambiguity_violation": "n-ambi",
    "traceability_check": "n-trace",
    # Loops
    "backtrack": "n-supervisor",
    "discovery": "n-supervisor",
    "anti_paralysis_warn": "n-supervisor",
    # Execution
    "implementation": "n-impl",
    "verification": "n-verify",
    # Close
    "task_done": "n-done",
    "session_end": "n-end",
    # Errors
    "error": "n-supervisor",
}


def _trace_dir(agent_dir: Path | None = None) -> Path:
    """Resolve trace dir generically (Rule 1 — agent-agnostic).

    Resolution order: explicit arg → $COS_AGENT_DIR →
    $COS_STATE_DIR/$COS_AGENT → fallback ".coding-os/claude".
    """
    if agent_dir is None:
        import os as _os

        explicit = _os.environ.get("COS_AGENT_DIR")
        if explicit:
            agent_dir = Path(explicit)
        else:
            agent = _os.environ.get("COS_AGENT") or "claude"
            state = _os.environ.get("COS_STATE_DIR")
            base = Path(state) if state else Path(".coding-os")
            agent_dir = base / agent
    d = agent_dir / _TRACE_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _trace_path(session_id: str, agent_dir: Path | None = None) -> Path:
    return _trace_dir(agent_dir) / f"{session_id}.jsonl"


def _rotate_if_large(path: Path) -> None:
    """If trace file exceeds limit, rename to <session>.<ts>.jsonl and start fresh."""
    try:
        if path.exists() and path.stat().st_size >= _MAX_FILE_BYTES:
            ts = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
            path.rename(path.with_suffix(f".{ts}.jsonl"))
    except OSError as exc:
        _logger.debug("trace rotate skipped: %s", exc)


def emit(
    session_id: str,
    kind: str,
    data: dict[str, Any] | None = None,
    *,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span: str | None = None,
    agent_dir: Path | None = None,
    role: str | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    try:
        event = {
            "ts": time.time(),
            "session_id": session_id,
            "trace_id": trace_id or session_id,
            "span_id": span_id or uuid.uuid4().hex[:12],
            "parent_span": parent_span,
            "kind": kind,
            "node": FLOWCHART_NODES.get(kind, "unknown"),
            "role": role,
            "phase": phase,
            "data": data or {},
        }
        path = _trace_path(session_id, agent_dir)
        _rotate_if_large(path)
        line = json.dumps(event, separators=(",", ":"), default=str) + "\n"
        _append_locked(path, line)
        return event
    except Exception as exc:  # pragma: no cover — tracing must never break callers
        os.write(2, f"[tracing] failed kind={kind} exc={exc}\n".encode())
        return {"kind": kind, "error": str(exc)}


def _append_locked(path: Path, line: str) -> None:
    """Flock-safe append. Each write gets its own lock for multi-agent safety."""
    try:
        import fcntl

        with open(path, "a", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                fh.write(line)
            finally:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError as exc:
                    _logger.debug("trace flock release: %s", exc)
    except ImportError:
        # Windows — fall back to best-effort append
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)


def read_trace(session_id: str, agent_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return all events for a session in chronological order (as written)."""
    path = _trace_path(session_id, agent_dir)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                events.append({"kind": "corrupt", "raw": raw})
    except OSError:
        return []
    return events


def summarize(session_id: str, agent_dir: Path | None = None) -> dict[str, Any]:
    """
    Return a compact summary of the trace: node-sequence, counts, roles visited,
    presets/situations matched, violations. Useful for the `cos trace show` CLI
    and for behavioral tests that assert "chain visited the right nodes".
    """
    events = read_trace(session_id, agent_dir)
    if not events:
        return {"session_id": session_id, "events": 0, "nodes": [], "roles": []}

    nodes_sequence: list[str] = []
    roles_visited: list[str] = []
    kinds_counts: dict[str, int] = {}
    presets: list[str] = []
    situations: list[str] = []
    chain: list[str] | None = None
    violations: list[str] = []
    backtracks: int = 0
    discoveries: int = 0

    for ev in events:
        k = ev.get("kind")
        kinds_counts[k] = kinds_counts.get(k, 0) + 1
        node = ev.get("node")
        if node and (not nodes_sequence or nodes_sequence[-1] != node):
            nodes_sequence.append(node)
        if ev.get("role"):
            roles_visited.append(ev["role"])

        data = ev.get("data") or {}
        if k == "preset_matched":
            presets.append(data.get("preset_id", "?"))
        elif k == "situation_override":
            situations.append(data.get("situation_id", "?"))
        elif k == "compose_done":
            chain = data.get("chain") or chain
        elif k == "backtrack":
            backtracks += 1
        elif k == "discovery":
            discoveries += 1
        elif k == "ambiguity_violation":
            violations.append(f"{data.get('formula', '?')}/{data.get('criterion', '?')}")

    return {
        "session_id": session_id,
        "events": len(events),
        "first_ts": events[0].get("ts"),
        "last_ts": events[-1].get("ts"),
        "nodes": nodes_sequence,
        "roles": roles_visited,
        "kinds": kinds_counts,
        "preset": presets[-1] if presets else None,
        "situation": situations[-1] if situations else None,
        "chain": chain,
        "violations": violations,
        "backtracks": backtracks,
        "discoveries": discoveries,
    }
