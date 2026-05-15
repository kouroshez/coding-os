from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        return 1
    path = Path(sys.argv[1])
    key = sys.argv[2]
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
