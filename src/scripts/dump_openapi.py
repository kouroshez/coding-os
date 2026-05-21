#!/usr/bin/env python3
"""Dump the Hub FastAPI OpenAPI spec to docs/api/openapi.json.

The Hub's HTTP contract is otherwise only visible at runtime
(`GET /openapi.json` while `cos hub start` is running). Snapshotting
it into the repo gives offline consumers a stable contract file and
lets CI diff-guard against accidental API drift.

Usage:
    python3 src/scripts/dump_openapi.py            # write the snapshot
    python3 src/scripts/dump_openapi.py --check    # fail if drifted

Exit: 0 on success / in-sync; 1 on drift (--check); 2 on error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT = REPO_ROOT / "docs" / "api" / "openapi.json"


def _build_spec() -> dict:
    # Import lazily so a missing `web` extra produces a clean message.
    sys.path.insert(0, str(REPO_ROOT / "src" / "core"))
    try:
        from web.server import create_app
    except Exception as exc:  # pragma: no cover - import-time failure
        print(f"FAIL: cannot import the Hub app: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    app = create_app()
    return app.openapi()


def main(argv: list[str]) -> int:
    check_only = "--check" in argv[1:]
    spec = _build_spec()
    # Stable, deterministic serialization (sorted keys, 2-space indent).
    rendered = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    if check_only:
        if not SNAPSHOT.exists():
            print(f"FAIL: snapshot missing: {SNAPSHOT}", file=sys.stderr)
            return 1
        current = SNAPSHOT.read_text(encoding="utf-8")
        if current != rendered:
            print(
                "FAIL: OpenAPI spec drifted from docs/api/openapi.json.\n"
                "      Run: python3 src/scripts/dump_openapi.py",
                file=sys.stderr,
            )
            return 1
        print("OK: OpenAPI snapshot is in sync.")
        return 0

    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(rendered, encoding="utf-8")
    print(f"wrote {SNAPSHOT.relative_to(REPO_ROOT)} ({len(rendered)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
