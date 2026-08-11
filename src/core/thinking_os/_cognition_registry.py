"""Coding OS — Formula-agent + situation registry loaders."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("coding_os.cognition")

# ---------------------------------------------------------------------------
# Registry paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve().parent
AGENTS_DIR = _HERE / "agents"
SITUATIONS_DIR = _HERE / "situations"

# ---------------------------------------------------------------------------
# Registry loaders (cached at module level after first load)
# ---------------------------------------------------------------------------

_situation_registry: dict[str, dict[str, Any]] | None = None
_agent_registry: dict[str, dict[str, Any]] | None = None


def _load_yaml(path: Path) -> Any:
    with path.open() as fh:
        return yaml.safe_load(fh)


def load_situation_registry() -> dict[str, dict[str, Any]]:
    global _situation_registry
    if _situation_registry is None:
        reg = _load_yaml(SITUATIONS_DIR / "registry.yaml")
        _situation_registry = {s["id"]: s for s in reg.get("situations", [])}
    return _situation_registry


def load_agent_registry() -> dict[str, dict[str, Any]]:
    global _agent_registry
    if _agent_registry is not None:
        return _agent_registry
    registry: dict[str, dict[str, Any]] = {}
    for agent_file in sorted(AGENTS_DIR.glob("*.md")):
        if agent_file.name == "README.md":
            continue
        text = agent_file.read_text()
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                meta = yaml.safe_load(parts[1]) or {}
                # Chat-only roles (e.g. onboarder) live in agents/ so the chat
                # role picker lists them, but they are NOT formula agents — keep
                # them out of the formula registry so the 11-role contract holds.
                if meta.get("chat_only"):
                    continue
                fid = meta.get("id", agent_file.stem)
                meta["_file"] = agent_file.name
                registry[str(fid)] = meta
    _agent_registry = registry
    return _agent_registry
