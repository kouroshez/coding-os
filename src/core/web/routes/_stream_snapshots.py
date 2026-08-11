"""core.web.routes.stream — presence + activity snapshots read from presence files."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("coding_os.web.stream")


def _snapshot_activity() -> dict[str, dict[str, int | str | None]]:
    """{agent: {ts, kind, sid}} where ts = max(last_tool_at, last_prompt_at).

    Drives the agent-activity SSE event so the stream panel surfaces
    tool/prompt fires, not just task transitions.  Returns empty on
    import failure — agents lacking presence files are simply absent.
    """
    try:
        from board_os.hub_adapter_manifest import list_agent_manifest_rows  # type: ignore
        from web.routes.board import _presence_files  # type: ignore
    except ImportError as exc:
        logger.debug("activity import failed: %s", exc)
        return {}
    out: dict[str, dict[str, int | str | None]] = {}
    for r in list_agent_manifest_rows():
        agent = str(r.get("id") or "")
        if not agent:
            continue
        best_ts = 0
        best_kind: str | None = None
        best_sid: str | None = None
        for path in _presence_files(agent):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("ended_at") is not None:
                continue
            for kind, key in (("tool", "last_tool_at"), ("prompt", "last_prompt_at")):
                ts = data.get(key)
                if isinstance(ts, int) and ts > best_ts:
                    best_ts = ts
                    best_kind = kind
                    best_sid = data.get("session_id") or path.stem
        if best_ts:
            out[agent] = {"ts": best_ts, "kind": best_kind, "sid": best_sid}
    return out


def _snapshot_presence() -> dict[str, str]:
    """Return {agent_id: state} snapshot — drives presence-updated SSE diff.

    Imported lazily because board.py mounts later in the app graph and a
    top-level import would create a cycle on cold reload.
    """
    try:
        from board_os.hub_adapter_manifest import list_agent_manifest_rows  # type: ignore
        from web.routes.board import _presence_state  # type: ignore
    except ImportError as exc:
        logger.debug("presence import failed: %s", exc)
        return {}
    snap: dict[str, str] = {}
    for r in list_agent_manifest_rows():
        agent = str(r.get("id") or "")
        if not agent:
            continue
        try:
            snap[agent] = _presence_state(agent)
        except Exception as exc:
            logger.debug("presence snapshot failed for %s: %s", agent, exc)
    return snap
