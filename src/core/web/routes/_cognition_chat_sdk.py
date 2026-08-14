"""Claude Agent SDK + adapter-dispatcher seam for the Hub chat routes.

Every construction of an SDK type crosses this module (P8: core never builds
ClaudeAgentOptions itself), together with the presence write the chat path owes
the Live-agents HUD. A leaf — it imports no sibling route module, so the chat
route groups never cycle through it.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy adapter-dispatcher probe state (moved with _adapter_dispatcher).
_ADAPTER_DISPATCHER_MOD = None
_ADAPTER_DISPATCHER_TRIED = False

# Lazy presence-writer probe state (moved with _chat_presence_write).
_CHAT_PRESENCE_WRITER = None
_CHAT_PRESENCE_TRIED = False

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))


CHAT_CAPABILITY = "chat"

# The port core is allowed to call. Anything outside this set means an adapter's
# own SDK surface leaked back into the kernel.
CHAT_PORT = (
    "list_sessions",
    "get_session_info",
    "get_session_messages",
    "stream_turn",
    "tool_guard",
)


def _chat_runtime():
    """The adapter module implementing the Hub chat port, or None.

    Resolved by CAPABILITY, not by importing a provider package: core previously
    imported the SDK module and called its own attribute names, so removing the
    literal `claude_agent_sdk` moved the coupling instead of ending it — a second
    runtime still had to expose those four names by coincidence. Now an adapter
    implements CHAT_PORT and declares `chat` in runtime_entrypoints.
    """
    from thinking_os.adapter_registry import load_adapter_records, load_entrypoint_module

    for record in load_adapter_records().values():
        if CHAT_CAPABILITY not in record.capabilities:
            continue
        module = load_entrypoint_module(record, CHAT_CAPABILITY)
        if module is None:
            continue
        if not all(callable(getattr(module, name, None)) for name in CHAT_PORT):
            logger.debug("%s declares chat but does not implement the port", record.id)
            continue
        if callable(getattr(module, "available", None)) and not module.available():
            logger.debug("%s chat runtime present but unavailable", record.id)
            continue
        return module
    return None


# Historical name kept so the route modules read the same either way; the thing
# returned is now the port, never a provider SDK.
_claude_sdk = _chat_runtime


def _project_cwd() -> str:
    from web._project_context import current_project_root

    return str(current_project_root())


def _adapter_dispatcher():
    """Load src/adapters/claude/sdk_dispatcher.py once — the adapter SDK-construction
    seam (P8: every ClaudeAgentOptions build crosses this boundary into the adapter)."""
    global _ADAPTER_DISPATCHER_MOD, _ADAPTER_DISPATCHER_TRIED
    if _ADAPTER_DISPATCHER_TRIED:
        return _ADAPTER_DISPATCHER_MOD
    _ADAPTER_DISPATCHER_TRIED = True
    try:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[3] / "adapters" / "claude" / "sdk_dispatcher.py"
        spec = importlib.util.spec_from_file_location("cos_adapter_claude_dispatcher", path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _ADAPTER_DISPATCHER_MOD = mod
    except Exception as exc:
        logger.debug("adapter dispatcher load failed: %s", exc)
    return _ADAPTER_DISPATCHER_MOD


def _session_options_builder():
    """The adapter's profile-based session-options builder (SSOT), or None."""
    mod = _adapter_dispatcher()
    return getattr(mod, "claude_session_options", None) if mod else None


def _build_agent_options(**kwargs):
    """Construct ClaudeAgentOptions via the adapter seam — P8: core never builds the
    SDK type itself. Raises if the adapter dispatcher cannot be loaded."""
    mod = _adapter_dispatcher()
    builder = getattr(mod, "claude_agent_options", None) if mod else None
    if builder is None:
        raise RuntimeError("claude adapter ClaudeAgentOptions seam unavailable")
    return builder(**kwargs)


def _chat_session_options(
    profile, *, cwd, model, system_prompt, effort=None, resume=None, fork=False
):
    """Build chat ClaudeAgentOptions via the adapter SSOT builder; on builder error
    fall back to the chat-light kwargs, still constructed through the adapter seam."""
    build = _session_options_builder()
    if build is not None:
        try:
            return build(
                profile,
                cwd=cwd,
                model=model,
                system_prompt=system_prompt,
                effort=effort,
                resume=resume,
                fork=fork,
            )
        except Exception as exc:
            logger.debug("session-options builder call failed (%s); generic seam fallback", exc)
    kwargs = {
        "cwd": cwd,
        "model": model,
        "permission_mode": "dontAsk",
        "setting_sources": [],
        "include_partial_messages": True,
        "system_prompt": system_prompt,
    }
    if effort:
        kwargs["effort"] = effort
    if profile == "chat_resume":
        if resume:
            kwargs["resume"] = resume
        kwargs["fork_session"] = fork
    return _build_agent_options(**kwargs)


def _chat_presence_write(cwd: str, sid: str, event: str) -> None:
    """Fire-and-forget Hub-chat presence so the chat shows in the Live-agents HUD (P13)."""
    # Reuse the adapter's unified 12-key writer and stamp the long-lived host
    # pid, so the board's glob reader sees the live chat session (the chat path
    # fires no shell hooks, so nothing else writes its presence).
    global _CHAT_PRESENCE_WRITER, _CHAT_PRESENCE_TRIED
    try:
        if not _CHAT_PRESENCE_TRIED:
            _CHAT_PRESENCE_TRIED = True
            import importlib.util
            from pathlib import Path as _Path

            path = (
                _Path(__file__).resolve().parents[3] / "adapters" / "claude" / "sdk_dispatcher.py"
            )
            spec = importlib.util.spec_from_file_location("cos_adapter_claude_presence", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _CHAT_PRESENCE_WRITER = getattr(mod, "_presence_write", None)
        if _CHAT_PRESENCE_WRITER is not None:
            import os
            from pathlib import Path as _Path

            _CHAT_PRESENCE_WRITER(_Path(cwd), "claude", sid, event, pid=os.getpid())
    except Exception as exc:
        logger.debug("chat presence write skipped (%s): %s", event, exc)
