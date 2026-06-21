"""Decide whether a FILE_PATH matches one of the graph.enforce_context_on globs.

USAGE
    python3 graph_context_match.py <config_yaml_path> <file_path>
Prints "yes" or "no" on stdout.
"""

from __future__ import annotations

import fnmatch
import sys


def matches(config_path: str, file_path: str) -> bool:
    try:
        import yaml
    except ImportError:
        return False
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        return False
    patterns = ((data.get("graph") or {}).get("enforce_context_on")) or []
    return any(fnmatch.fnmatchcase(file_path, pat) for pat in patterns)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("no")
        return 0
    print("yes" if matches(argv[1], argv[2]) else "no")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
