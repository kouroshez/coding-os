"""Migration test for the 2026-04-30 `thinking_os.db` → `coding-os.db` rename."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from db import (
    DB_FILENAME,
    DEFAULT_DB_PATH,
    LEGACY_DB_FILENAME,
    init_db,
    migrate_legacy_db_filename,
)


def test_constants() -> None:
    assert DB_FILENAME == "coding-os.db"
    assert LEGACY_DB_FILENAME == "thinking_os.db"
    assert DEFAULT_DB_PATH.name == "coding-os.db"


def test_no_rename_when_canonical_already_exists(tmp_path: Path) -> None:
    target = tmp_path / "coding-os.db"
    legacy = tmp_path / "thinking_os.db"
    target.write_bytes(b"")
    legacy.write_bytes(b"")
    assert migrate_legacy_db_filename(target) is False
    assert legacy.exists(), "legacy must be left alone when canonical exists"


def test_no_rename_when_no_legacy(tmp_path: Path) -> None:
    target = tmp_path / "coding-os.db"
    assert migrate_legacy_db_filename(target) is False
    assert not target.exists()


def test_renames_legacy_db_and_sidecars(tmp_path: Path) -> None:
    legacy = tmp_path / "thinking_os.db"
    legacy_shm = tmp_path / "thinking_os.db-shm"
    legacy_wal = tmp_path / "thinking_os.db-wal"
    legacy.write_bytes(b"FAKE-DATA")
    legacy_shm.write_bytes(b"shm")
    legacy_wal.write_bytes(b"wal")

    target = tmp_path / "coding-os.db"
    assert migrate_legacy_db_filename(target) is True

    assert target.exists()
    assert target.read_bytes() == b"FAKE-DATA", "data must survive the rename"
    assert (tmp_path / "coding-os.db-shm").exists()
    assert (tmp_path / "coding-os.db-wal").exists()
    assert not legacy.exists()
    assert not legacy_shm.exists()
    assert not legacy_wal.exists()


def test_init_db_uses_canonical_filename(tmp_path: Path) -> None:
    target = tmp_path / "coding-os.db"
    conn = init_db(str(target))
    try:
        assert target.exists()
        v = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert v >= 22
    finally:
        conn.close()


def test_init_db_auto_migrates_legacy_at_open_time(tmp_path: Path) -> None:
    """End-to-end: a project with the old filename gets renamed by init_db."""
    legacy = tmp_path / "thinking_os.db"
    # Build a legacy DB with one observation row so we can prove data survives.
    seed = sqlite3.connect(str(legacy))
    seed.execute("CREATE TABLE legacy_marker (msg TEXT)")
    seed.execute("INSERT INTO legacy_marker (msg) VALUES ('before-rename')")
    seed.commit()
    seed.close()

    target = tmp_path / "coding-os.db"
    conn = init_db(str(target))
    try:
        assert target.exists(), "init_db must produce coding-os.db"
        assert not legacy.exists(), "legacy file must be renamed away"
        # The legacy table is still there (migrations are additive).
        row = conn.execute("SELECT msg FROM legacy_marker").fetchone()
        assert row is not None and row[0] == "before-rename"
    finally:
        conn.close()
