"""core.web.routes.presence — /api/presence/* live HUD summary."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

logger = logging.getLogger("coding_os.web.presence")

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

router = APIRouter(prefix="/api/presence", tags=["presence"])


def _state_dir() -> Path:
    from web._project_context import current_project_root, is_explicit_project_scope  # type: ignore

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os"
    env = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if env:
        return Path(env).resolve()
    return current_project_root() / ".coding-os"


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def _strip_session_prefix(value: str | None, session_id: str | None) -> str | None:
    """write-state.sh prefixes each value with the writer's session/panel id — strip it."""
    if not value:
        return value
    if session_id and value.startswith(session_id):
        return value[len(session_id) :].strip() or None
    # The prefix token is whatever write-state.sh had: a ses-… session id, a
    # ppid-… panel id, or a raw UUID panel id (the fallback when the panel
    # session-id file is unseeded — common on Claude, whose per-tool-call hook
    # subprocesses each resolve a fresh ppid panel). Strip whichever leads.
    import re as _re

    m = _re.match(
        r"^(?:ses-\S+|ppid-\S+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27})\s+(.*)$",
        value,
    )
    if m:
        return m.group(1).strip() or None
    return value


def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _latest_claude_chat_uuid(project_root: Path) -> str | None:
    """Newest Claude SDK transcript file (proxy for currently-active chat)."""
    try:
        from claude_agent_sdk import project_key_for_directory  # type: ignore

        key = project_key_for_directory(project_root)
    except Exception as exc:
        logger.debug("project_key_for_directory unavailable: %s", exc)
        key = "-" + str(project_root).replace("/", "-").lstrip("-")
    base = Path.home() / ".claude" / "projects" / key
    if not base.is_dir():
        return None
    newest: Path | None = None
    newest_mtime = 0.0
    for jsonl in base.glob("*.jsonl"):
        try:
            mt = jsonl.stat().st_mtime
        except OSError:
            continue
        if mt > newest_mtime:
            newest = jsonl
            newest_mtime = mt
    if newest is None:
        return None
    return newest.stem


def _newest_marker(agent_dir: Path, basename: str) -> str | None:
    """Newest copy of a per-panel marker across agent_dir + every panels/*/.

    Post-TASK-035 the cognitive-state markers (.task-current,
    .thinking_os-gate, .active-skill) live under panels/<id>/. The panel id is
    NOT stable across Claude's per-tool-call hook subprocesses, so one
    session's markers scatter across many ppid-* panels and the agent-level
    copy is a stale fossil. The HUD wants the live value, so the newest mtime
    wins (empty newest → None, i.e. "no current value").
    """
    candidates = [agent_dir / basename]
    panels = agent_dir / "panels"
    if panels.is_dir():
        try:
            candidates.extend(p / basename for p in panels.iterdir() if p.is_dir())
        except OSError as exc:
            logger.debug("panel scan failed for %s: %s", agent_dir, exc)
    best_text: str | None = None
    best_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best_text = _read_text(path)
    return best_text


def _agent_runtime(agent_dir: Path, agent: str) -> dict[str, Any] | None:
    """Best-effort runtime snapshot for one agent."""
    if not agent_dir.is_dir():
        return None
    # Prefer the live panel-scoped session-id marker; the flat agent-level
    # session-id is a startup fossil nothing writes anymore (P7).
    sid = _newest_marker(agent_dir, "session-id") or _read_text(agent_dir / "session-id")
    task = _strip_session_prefix(_newest_marker(agent_dir, ".task-current"), sid)
    skill_active = _strip_session_prefix(_newest_marker(agent_dir, ".active-skill"), sid)
    gate = _strip_session_prefix(_newest_marker(agent_dir, ".thinking_os-gate"), sid)
    session_payload = None
    if sid:
        session_payload = _read_json(agent_dir / "sessions" / f"{sid}.json")
    # Model is per-session — the shared $COS_AGENT_DIR/.model file is a
    # stale fallback (gets overwritten by whichever runtime started last
    # and never cleaned up).  Prefer sessions/<sid>.json::model so two
    # concurrent agents on the same project can disagree on model without
    # one trampling the other's display.
    model: str | None = None
    if isinstance(session_payload, dict):
        candidate = session_payload.get("model")
        if isinstance(candidate, str) and candidate.strip():
            model = candidate.strip()
    if not model:
        model = _strip_session_prefix(_read_text(agent_dir / ".model"), sid)
    return {
        "agent": agent,
        "session_id": sid,
        "task": task,
        "skill_active": skill_active,
        "model": model,
        "gate": gate,
        "session": session_payload,
    }


def _last_hook_event(state: Path) -> dict[str, Any] | None:
    log = state / ".hooks.log"
    if not log.exists():
        return None
    try:
        with log.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            window = min(size, 8192)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    from .hooks import _parse_hook_line  # type: ignore

    for line in reversed(tail.splitlines()):
        evt = _parse_hook_line(line)
        if evt is not None:
            return evt
    return None


def _canonical_agents() -> list[str]:
    """Return the canonical adapter ids (scanned from src/adapters, fails soft)."""
    from board_os.hub_adapter_manifest import list_agent_ids  # type: ignore

    return list_agent_ids()


def _project_slug(project_root: Path) -> str | None:
    """Owning-project registry slug for a resolved root (fail-soft, TASK-435).

    Home-level presence surfaces render at the unscoped '/' route and cannot
    read a slug from the URL, so each agent carries its project's slug to build
    an explicit /p/<slug>/cognition/... link instead of an unscoped one."""
    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception as exc:
        logger.debug("load_registry unavailable for slug stamp: %s", exc)
        reg = None
    if reg is not None:
        for entry in reg.projects:
            try:
                if Path(entry.path).resolve() == project_root:
                    return entry.slug
            except OSError:
                continue
    try:
        from cli.registry import _derive_slug  # type: ignore

        return _derive_slug(project_root)
    except Exception as exc:
        logger.debug("_derive_slug unavailable: %s", exc)
        return None


@router.get("/now")
def presence_now(
    _rl=Depends(make_rate_limit_dep("presence.now")),
    _m=Depends(make_metrics_dep("presence.now")),
):
    """Compact 'who is running, doing what, last hook fire' for the AppShell HUD."""
    from web._project_context import current_project_root  # type: ignore

    project = current_project_root()
    slug = _project_slug(project)
    state = _state_dir()
    canonical = _canonical_agents()

    agents: list[dict[str, Any]] = []
    if state.is_dir():
        for agent_id in canonical:
            agent_dir = state / agent_id
            snap = _agent_runtime(agent_dir, agent_id)
            if snap is None:
                continue
            agents.append(snap)

    last_hook = _last_hook_event(state)
    chat_uuid = _latest_claude_chat_uuid(project)

    # Use the same presence math as `/api/board/list` so the AppShell HUD
    # and the Scrumban board agree on agent state.
    agent_states: dict[str, str] = {"human": "active"}
    try:
        from web.routes.board import _agent_state, _db_conn  # type: ignore

        conn = _db_conn()
        try:
            for agent_id in canonical:
                agent_states[agent_id] = _agent_state(conn, agent_id)
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("agent_state lookup failed; using bare presence: %s", exc)

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "project_root": str(project),
                    "slug": slug,
                    "state_dir": str(state),
                    "agents": agents,
                    "agent_states": agent_states,
                    "last_hook": last_hook,
                    "current_chat_uuid": chat_uuid,
                    "meta": {"layer": "presence"},
                },
            }
        )
    )


def _context_window(model: str | None) -> int:
    """Context-window size for a model id: 1M for a `[1m]` id, else 200K."""
    return 1_000_000 if (model and "[1m]" in model) else 200_000


def _context_pct_from_used_tokens(used_tokens: Any, model: str | None) -> float | None:
    """Pure: context percent from a pre-summed token count + model.

    Reads the `used_tokens` value the Stop hook stamps into sessions/<sid>.json
    (TASK-255). Honest-null when there is no usable count (TASK-192)."""
    try:
        used = int(used_tokens)
    except (TypeError, ValueError):
        return None
    if used <= 0:
        return None
    return round(min(100.0, used / _context_window(model) * 100.0), 1)


def _context_pct_from_usage(usage: dict, model: str | None) -> float | None:
    """Pure: context-window percent from a transcript usage block + model.

    1M window for a `[1m]` model id, else 200K. Returns None when there is no
    usable token count — never a fabricated number (TASK-192)."""
    if not isinstance(usage, dict):
        return None
    used = sum(
        int(usage.get(k) or 0)
        for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    if used <= 0:
        return None
    return round(min(100.0, used / _context_window(model) * 100.0), 1)


def _latest_transcript_usage(transcript_path: Path) -> dict | None:
    """Tail the in-tree snapshot transcript for the most recent usage block.

    Cheap (last 256 KB only), fail-open. Only Claude writes these snapshots,
    so non-Claude agents naturally yield no usage."""
    try:
        with transcript_path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            window = min(size, 256 * 1024)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("usage"), dict):
            return msg["usage"]
        if isinstance(obj.get("usage"), dict):
            return obj["usage"]
    return None


@router.get("/agents")
def presence_agents(
    _rl=Depends(make_rate_limit_dep("presence.agents")),
    _m=Depends(make_metrics_dep("presence.agents")),
):
    """Unified per-agent live snapshot — model+gate+task+skill+role+chain+lifecycle+sdk_uuid in ONE call."""
    from web._project_context import current_project_root  # type: ignore

    project = current_project_root()
    slug = _project_slug(project)
    state = _state_dir()
    canonical = _canonical_agents()

    # Lifecycle state from the same SSOT the board uses.
    states: dict[str, str] = {}
    try:
        from web.routes.board import _agent_state, _db_conn  # type: ignore

        conn = _db_conn()
        try:
            for agent_id in canonical:
                states[agent_id] = _agent_state(conn, agent_id)
        finally:
            conn.close()
    except Exception as exc:
        logger.debug("agent_state lookup failed: %s", exc)

    try:
        from web.routes.roles import resolve_chain  # type: ignore
    except Exception:
        resolve_chain = None  # type: ignore

    agents: list[dict[str, Any]] = []
    if state.is_dir():
        for agent_id in canonical:
            snap = _agent_runtime(state / agent_id, agent_id)
            if snap is None:
                continue
            chain: list[str] = []
            role: str | None = None
            if resolve_chain is not None:
                try:
                    chain, role = resolve_chain(state, agent_id)
                except Exception as exc:
                    logger.debug("resolve_chain failed for %s: %s", agent_id, exc)
            sess = snap.get("session")
            sdk_uuid = sess.get("sdk_uuid") if isinstance(sess, dict) else None
            # Context-window % — Claude-only; honest null for adapters with no
            # usage signal. Primary source: used_tokens stamped on the Stop
            # path (TASK-255, no opt-in needed). Fallback: the opt-in snapshot
            # transcript tail (COS_SNAPSHOT_TRANSCRIPT=1).
            context_pct: float | None = None
            sid = snap.get("session_id")
            if isinstance(sess, dict) and sess.get("used_tokens") is not None:
                context_pct = _context_pct_from_used_tokens(
                    sess.get("used_tokens"), snap.get("model")
                )
            if context_pct is None and sid:
                tpath = state / agent_id / "sessions" / "transcripts" / f"{sid}.jsonl"
                if tpath.exists():
                    usage = _latest_transcript_usage(tpath)
                    if usage:
                        context_pct = _context_pct_from_usage(usage, snap.get("model"))
            agents.append(
                {
                    "agent": agent_id,
                    "session_id": snap.get("session_id"),
                    "sdk_uuid": sdk_uuid,
                    "slug": slug,
                    "model": snap.get("model"),
                    "gate": snap.get("gate"),
                    "task": snap.get("task"),
                    "skill_active": snap.get("skill_active"),
                    "role": role,
                    "chain": chain,
                    "state": states.get(agent_id, "offline"),
                    "context_pct": context_pct,
                    "used_tokens": (sess.get("used_tokens") if isinstance(sess, dict) else None),
                    "context_window": _context_window(snap.get("model")),
                }
            )

    return unwrap(
        json.dumps(
            {
                "ok": True,
                "data": {
                    "project_root": str(project),
                    "state_dir": str(state),
                    "agents": agents,
                    "meta": {"layer": "presence"},
                },
            }
        )
    )
