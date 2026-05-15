from __future__ import annotations

import json
import shlex
import sys

RESERVED_KEYS = ("ts", "lvl", "scope", "msg")


def main() -> int:
    if len(sys.argv) < 6:
        return 1
    ts, level, scope, message, kv_blob = sys.argv[1:6]
    event = {"ts": ts, "lvl": level, "scope": scope, "msg": message}
    if kv_blob:
        for token in shlex.split(kv_blob):
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key in RESERVED_KEYS or key in event:
                continue
            event[key] = value
    sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
