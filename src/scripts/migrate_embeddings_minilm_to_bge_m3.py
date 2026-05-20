"""CLI — re-embed the existing `embeddings` table with BGE-M3 (Phase I.1).

DEPENDS:  core/thinking_os/migrator_embeddings.py.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=str, default=None, help="Override DB path.")
    parser.add_argument(
        "--target-model",
        type=str,
        default="BAAI/bge-m3",
        help="Target model for re-embedding.",
    )
    parser.add_argument("--batch-size", type=int, default=256, help="Rows per batch.")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=".coding-os/.embedding-migration.json",
        help="Checkpoint file path.",
    )
    parser.add_argument(
        "--max-batches",
        type=int,
        default=None,
        help="Optional cap (default: run until idle).",
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Report status without running any batches.",
    )
    args = parser.parse_args()

    thinking_os = Path(__file__).resolve().parent.parent.parent / "core" / "thinking_os"
    sys.path.insert(0, str(thinking_os))
    import migrator_embeddings  # type: ignore
    from database import init_db  # type: ignore

    conn = init_db(args.db)
    try:
        if args.status_only:
            report = migrator_embeddings.migration_status(
                conn,
                target_model=args.target_model,
                checkpoint_path=args.checkpoint,
            )
        else:
            report = migrator_embeddings.run_until_idle(
                conn,
                target_model=args.target_model,
                batch_size=args.batch_size,
                checkpoint_path=args.checkpoint,
                max_batches=args.max_batches,
            )
        print(json.dumps(report, indent=2, default=str))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
