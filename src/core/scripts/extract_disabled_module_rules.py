#!/usr/bin/env python3
"""Emit core-rule filenames owned ONLY by disabled subsystem modules.

Called from install-adapter.sh (form B — standalone file, never a heredoc — to
dodge the Homebrew bash heredoc deadlock, same rationale as extract_stacks.py)
so a fresh install / `cos update` keeps a disabled module's rule unlinked.
Ref-counted: a rule co-owned by any ENABLED module (kernel is always enabled) is
never emitted. The live toggle is done inline by
cli.module_commands.cascade_module_rules; this reader only covers the
fresh-install path (mirrors extract_disabled_skills.py).

USAGE:
    python3 extract_disabled_module_rules.py <project_root>

OUTPUT:
    space-separated rule filenames on stdout (empty + exit 0 when none / unreadable).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _is_enabled(module: dict, disabled: set[str]) -> bool:
    return bool(module.get("kernel")) or str(module.get("id")) not in disabled


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(f"usage: {argv[0]} <project_root>\n")
        return 2
    try:
        import yaml
    except ImportError:
        return 0  # no yaml in this interpreter — inline apply path already ran
    manifest = Path(__file__).resolve().parents[1] / "subsystems.yaml"
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return 0
    state_file = Path(argv[1]) / ".coding-os" / "subsystems-state.json"
    try:
        disabled = {
            str(x)
            for x in (json.loads(state_file.read_text(encoding="utf-8")).get("disabled") or [])
        }
    except (OSError, json.JSONDecodeError):
        return 0
    if not disabled:
        return 0
    modules = data.get("modules") or []
    enabled_owned = {
        rule for m in modules if _is_enabled(m, disabled) for rule in (m.get("rules") or [])
    }
    drop = {
        rule
        for m in modules
        if not _is_enabled(m, disabled)
        for rule in (m.get("rules") or [])
        if rule not in enabled_owned
    }
    print(" ".join(sorted(drop)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
