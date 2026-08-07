"""Manifest-loaded Hub transcript providers."""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from functools import lru_cache
from types import ModuleType
from typing import Any

from thinking_os.adapter_registry import load_adapter_records, load_entrypoint_module

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatProvider:
    agent: str
    module: ModuleType


@lru_cache(maxsize=1)
def providers() -> tuple[ChatProvider, ...]:
    loaded: list[ChatProvider] = []
    for record in load_adapter_records().values():
        if "transcript" not in record.capabilities:
            continue
        module = load_entrypoint_module(record, "transcript")
        if module is None:
            continue
        if callable(getattr(module, "available", None)) and module.available():
            loaded.append(ChatProvider(agent=record.id, module=module))
    return tuple(loaded)


async def _invoke(provider: ChatProvider, method: str, *args: Any) -> Any:
    value = getattr(provider.module, method)(*args)
    return await value if inspect.isawaitable(value) else value


async def list_sessions(cwd: str, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    sources: list[str] = []
    for provider in providers():
        try:
            provider_rows = await _invoke(provider, "list_sessions", cwd, limit)
        except Exception as exc:
            logger.warning("%s chat list failed: %s", provider.agent, exc)
            continue
        for row in provider_rows:
            row.setdefault("agent", provider.agent)
            rows.append(row)
        sources.append(provider.agent)
    return rows, sources


async def get_session(
    session_id: str,
    cwd: str,
    limit: int,
    offset: int,
    agent_hints: set[str] | None = None,
) -> dict[str, Any] | None:
    candidates = list(providers())
    if agent_hints:
        candidates.sort(key=lambda provider: provider.agent not in agent_hints)
    for provider in candidates:
        if agent_hints and provider.agent not in agent_hints:
            continue
        try:
            data = await _invoke(provider, "get_session", session_id, cwd, limit, offset)
        except Exception as exc:
            logger.warning("%s chat read failed for %s: %s", provider.agent, session_id, exc)
            continue
        if data is not None:
            data.setdefault("meta", {}).setdefault("agent", provider.agent)
            data.setdefault("session", {}).setdefault("agent", provider.agent)
            return data
    return None
