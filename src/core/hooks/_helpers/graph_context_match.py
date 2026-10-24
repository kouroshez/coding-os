"""Decide whether a FILE_PATH matches the graph-context gate's globs.

USAGE
    python3 graph_context_match.py <config_yaml_path> <file_path>
Prints "strict" (graph.enforce_strict_on), "yes" (graph.enforce_context_on) or "no".
"""

from __future__ import annotations

import fnmatch
import sys


def tier(config_path: str, file_path: str) -> str:
    try:
        import yaml
    except ImportError:
        return "no"
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        return "no"
    graph = data.get("graph") or {}
    for name, key in (("strict", "enforce_strict_on"), ("yes", "enforce_context_on")):
        if any(fnmatch.fnmatchcase(file_path, pat) for pat in graph.get(key) or []):
            return name
    return "no"


def matches(config_path: str, file_path: str) -> bool:
    return tier(config_path, file_path) != "no"


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("no")
        return 0
    print(tier(argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
