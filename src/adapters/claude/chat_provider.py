"""Claude's implementation of the Hub chat port.

The kernel used to call `sdk.list_sessions` / `get_session_info` /
`get_session_messages` / `query` on whatever module the adapter registry
resolved. That removed the *name* `claude_agent_sdk` from core but not the
coupling: a second runtime still had to expose those four attributes with those
signatures. The port lives here instead, so an adapter implements four
functions and core never touches a provider SDK's own surface.

Every function degrades to an empty/None result when the SDK is absent — the
Hub renders "runtime unavailable" rather than raising, and `available()` is what
the config probe reads to say so explicitly.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

_SDK_PACKAGE = "claude-agent-sdk"


class GuardUnavailableError(RuntimeError):
    """This runtime cannot carry the kernel's pre-tool-use policy."""


def _sdk() -> Any | None:
    try:
        import claude_agent_sdk

        return claude_agent_sdk
    except ImportError:
        return None


def available() -> bool:
    return _sdk() is not None


def requirement() -> dict[str, str]:
    return {
        "missing": f"the {_SDK_PACKAGE} package",
        "remedy": "uv sync --extra claude-sdk",
    }


def list_sessions(*, directory: str, limit: int) -> list[Any]:
    sdk = _sdk()
    if sdk is None:
        return []
    return list(sdk.list_sessions(directory=directory, limit=limit))


def get_session_info(session_id: str, *, directory: str) -> Any | None:
    sdk = _sdk()
    if sdk is None:
        return None
    return sdk.get_session_info(session_id, directory=directory)


def get_session_messages(session_id: str, *, directory: str, limit: int, offset: int) -> list[Any]:
    sdk = _sdk()
    if sdk is None:
        return []
    return list(
        sdk.get_session_messages(session_id, directory=directory, limit=limit, offset=offset)
    )


async def stream_turn(*, prompt: Any, options: Any) -> AsyncIterator[Any]:
    """Yield the runtime's turn events. Options are built by this adapter's dispatcher."""
    sdk = _sdk()
    if sdk is None:
        return
    async for event in sdk.query(prompt=prompt, options=options):
        yield event


def tool_guard(*, matcher: str, hooks: list[Any]) -> Any:
    """Wrap core-local hook callables in this runtime's pre-tool-use matcher type.

    Core supplies the closure (its policy); the SDK type that carries it is the
    adapter's business.

    Raises rather than returning None when the runtime is absent. Core drops the
    result straight into a session running `permission_mode="dontAsk"`, where the
    wrapped closure is the only thing scoping writes — a None there would remove
    the policy silently, and an unattended session would run unguarded.
    """
    sdk = _sdk()
    if sdk is None:
        raise GuardUnavailableError(
            f"{_SDK_PACKAGE} is not installed, so this adapter cannot carry a "
            f"pre-tool-use guard for {matcher!r}. Refuse the session rather than "
            f"starting it without the policy."
        )
    return sdk.HookMatcher(matcher=matcher, hooks=hooks)
