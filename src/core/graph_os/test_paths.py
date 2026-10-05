"""graph_os — which repo paths hold tests: one rule for every tool that sets test code aside.

Seven tools kept their own copy of this check, all written for Python layouts,
so `_test.go`, `.test.ts`, `.spec.tsx` and `__tests__/` counted as production:
a symbol called only by its Jest test was "tested" yet never "dead", and test
fixtures were listed as API routes.
"""

from __future__ import annotations

import re
import sqlite3

SQL_FUNCTION = "cos_is_test_path"

_TEST_DIRS = frozenset(
    {"tests", "test", "__tests__", "__mocks__", "mocks", "testdata", "spec", "e2e"}
)
_TEST_FILE_RE = re.compile(
    r"^test_[^/]*\.py$|^conftest\.py$|_test\.(?:py|go)$|\.(?:test|spec)\.[cm]?[jt]sx?$"
)


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    return any(part in _TEST_DIRS for part in parts[:-1]) or bool(_TEST_FILE_RE.search(parts[-1]))


def register_sql_function(conn: sqlite3.Connection) -> None:
    conn.create_function(
        SQL_FUNCTION, 1, lambda path: int(is_test_path(path or "")), deterministic=True
    )
