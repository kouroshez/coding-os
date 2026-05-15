"""Tests for the get_backend factory and BackendUnavailable handling.

Ship gate: factory must honour the fail-loud contract (Section 12.5
of the plan). Explicit kuzu request when kuzu is missing => raise;
auto request falls back silently but sets backend_id correctly.
"""

from __future__ import annotations

import importlib

import pytest

from graph_os.backend import BackendUnavailable, get_backend


def _kuzu_available() -> bool:
    try:
        importlib.import_module("kuzu")
        return True
    except ImportError:
        return False


def test_factory_rejects_unknown_choice():
    with pytest.raises(ValueError):
        get_backend(backend="postgres")


def test_factory_sqlite_always_available(migrated_conn):
    backend = get_backend(backend="sqlite", sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_auto_falls_back_to_sqlite_when_kuzu_absent(
    migrated_conn, monkeypatch
):
    if _kuzu_available():
        pytest.skip("kuzu installed — auto would prefer it")
    backend = get_backend(backend="auto", sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()


def test_factory_kuzu_explicit_raises_when_missing():
    if _kuzu_available():
        pytest.skip("kuzu installed — explicit request succeeds")
    with pytest.raises(BackendUnavailable):
        get_backend(backend="kuzu")


def test_factory_env_variable_picks_backend(migrated_conn, monkeypatch):
    monkeypatch.setenv("COS_GRAPH_BACKEND", "sqlite")
    backend = get_backend(sqlite_conn=migrated_conn)
    try:
        assert backend.backend_id == "sqlite"
    finally:
        backend.close()
