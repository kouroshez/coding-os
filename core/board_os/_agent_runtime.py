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
    except Exception as exc:  # noqa: BLE001 — detection is best-effort
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


def reset_cache() -> None:
    """Test-only: drop the cached registry so tests get fresh adapter data."""
    _known_agent_ids.cache_clear()


__all__ = ["detect_agent", "reset_cache"]
