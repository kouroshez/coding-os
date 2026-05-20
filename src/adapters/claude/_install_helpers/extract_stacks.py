#!/usr/bin/env python3
"""
Extract installed stack names from .coding-os/installed-manifest.json.

Called from install.sh (form B — separate file, NOT a heredoc) because
Homebrew bash 5.3.9 sporadically deadlocks BOTH `python3 - <<HEREDOC`
AND nested `$(python3 -c "$(cat <<'PY' ... PY)")` patterns inside
$(...) command substitutions. A standalone `.py` invoked as
`python3 path/to/file.py args` has no heredoc → no bug surface.

USAGE:
    python3 extract_stacks.py <manifest_path>

OUTPUT:
    space-separated stack names on stdout, e.g. "django nextjs"
    Empty stdout + exit 0 when manifest has no templates.
    Exit 1 + stderr message on parse error.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(f"usage: {argv[0]} <manifest_path>\n")
        return 2
    try:
        with open(argv[1]) as f:
            data = json.load(f)
    except FileNotFoundError:
        return 0  # no manifest yet — silent, install.sh skips the LINKER
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"manifest parse error: {exc}\n")
        return 1
    print(" ".join(data.get("templates", [])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
