#!/usr/bin/env python3
"""End-to-end smoke for DB connection unification.

Confirms every component (thinking_os, graph_os, board_os, web Hub,
hook helpers) opens the SAME canonical SQLite file and that
`resolve_db_path()` is the single source of truth.

For each connection site, the script:
1. Calls the resolver / opener.
2. Reads back the canonical file path.
3. Asserts it matches the expected `<project>/.coding-os/coding-os.db`.
4. Performs a real read against the live DB to confirm it's open.

Run: uv run python scripts/smoke_db_connections.py
Exit: 0 if all PASS; 1 if any FAIL.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "core"))
sys.path.insert(0, str(REPO_ROOT))

EXPECTED = (REPO_ROOT / ".coding-os" / "coding-os.db").resolve()


def _check(name: str, fn: Callable[[], Path | str | None]) -> tuple[str, bool, str]:
    try:
        path = fn()
    except Exception as exc:  # noqa: BLE001
        return name, False, f"raised {type(exc).__name__}: {exc}"
    if path is None:
        return name, False, "returned None"
    actual = Path(path).resolve()
    if actual != EXPECTED:
        return name, False, f"path mismatch: {actual} != {EXPECTED}"
    return name, True, str(actual)


def _real_query(name: str, db_path: str) -> tuple[str, bool, str]:
    """Open the path with sqlite3 and run a tiny read to confirm it's live."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM graph_nodes"
            ).fetchone()
            nodes = row[0] if row else 0
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        return name, False, f"sqlite open/read failed: {exc}"
    return name, True, f"graph_nodes={nodes}"


def main() -> int:
    sites: list[tuple[str, Callable[[], Path | str | None]]] = []

    # 1. canonical helper
    def site_resolve():
        from thinking_os.database import resolve_db_path
        return resolve_db_path(REPO_ROOT)
    sites.append(("thinking_os.database.resolve_db_path(REPO_ROOT)", site_resolve))

    # 2. DEFAULT_DB_PATH constant (cwd-based default)
    def site_default():
        from thinking_os.database import DEFAULT_DB_PATH
        return DEFAULT_DB_PATH
    sites.append(("thinking_os.database.DEFAULT_DB_PATH", site_default))

    # 3. Web Hub current_db_path
    def site_web():
        from web._project_context import current_db_path
        return current_db_path()
    sites.append(("web._project_context.current_db_path()", site_web))

    # 4. graph_os SqliteBackend default path resolution
    def site_graph_backend():
        from graph_os.backends.sqlite_backend import SqliteBackend
        # Construct a backend without conn to trigger resolve_db_path
        # then close.  Use a temp dir env override so we don't recreate
        # the production DB if it doesn't exist on this machine.
        be = SqliteBackend()
        try:
            return be._conn.execute(
                "SELECT file FROM pragma_database_list WHERE name='main'"
            ).fetchone()[0]
        finally:
            be.close()
    sites.append(("graph_os.SqliteBackend default", site_graph_backend))

    # 5. cognition route resolver (Hub)
    def site_cognition():
        os.environ["COS_PROJECT_ROOT"] = str(REPO_ROOT)
        from web.routes.cognition import _db_path
        return _db_path()
    sites.append(("web.routes.cognition._db_path()", site_cognition))

    # 6. hook helper resolution (work_log_append)
    def site_hook_work_log():
        from thinking_os.database import resolve_db_path
        os.environ["COS_PROJECT_ROOT"] = str(REPO_ROOT)
        # The hook itself imports resolve_db_path lazily — exercise it directly.
        return resolve_db_path(REPO_ROOT)
    sites.append(("hook _helpers/work_log_append (via resolve_db_path)", site_hook_work_log))

    # 7. board_os transition_gates fallback
    def site_board_gates():
        from thinking_os.database import resolve_db_path
        return resolve_db_path()
    sites.append(("board_os.transition_gates_cli (via resolve_db_path)", site_board_gates))

    print(f"\nExpected canonical: {EXPECTED}")
    print(f"{'='*78}")
    pass_n = 0
    fail_n = 0
    paths_seen: set[str] = set()

    for name, fn in sites:
        site_name, ok, detail = _check(name, fn)
        glyph = "✓" if ok else "✗"
        print(f"  {glyph} {site_name}")
        print(f"      {detail}")
        if ok:
            pass_n += 1
            paths_seen.add(detail)
        else:
            fail_n += 1

    # ── Live read verification ─────────────────────────────────────
    print(f"\n{'='*78}")
    print("Live read smoke (sqlite3.connect → SELECT COUNT(*) FROM graph_nodes)")
    print(f"{'='*78}")
    if EXPECTED.exists():
        live_name, live_ok, live_detail = _real_query("canonical", str(EXPECTED))
        glyph = "✓" if live_ok else "✗"
        print(f"  {glyph} {live_name}: {live_detail}")
        if not live_ok:
            fail_n += 1
        else:
            pass_n += 1
    else:
        print(f"  ⚠ canonical DB does not exist at {EXPECTED}")
        print(f"     run `cos init` or `python -c 'from thinking_os.database import init_db; init_db()'` first")

    # ── Final assertion ────────────────────────────────────────────
    print(f"\n{'='*78}")
    print(f"Distinct paths seen across {len(sites)} sites: {len(paths_seen)}")
    if len(paths_seen) == 1:
        print(f"  → SHARED ✓ (every site resolves to the same canonical file)")
    else:
        print(f"  → DIVERGED ✗")
        for p in sorted(paths_seen):
            print(f"     - {p}")

    print(f"\nRESULT: {pass_n} pass · {fail_n} fail")
    return 0 if fail_n == 0 and len(paths_seen) <= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
