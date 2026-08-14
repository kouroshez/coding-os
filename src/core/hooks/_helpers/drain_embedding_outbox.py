"""Drain the embedding outbox off the interactive path (Stop-hook helper).

Fast-paths out with zero model load when the outbox is empty (the common case),
so it never adds latency to a normal session end. Fail-open: any missing dep or
error is a no-op — the outbox is durable, so a later drain / reindex catches up.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path


def main() -> int:
    root = os.environ.get("COS_PROJECT_ROOT", os.getcwd())
    sys.path.insert(0, str(Path(root) / "src" / "core" / "thinking_os"))
    try:
        from database import init_db, resolve_db_path  # type: ignore

        conn = init_db(str(resolve_db_path(Path(root))))
    except Exception as exc:  # deps/db missing → no-op, durable outbox retried later
        print(f"[outbox] drain skipped: {exc}", file=sys.stderr)
        return 0
    try:
        # Cheap fast-path: nothing pending → exit before importing the model.
        pending = conn.execute(
            "SELECT COUNT(*) FROM embedding_outbox WHERE attempts < 3"
        ).fetchone()[0]
        if not pending:
            return 0
        import embeddings  # type: ignore

        rep = embeddings.drain_outbox(conn, limit=64)
        # Report any batch that did work, including one that only dropped
        # source-less rows. Reporting on `drained` alone hid a starving queue
        # behind a silent success for two months.
        if rep.get("drained") or rep.get("dropped") or rep.get("failed"):
            print(
                f"[outbox] drained {rep.get('drained', 0)}, "
                f"dropped {rep.get('dropped', 0)} source-less, "
                f"failed {rep.get('failed', 0)}; "
                f"{rep.get('remaining', 0)} remaining",
                file=sys.stderr,
            )
        elif rep.get("status") != "ok":
            print(f"[outbox] drain {rep.get('status')}", file=sys.stderr)
    except Exception as exc:
        print(f"[outbox] drain error: {exc}", file=sys.stderr)
        return 0
    finally:
        with contextlib.suppress(Exception):
            conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
