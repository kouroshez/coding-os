from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        return 1
    path = Path(sys.argv[1])
    key = sys.argv[2]
    # Exclusive flock across the whole read-modify-write so two concurrent
    # hooks can't both consume the same one-shot override. On a
    # platform without fcntl, or if the file is missing, fall back to the
    # best-effort non-atomic path (the override file rarely contends).
    try:
        import fcntl

        with open(path, "r+", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            except OSError as exc:
                # Lock unsupported (e.g. some network filesystems) — proceed
                # best-effort rather than fail the override consumption.
                sys.stderr.write(f"consume_override: flock unavailable: {exc}\n")
            try:
                data = json.loads(fh.read() or "{}")
            except json.JSONDecodeError:
                return 1
            if not isinstance(data, dict) or key not in data:
                return 1
            del data[key]
            fh.seek(0)
            fh.write(json.dumps(data, indent=2) + "\n")
            fh.truncate()
        return 0
    except (OSError, ImportError):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return 1
        if not isinstance(data, dict) or key not in data:
            return 1
        del data[key]
        path.write_text(json.dumps(data, indent=2) + "\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
