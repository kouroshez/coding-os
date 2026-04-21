"""
PURPOSE:      Discover the per-agent state-dir markers (".claude/", ".codex/", ...)
              from adapters/<id>/adapter.yaml so that core/ stays agent-agnostic
              (Rule 1 / P2). Used by concepts.py and capture.py to classify
              file paths without hardcoding any agent name.
INPUT:        none — reads adapters/*/adapter.yaml at module import.
OUTPUT:       AGENT_STATE_PREFIXES — frozenset like {".claude/", ".codex/"}.
DEPENDENCIES: PyYAML (already a hard dep of coding-os).
NOTES:        Pure helper, no circular imports with cli/. Falls back to an
              empty set if the adapters dir is missing — callers must handle.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_ADAPTERS_DIR = Path(__file__).resolve().parent.parent.parent / "adapters"


@lru_cache(maxsize=1)
def agent_state_prefixes() -> frozenset[str]:
    """Return {".claude/", ".codex/", ...} read from adapter manifests."""
    if not _ADAPTERS_DIR.exists():
        return frozenset()

    prefixes: set[str] = set()
    for manifest in _ADAPTERS_DIR.glob("*/adapter.yaml"):
        try:
            data = yaml.safe_load(manifest.read_text()) or {}
        except yaml.YAMLError:
            continue
        # Each adapter declares hooks_dir/settings_file/rules_dir under its
        # private state root (e.g. ".claude/hooks"). Take the leading segment.
        for key in ("hooks_dir", "settings_file", "rules_dir", "skills_dir", "commands_dir"):
            value = data.get(key)
            if not isinstance(value, str):
                continue
            head = value.split("/", 1)[0]
            if head.startswith("."):
                prefixes.add(head + "/")
    return frozenset(prefixes)
