"""
Tests for db.py — migration, WAL mode, table creation, FTS5 detection.

TASK-141: Unit tests for the database module.
"""

from __future__ import annotations

import sqlite3

# Adjust path so we can import from parent
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import (
    get_connection,
    init_db,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Return a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def fresh_conn(tmp_db_path: Path) -> sqlite3.Connection:
    """Return a fresh connection with pragmas applied but no migrations."""
    conn = get_connection(tmp_db_path)
    yield conn
    conn.close()


@pytest.fixture
def migrated_conn(tmp_db_path: Path) -> sqlite3.Connection:
    """Return a connection with all migrations applied."""
    conn = init_db(tmp_db_path)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# WAL mode and PRAGMAs
# ---------------------------------------------------------------------------


def test_find_project_root_prefers_marker_over_stray(tmp_path: Path) -> None:
    """TASK-047: a subdir holding a STRAY .coding-os must resolve to the
    marker-co-located project root, not the stray."""
    from _db_paths import _find_project_root_from_cwd

    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / ".git").mkdir()  # root marker
    sub = root / "src" / "cli"
    (sub / ".coding-os").mkdir(parents=True)  # stray, NO marker sibling
    assert _find_project_root_from_cwd(sub).resolve() == root.resolve()


def test_find_project_root_falls_back_to_innermost_without_marker(
    tmp_path: Path,
) -> None:
    """No marker anywhere → innermost .coding-os (TASK-117 anti-lazy-create)."""
    from _db_paths import _find_project_root_from_cwd

    root = tmp_path / "bare"
    (root / ".coding-os").mkdir(parents=True)
    sub = root / "deep"
    (sub / ".coding-os").mkdir(parents=True)
    assert _find_project_root_from_cwd(sub).resolve() == sub.resolve()


def test_find_project_root_stops_below_home(tmp_path: Path, monkeypatch) -> None:
    """TASK-498: $HOME/.coding-os is the global hub, never a project root. A
    subdir under $HOME with no project .coding-os must NOT resolve to $HOME."""
    from _db_paths import _find_project_root_from_cwd

    home = tmp_path / "home"
    (home / ".coding-os").mkdir(parents=True)  # global-hub state
    (home / "pyproject.toml").write_text("", encoding="utf-8")  # home carries a marker
    sub = home / "proj" / "src"
    sub.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    got = _find_project_root_from_cwd(sub).resolve()
    assert got != home.resolve()
    assert got == sub.resolve()  # innermost-or-cwd fallback, never the hub


def test_project_root_precedence(tmp_path: Path, monkeypatch) -> None:
    """TASK-498: canonical project_root() = COS_PROJECT_ROOT > parent of an
    absolute COS_STATE_DIR > upward marker-walk."""
    from database import project_root

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    monkeypatch.setenv("COS_PROJECT_ROOT", str(explicit))
    assert project_root() == explicit.resolve()

    monkeypatch.delenv("COS_PROJECT_ROOT", raising=False)
    state = tmp_path / "viastate" / ".coding-os"
    state.mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    assert project_root() == (tmp_path / "viastate").resolve()

    monkeypatch.setenv("COS_STATE_DIR", ".coding-os")  # relative → ignored, must walk
    monkeypatch.setenv("HOME", str(tmp_path / "nohome"))
    root = tmp_path / "walkroot"
    (root / ".coding-os").mkdir(parents=True)
    (root / ".coding-os.yaml").write_text("v\n", encoding="utf-8")
    sub = root / "a" / "b"
    sub.mkdir(parents=True)
    assert project_root(sub) == root.resolve()


def test_project_root_tier2_stops_below_home(tmp_path: Path, monkeypatch) -> None:
    """TASK-506: an absolute COS_STATE_DIR == $HOME/.coding-os is the global hub,
    not a project root — tier-2 must NOT return $HOME; it falls through to the
    marker-walk (which has its own $HOME hard-stop)."""
    from database import project_root

    home = tmp_path / "home"
    (home / ".coding-os").mkdir(parents=True)  # global-hub state
    monkeypatch.delenv("COS_PROJECT_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("COS_STATE_DIR", str(home / ".coding-os"))  # absolute, == hub
    # cwd start is a subdir under $HOME with no project .coding-os → walk falls
    # back to that subdir, never $HOME.
    sub = home / "proj" / "src"
    sub.mkdir(parents=True)
    got = project_root(sub).resolve()
    assert got != home.resolve()


def test_resolve_db_path_bound_scope_beats_env(tmp_path: Path, monkeypatch) -> None:
    """TASK-769: a per-request bound project scope (set only by the Hub's
    ProjectScopeMiddleware) must win over an ambient $COS_DB_PATH — else every
    scoped /api/p/<slug>/* request leaks onto the launch project's DB. CLI/MCP
    callers never bind the ContextVar, so $COS_DB_PATH keeps its precedence."""
    from database import (
        reset_active_project_root,
        resolve_db_path,
        set_active_project_root,
    )

    launch_db = tmp_path / "launch" / ".coding-os" / "coding-os.db"
    monkeypatch.setenv("COS_DB_PATH", str(launch_db))

    # No bound scope → env wins (CLI/MCP behavior, unchanged); an explicit arg
    # still does NOT override the env for non-web callers.
    assert resolve_db_path() == launch_db
    assert resolve_db_path(tmp_path / "other") == launch_db

    # A bound per-request scope beats the env (the Hub scoping fix), whether or
    # not an arg is passed (current_db_path passes the bound root as the arg).
    scoped = tmp_path / "streamos"
    expected = scoped / ".coding-os" / "coding-os.db"
    token = set_active_project_root(scoped)
    try:
        assert resolve_db_path() == expected
        assert resolve_db_path(scoped) == expected
    finally:
        reset_active_project_root(token)

    # After reset, env precedence is restored — no leak across requests.
    assert resolve_db_path() == launch_db


def test_bare_home_refuses_project_db(tmp_path: Path, monkeypatch) -> None:
    """TASK-770/775/787: cwd == $HOME with no project below must NOT anchor a
    project DB inside the global hub state dir. _find_project_root_from_cwd returns
    None at the bare-$HOME boundary; resolve_db_path RAISES there — the ONE
    complete guard, since every DB-open path (incl. the graph backend / cognition
    route that connect directly) funnels through it — and init_db adds a second
    guard for the DEFAULT_DB_PATH / explicit-path route that skips the resolver."""
    from _db_paths import _find_project_root_from_cwd, resolve_db_path
    from database import init_db

    home = tmp_path / "home"
    (home / ".coding-os").mkdir(parents=True)  # global hub state dir
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("COS_DB_PATH", raising=False)

    # Bare $HOME → no project root → None (never $HOME itself).
    assert _find_project_root_from_cwd(home) is None

    # A real subdir under $HOME still lazy-resolves to cwd, never None.
    sub = home / "scratch" / "here"
    sub.mkdir(parents=True)
    assert _find_project_root_from_cwd(sub) == sub.resolve()

    # resolve_db_path is the ONE complete guard — every DB-open path funnels
    # through it — so it raises at bare $HOME rather than mint a phantom DB.
    monkeypatch.chdir(home)
    with pytest.raises(RuntimeError, match="global hub state dir"):
        resolve_db_path()
    # init_db adds a second guard for the DEFAULT_DB_PATH / explicit-path route.
    with pytest.raises(RuntimeError, match="global hub"):
        init_db(str(home / ".coding-os" / "coding-os.db"))
