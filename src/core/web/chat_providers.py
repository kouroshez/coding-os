"""Manifest-loaded Hub transcript providers."""

from __future__ import annotations

import importlib.util
import inspect
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_ADAPTERS_DIR = Path(__file__).resolve().parents[2] / "adapters"


@dataclass(frozen=True)
class ChatProvider:
    agent: str
    module: ModuleType


@lru_cache(maxsize=1)
def providers() -> tuple[ChatProvider, ...]:
    loaded: list[ChatProvider] = []
    if not _ADAPTERS_DIR.is_dir():
        return ()
    for adapter_dir in sorted(path for path in _ADAPTERS_DIR.iterdir() if path.is_dir()):
        manifest_path = adapter_dir / "adapter.yaml"
        if not manifest_path.is_file():
            continue
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.debug("chat provider manifest skipped %s: %s", manifest_path, exc)
            continue
        provider_name = manifest.get("chat_provider")
        agent = str(manifest.get("id") or adapter_dir.name)
        if not isinstance(provider_name, str) or Path(provider_name).name != provider_name:
            continue
        provider_path = adapter_dir / provider_name
        if not provider_path.is_file():
            logger.warning("chat provider missing for %s: %s", agent, provider_path)
            continue
        spec = importlib.util.spec_from_file_location(f"coding_os_chat_provider_{agent}", provider_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning("chat provider load failed for %s: %s", agent, exc)
            continue
        if callable(getattr(module, "available", None)) and module.available():
            loaded.append(ChatProvider(agent=agent, module=module))
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
