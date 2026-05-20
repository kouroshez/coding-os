"""Decide whether a FILE_PATH matches one of the graph.enforce_context_on globs.

USAGE
    python3 graph_context_match.py <config_yaml_path> <file_path>
Prints "yes" or "no" on stdout.
"""

from __future__ import annotations

import fnmatch
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("no")
        return 0
    config_path, fp = argv[1], argv[2]
    try:
        import yaml
    except ImportError:
        print("no")
        return 0
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except OSError:
        print("no")
        return 0
    patterns = ((data.get("graph") or {}).get("enforce_context_on")) or []
    for pat in patterns:
        if fnmatch.fnmatchcase(fp, pat):
            print("yes")
            return 0
    print("no")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
