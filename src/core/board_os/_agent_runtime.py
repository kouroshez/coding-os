"""Shared agent-runtime detection helper (E2 of Wave 0 audit fixes)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger("board_os.agent_runtime")

# Fallback when neither env nor explicit session names a known adapter.
_UNKNOWN_AGENT = "agent"

# Hard floor: we only ever return values from this set OR the explicit
# session string OR _UNKNOWN_AGENT. Adapter ids loaded at runtime extend
# the allowlist via _known_agent_ids().
_HUMAN_LITERAL = "human"


@lru_cache(maxsize=1)
def _known_agent_ids() -> tuple[frozenset[str], dict[str, tuple[str, ...]]]:
    """Load adapter ids + env markers from the adapter registry, cached."""
    here = Path(__file__).resolve()
    repo_root = here.parent.parent.parent  # core/board_os/<file> → repo root
    adapters_dir = repo_root / "adapters"

    try:
        # Lazy import — cli is not always on path (e.g. when called from
        # the MCP server). Detection must remain non-fatal.
        import sys

        cli_pkg = repo_root / "cli"
        if str(cli_pkg.parent) not in sys.path:
            sys.path.insert(0, str(cli_pkg.parent))
        from cli.adapter_registry import load_adapter_registry  # type: ignore

        reg = load_adapter_registry(adapters_dir)
    except Exception as exc:
        logger.debug(
            "adapter registry unreachable, agent detection degrades to marker-only: %s",
            exc,
        )
        return frozenset(), {}

    ids = frozenset(reg.keys())
    markers = {aid: tuple(p.runtime_env_markers) for aid, p in reg.items()}
    return ids, markers


def detect_agent(agent_session: str | None = None) -> str:
    """Return the adapter id of the currently running agent.

    Priority order (matches cos-env.sh shell logic):
      1. Explicit ``agent_session`` argument when it names a known id /
         human / literal substring.
      2. ``COS_AGENT`` env override.
      3. Adapter ``runtime_env_markers`` declared in adapter.yaml.
      4. Persisted ``.coding-os/.agent`` marker file.
      5. ``_UNKNOWN_AGENT`` fallback.

    The function never raises — agent attribution is best-effort and must
    not block tool dispatch.
    """
    known_ids, markers_by_id = _known_agent_ids()

    label = _from_explicit_session(agent_session, known_ids)
    if label is not None:
        return label

    explicit_env = (os.environ.get("COS_AGENT") or "").strip().lower()
    if explicit_env in known_ids or explicit_env == _HUMAN_LITERAL:
        return explicit_env

    for agent_id in sorted(known_ids):
        for env_key in markers_by_id.get(agent_id, ()):
            if os.environ.get(env_key):
                return agent_id

    marker_value = _read_agent_marker_file()
    if marker_value and (marker_value in known_ids or marker_value == _HUMAN_LITERAL):
        return marker_value

    return _UNKNOWN_AGENT


def _from_explicit_session(
    agent_session: str | None,
    known_ids: frozenset[str],
) -> str | None:
    """Best-effort match of an explicit session string to a known adapter."""
    if not agent_session:
        return None
    s = agent_session.strip().lower()
    if not s:
        return None
    # Match adapter ids by substring so callers can pass a fully-qualified
    # session id like "ses-claude-20260427-...". First exact match wins;
    # ties broken alphabetically (deterministic).
    for agent_id in sorted(known_ids):
        if agent_id in s:
            return agent_id
    if _HUMAN_LITERAL in s:
        return _HUMAN_LITERAL
    return agent_session.strip()[:24]


def _read_agent_marker_file() -> str:
    """Read ``.coding-os/.agent`` if present; return empty string otherwise."""
    state_dir = os.environ.get("COS_STATE_DIR")
    if state_dir:
        candidate = Path(state_dir) / ".agent"
    else:
        candidate = Path.cwd() / ".coding-os" / ".agent"
    if not candidate.is_file():
        return ""
    try:
        return candidate.read_text(encoding="utf-8", errors="ignore").strip().lower()
    except OSError as exc:
        logger.debug("agent marker read failed: %s", exc)
        return ""


def _read_active_session_pointer() -> str:
    """Read the freshest "who is calling" session pointer, panel-first.

    ``$COS_PANEL_DIR/session-id`` names THIS panel and is refreshed every
    prompt, so it is preferred over the agent-level ``.active-session``,
    which is shared across sibling panels and resolves last-writer-wins —
    the source of cross-panel attribution drift (one panel's board write
    landing under another's session). Parity with
    ``cli.board_commands._agent_session_id``. The agent-level pointer stays
    as the fallback for callers without a panel dir. Best-effort: ``""`` on
    any miss.
    """
    panel_dir = os.environ.get("COS_PANEL_DIR")
    if panel_dir:
        try:
            panel_value = (
                (Path(panel_dir) / "session-id")
                .read_text(encoding="utf-8", errors="ignore")
                .strip()
            )
        except OSError as exc:
            logger.debug("panel session-id read failed: %s", exc)
            panel_value = ""
        if panel_value:
            return panel_value

    agent_dir = os.environ.get("COS_AGENT_DIR")
    if agent_dir:
        pointer = Path(agent_dir) / ".active-session"
    else:
        state_dir = os.environ.get("COS_STATE_DIR")
        base = Path(state_dir) if state_dir else (Path.cwd() / ".coding-os")
        agent = (os.environ.get("COS_AGENT") or "").strip().lower() or detect_agent()
        if not agent or agent == _UNKNOWN_AGENT:
            return ""
        pointer = base / agent / ".active-session"
    try:
        return pointer.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError as exc:
        logger.debug("active-session pointer read failed: %s", exc)
        return ""


def resolve_agent_session(explicit: str | None = None) -> str | None:
    """Return the session id to attribute a board write to.

    Adapter-agnostic resolver shared by ``cos_task_create``,
    ``cos_task_move``, ``cos_work_log_append``, and any future board
    mutator. Priority order:

      1. ``explicit`` — caller-supplied session id wins.
      2. ``$COS_SESSION_FILE`` — written by ``cos-env.sh`` /
         ``session-context.sh`` at every ``SessionStart startup`` in the
         shape ``ses-<agent>-YYYYMMDD-HHMMSS-xxxx``.
      3. ``.active-session`` disk pointer — the current panel, refreshed
         every prompt; the bridge for the long-lived MCP server whose
         ``$COS_SESSION_FILE`` env is frozen/empty (TASK-168).
      4. ``$COS_SESSION_ID`` — direct env override (CI / test harness).
      5. Synthesised ``ses-<detected-agent>-pid<PID>`` fallback so the
         row never lands as ``NULL`` (which the board UI maps to the
         green ``H`` glyph by default — see
         ``core/web/ui/src/features/cos-board/useBoardStream.ts``).

    Never raises; never returns an empty string.
    """
    if explicit:
        s = explicit.strip()
        if s:
            return s

    session_file = os.environ.get("COS_SESSION_FILE")
    if session_file:
        try:
            value = Path(session_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.debug("session file read failed: %s", exc)
            value = ""
        if value:
            return value

    # The long-lived MCP server has a frozen/empty $COS_SESSION_FILE; the
    # agent-level .active-session pointer (refreshed every prompt by
    # session-context.sh) is the freshest "who is calling" signal. Reading it
    # here keeps MCP-created board writes attributed to the active panel
    # instead of the shared ses-<agent>-pid<server-pid> synthetic.
    pointer = _read_active_session_pointer()
    if pointer:
        return pointer

    env_id = (os.environ.get("COS_SESSION_ID") or "").strip()
    if env_id:
        return env_id

    agent = detect_agent()
    if agent and agent != _UNKNOWN_AGENT:
        return f"ses-{agent}-pid{os.getpid()}"
    return None


def human_actor() -> dict[str, str]:
    """Resolve the human operator's actor identity (future-auth-ready).

    No auth yet: the web panel acts as a single local human. Identity is
    sourced from ``$COS_HUMAN_ACTOR`` (shape ``id`` or ``id:Label``) so a
    later auth layer can set the authenticated user without touching
    callers; the ``human`` default keeps the no-auth panel working.
    """
    raw = (os.environ.get("COS_HUMAN_ACTOR") or _HUMAN_LITERAL).strip()
    actor_id, _, label = raw.partition(":")
    actor_id = actor_id.strip() or _HUMAN_LITERAL
    return {"type": "human", "id": actor_id, "label": label.strip() or actor_id}


def reset_cache() -> None:
    """Test-only: drop the cached registry so tests get fresh adapter data."""
    _known_agent_ids.cache_clear()


__all__ = ["detect_agent", "human_actor", "reset_cache", "resolve_agent_session"]
