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
