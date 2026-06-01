"""Regenerate the always-active agent digest (.coding-os/digest.md).

Called by session-context.sh at SessionStart:startup BEFORE the digest is
printed. The digest is the "working memory" half of the brain model — a small
high-signal summary (identity, top domains, beliefs, fading patterns,
breakthroughs, preferences) injected into every session. It was printed but
NEVER regenerated (cos_digest_regenerate had zero hook callers, so the file
never existed); this helper closes that gap (TASK-055).

Fail-open: prints nothing, exits 0 on any error. The print step in the hook
tolerates a missing file.

USAGE
    python3 digest_regen.py <db_path> <project_root>
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger("digest_regen")

_THIS = Path(__file__).resolve()
_THINKING_OS = _THIS.parents[2] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    db_path, project_root = argv[1], argv[2]
    if not db_path or not Path(db_path).exists():
        return 0
    try:
        import digest
    except ImportError as exc:
        logger.debug("digest import unavailable: %s", exc)
        return 0
    try:
        conn = sqlite3.connect(db_path, timeout=3)
        conn.row_factory = sqlite3.Row
        try:
            digest.regenerate(conn, project_root=Path(project_root))
        finally:
            conn.close()
    except Exception as exc:  # never break the startup hook
        logger.debug("digest.regenerate failed: %s", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
