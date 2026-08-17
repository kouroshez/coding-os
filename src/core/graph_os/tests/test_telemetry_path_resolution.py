"""Graph telemetry resolves the project root; it never mints one.

`_telemetry_path` used to fall back to `Path.cwd() / ".coding-os"` and mkdir it.
A minted state dir is itself a root marker, so it captured every later
resolution in that subtree — `src/core/web/ui/` ran on a phantom `coding-os.db`
(with its own `-wal`) for two months while the real DB sat at the repo root.
These tests pin the walk, and pin that an unresolvable root degrades to no
telemetry rather than to a new directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "src/core"))

from graph_os.tools import _graph_envelope


@pytest.fixture(autouse=True)
def _clear_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_graph_envelope, "_TELEMETRY_PATH_CACHE", [])
    monkeypatch.delenv("COS_STATE_DIR", raising=False)
    yield


def _make_project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / ".coding-os").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return root


def test_env_var_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    explicit = tmp_path / "explicit-state"
    monkeypatch.setenv("COS_STATE_DIR", str(explicit))

    resolved = _graph_envelope._telemetry_path()

    assert resolved is not None
    assert resolved.startswith(str(explicit))


def test_subdirectory_resolves_to_the_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path)
    nested = root / "src" / "core" / "web" / "ui"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    resolved = _graph_envelope._telemetry_path()

    assert resolved == str(root / ".coding-os" / ".graph-telemetry.jsonl")


def test_subdirectory_mints_no_phantom_state_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _make_project(tmp_path)
    nested = root / "src" / "core" / "web" / "ui"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    _graph_envelope._telemetry_path()

    assert not (nested / ".coding-os").exists(), (
        "a minted state dir becomes a root marker and captures the whole subtree"
    )


def test_outside_any_project_degrades_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The walk is patched, not the caller: this pins OUR degrade branch. Using a
    # real root-less cwd is not hermetic — the machine running these tests had a
    # stray /private/tmp/.coding-os, which is the very bug under test.
    import thinking_os._db_paths as db_paths

    orphan = tmp_path / "no-project" / "deep"
    orphan.mkdir(parents=True)
    monkeypatch.chdir(orphan)
    monkeypatch.setattr(db_paths, "_find_project_root_from_cwd", lambda: None)

    assert _graph_envelope._project_state_dir() is None
    assert _graph_envelope._telemetry_path() is None
    assert not (orphan / ".coding-os").exists()


def test_writing_telemetry_from_a_subdir_lands_in_the_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # End-to-end: the guard that matters is where the bytes actually go.
    root = _make_project(tmp_path)
    nested = root / "src" / "core" / "web" / "ui"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    path = _graph_envelope._telemetry_path()
    assert path is not None
    Path(path).write_text('{"ok": true}\n', encoding="utf-8")

    assert (root / ".coding-os" / ".graph-telemetry.jsonl").exists()
    assert not (nested / ".coding-os").exists()
