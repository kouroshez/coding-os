"""
GC stale presence files (`ended_at` >1h old, or unparseable + mtime >1h).

USAGE
    python3 presence_gc.py <presence_dir> <now_epoch>
"""
from __future__ import annotations

import json
import os
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        return 0
    d, now_s = argv[1], argv[2]
    try:
        now = int(now_s)
    except ValueError:
        return 0
    if not os.path.isdir(d):
        return 0
    for name in os.listdir(d):
        if not name.endswith(".json"):
            continue
        p = os.path.join(d, name)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            try:
                if now - os.path.getmtime(p) > 3600:
                    os.unlink(p)
            except OSError:
                pass
            continue
        ended = data.get("ended_at")
        if isinstance(ended, int) and now - ended > 3600:
            try:
                os.unlink(p)
            except OSError:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
