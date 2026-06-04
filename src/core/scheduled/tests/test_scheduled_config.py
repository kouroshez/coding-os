"""Tests for scheduled config + responsive learn_extract trigger (G5)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_CORE = Path(__file__).resolve().parents[2]
_THINKING_OS = _CORE / "thinking_os"
for _p in (str(_CORE), str(_THINKING_OS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scheduled import config as cfg_mod  # noqa: E402
from scheduled import responsive_extract  # noqa: E402
from scheduled._state import state_dir  # noqa: E402


class TestConfig:
    def test_missing_returns_defaults(self, tmp_path: Path) -> None:
        assert cfg_mod.load_config(tmp_path) == cfg_mod.DEFAULTS

    def test_save_clamps_and_persists(self, tmp_path: Path) -> None:
        saved = cfg_mod.save_config(tmp_path, {"hour": 99, "responsive_extract_threshold": 0})
        assert saved["hour"] == 23  # clamped to upper bound
        assert saved["responsive_extract_threshold"] == 1  # clamped to lower bound
        assert cfg_mod.load_config(tmp_path)["hour"] == 23  # round-trips

    def test_save_clamps_lower_hour(self, tmp_path: Path) -> None:
        assert cfg_mod.save_config(tmp_path, {"hour": -5})["hour"] == 0

    def test_enabled_coerced_to_bool(self, tmp_path: Path) -> None:
        assert cfg_mod.save_config(tmp_path, {"enabled": 0})["enabled"] is False

    def test_unknown_keys_ignored(self, tmp_path: Path) -> None:
        saved = cfg_mod.save_config(tmp_path, {"bogus": 1})
        assert "bogus" not in saved


def _make_project(tmp_path: Path, n_outcomes: int) -> Path:
    import database

    db_path = tmp_path / ".coding-os" / "coding-os.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = database.init_db(str(db_path))
    for i in range(n_outcomes):
        conn.execute(
            "INSERT INTO task_outcomes (task_id, type, domain, complexity, outcome) "
            "VALUES (?, 'task', 'INFRA', 'CLEAR', 'success')",
            (f"T{i}",),
        )
    conn.commit()
    conn.close()
    return db_path


def _run(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["responsive_extract.py", "sid", "TASK-1", str(db_path)])
    return responsive_extract.main()


class TestResponsiveExtract:
    def test_noop_when_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db_path = _make_project(tmp_path, 10)
        cfg_mod.save_config(tmp_path, {"enabled": False, "responsive_extract_threshold": 1})
        assert _run(db_path, monkeypatch) == 0
        assert not (state_dir(tmp_path) / ".last-extract").exists()

    def test_noop_below_threshold(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db_path = _make_project(tmp_path, 1)
        cfg_mod.save_config(tmp_path, {"responsive_extract_threshold": 5})
        assert _run(db_path, monkeypatch) == 0
        assert not (state_dir(tmp_path) / ".last-extract").exists()

    def test_fires_at_threshold(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        db_path = _make_project(tmp_path, 5)
        cfg_mod.save_config(
            tmp_path, {"responsive_extract_threshold": 2, "learn_extract_min_outcomes": 3}
        )
        assert _run(db_path, monkeypatch) == 0
        assert (state_dir(tmp_path) / ".last-extract").exists()  # marker touched → extracted

    def test_noop_when_db_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            sys, "argv", ["responsive_extract.py", "s", "t", str(tmp_path / "nope.db")]
        )
        assert responsive_extract.main() == 0
