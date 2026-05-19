"""Tests for the get_backend factory and BackendUnavailable handling.

Ship gate: factory honors the fail-loud contract (rejects unknown
backends, coerces the retired ``kuzu`` choice, accepts env override,
and emits a DeprecationWarning on the retired ``kuzu_path`` kwarg).

Kuzu backend was retired 2026-05-18 — there's no kuzu_backend.py to
import any more.
"""

from __future__ import annotations

import warnings

import pytest

from graph_os.backend import get_backend


def test_factory_rejects_unknown_choice():
    with pytest.raises(ValueError):
        get_backend(backend="postgres")


def test_factory_sqlite_always_available(migrated_conn):
    backend = get_backend(backend="sqlite", sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_auto_uses_sqlite(migrated_conn):
    """`auto` is the default and now always resolves to SQLite."""
    backend = get_backend(backend="auto", sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_legacy_kuzu_choice_coerced(migrated_conn):
    """Pinned configs that still pass backend='kuzu' get SQLite silently."""
    backend = get_backend(backend="kuzu", sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_env_variable_picks_backend(migrated_conn, monkeypatch):
    monkeypatch.setenv("COS_GRAPH_BACKEND", "sqlite")
    backend = get_backend(sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_kuzu_path_kwarg_warns_and_ignored(migrated_conn):
    """Old callers passing kuzu_path= get a DeprecationWarning, not a crash."""
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        backend = get_backend(sqlite_conn=migrated_conn, kuzu_path="/ignored")
    try:
        assert backend.backend_id == "sqlite"
        assert any(
            issubclass(w.category, DeprecationWarning) and "kuzu_path" in str(w.message)
            for w in captured
        )
    finally:
        backend.close()
