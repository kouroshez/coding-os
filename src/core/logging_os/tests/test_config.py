from __future__ import annotations

from pathlib import Path

import pytest

from core.logging_os import config


def test_state_dir_honors_explicit_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    explicit = tmp_path / "explicit-state"
    monkeypatch.setenv("COS_STATE_DIR", str(explicit))
    assert config.state_dir() == Path(str(explicit))


def test_state_dir_anchors_to_project_root_from_subdir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # a process started in a nested subdir must still resolve.coding-os
    # to the PROJECT ROOT (marked by .git), not its CWD — otherwise the log feed
    # fragments across sibling .coding-os/ dirs.
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    subdir = root / "src" / "core" / "thinking_os"
    subdir.mkdir(parents=True)
    monkeypatch.delenv("COS_STATE_DIR", raising=False)
    monkeypatch.chdir(subdir)
    # Pre-fix this returned subdir/.coding-os (CWD-relative).
    assert config.state_dir() == (root.resolve() / config.STATE_DIR_NAME)


def test_state_dir_anchors_via_pyproject_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    monkeypatch.delenv("COS_STATE_DIR", raising=False)
    monkeypatch.chdir(nested)
    assert config.state_dir() == (root.resolve() / config.STATE_DIR_NAME)


def test_state_dir_falls_back_to_cwd_when_no_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    # No project marker up the tree → legacy CWD-relative behaviour preserved.
    monkeypatch.delenv("COS_STATE_DIR", raising=False)
    monkeypatch.setattr(config, "_discover_project_root", lambda: None)
    assert config.state_dir() == Path(config.STATE_DIR_NAME)
