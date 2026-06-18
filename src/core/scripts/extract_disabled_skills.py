#!/usr/bin/env python3
"""Emit the project's opted-out skill names from .coding-os.yaml::disabled_skills.

Called from install-adapter.sh (form B — standalone file, never a heredoc — to
dodge the Homebrew bash heredoc deadlock, same rationale as extract_stacks.py)
so a re-install / `cos update` keeps a disabled core/stack skill unlinked. The
live toggle is done inline by cli.skill_commands.set_project_skill; this reader
only covers the fresh-install path.

USAGE:
    python3 extract_disabled_skills.py <project_config_path>

OUTPUT:
    space-separated skill names on stdout (empty + exit 0 when none / unreadable).
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(f"usage: {argv[0]} <project_config_path>\n")
        return 2
    try:
        import yaml
    except ImportError:
        return 0  # no yaml in this interpreter — inline apply path already ran
    try:
        with open(argv[1]) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return 0
    except yaml.YAMLError as exc:
        sys.stderr.write(f"config parse error: {exc}\n")
        return 0
    print(" ".join(str(s) for s in (data.get("disabled_skills") or [])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
