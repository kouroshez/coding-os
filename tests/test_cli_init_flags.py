"""Tests for new `cos init` flags (--name, --debug, --git, --force, --format).

Covers flag resolution, validation, and target path computation from
`cli._init_helpers.resolve_init_target`. Integration with the full scaffold
pipeline is covered by tests/test_cli.py and scripts/operational_eval.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._init_helpers import (
    CODING_OS_ROOT,
    DEBUG_DIR,
    DEFAULT_DEBUG_NAME,
    InitError,
    InitExit,
    _is_nested_in_git,
    _safe_remove_tree,
    maybe_git_init,
    resolve_init_target,
    validate_name,
)


# ---------- validate_name ----------

@pytest.mark.parametrize(
    "name",
    ["ok", "ok-name", "ok_name", "ok.name", "a", "a1", "foo-bar.baz_1"],
)
def test_validate_name_accepts_valid(name: str) -> None:
    validate_name(name)  # no raise


@pytest.mark.parametrize(
    "name",
    ["", "-bad", ".bad", "_bad", "Bad", "bad/name", "bad name", "bad!", "A"],
)
def test_validate_name_rejects_invalid(name: str) -> None:
    with pytest.raises(InitError) as exc_info:
        validate_name(name)
    assert exc_info.value.exit_code == InitExit.BAD_NAME


# ---------- resolve_init_target: --debug ----------

def test_debug_requires_cwd_inside_repo(tmp_path: Path) -> None:
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name=None, project_dir=None, debug=True, force=False, cwd=tmp_path,
        )
    assert exc_info.value.exit_code == InitExit.FLAG_CONFLICT
    assert "coding-os source repo" in str(exc_info.value)


def test_debug_with_project_dir_is_flag_conflict(tmp_path: Path) -> None:
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name=None,
            project_dir=str(tmp_path),
            debug=True,
            force=False,
            cwd=CODING_OS_ROOT,
        )
    assert exc_info.value.exit_code == InitExit.FLAG_CONFLICT


def test_debug_default_name_is_the_script_output() -> None:
    target = resolve_init_target(
        name=None, project_dir=None, debug=True, force=True, cwd=CODING_OS_ROOT,
    )
    try:
        assert target.path == DEBUG_DIR / DEFAULT_DEBUG_NAME
        assert target.debug is True
    finally:
        _safe_remove_tree(target.path)


def test_debug_custom_name() -> None:
    target = resolve_init_target(
        name="debug-test-xyz",
        project_dir=None,
        debug=True,
        force=True,
        cwd=CODING_OS_ROOT,
    )
    try:
        assert target.path == DEBUG_DIR / "debug-test-xyz"
    finally:
        _safe_remove_tree(target.path)


# ---------- resolve_init_target: --name only ----------

def test_name_creates_nested_dir_under_cwd(tmp_path: Path) -> None:
    target = resolve_init_target(
        name="my-proj",
        project_dir=None,
        debug=False,
        force=False,
        cwd=tmp_path,
    )
    assert target.path == tmp_path / "my-proj"
    assert target.path.is_dir()


def test_name_with_project_dir_parent(tmp_path: Path) -> None:
    parent = tmp_path / "nested"
    parent.mkdir()
    target = resolve_init_target(
        name="child",
        project_dir=str(parent),
        debug=False,
        force=False,
        cwd=tmp_path,
    )
    assert target.path == parent / "child"


def test_name_invalid_regex_rejected(tmp_path: Path) -> None:
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name="Bad Name!",
            project_dir=str(tmp_path),
            debug=False,
            force=False,
            cwd=tmp_path,
        )
    assert exc_info.value.exit_code == InitExit.BAD_NAME


# ---------- resolve_init_target: target state ----------

def test_non_empty_target_without_force_errors(tmp_path: Path) -> None:
    existing = tmp_path / "exists"
    existing.mkdir()
    (existing / "file.txt").write_text("x")
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name=None,
            project_dir=str(existing),
            debug=False,
            force=False,
            cwd=tmp_path,
        )
    assert exc_info.value.exit_code == InitExit.TARGET_STATE
    assert "not empty" in str(exc_info.value)


def test_non_empty_target_with_force_wipes(tmp_path: Path) -> None:
    existing = tmp_path / "exists"
    existing.mkdir()
    (existing / "old.txt").write_text("stale")
    target = resolve_init_target(
        name=None,
        project_dir=str(existing),
        debug=False,
        force=True,
        cwd=tmp_path,
    )
    assert target.forced_empty is True
    assert not (existing / "old.txt").exists()
    assert existing.is_dir()


def test_empty_target_is_used_as_is(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    target = resolve_init_target(
        name=None,
        project_dir=str(empty),
        debug=False,
        force=False,
        cwd=tmp_path,
    )
    assert target.forced_empty is False
    assert target.path == empty.resolve()


def test_file_target_is_rejected(tmp_path: Path) -> None:
    file_target = tmp_path / "afile"
    file_target.write_text("content")
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name=None,
            project_dir=str(file_target),
            debug=False,
            force=True,
            cwd=tmp_path,
        )
    assert exc_info.value.exit_code == InitExit.TARGET_STATE
    assert "not a directory" in str(exc_info.value)


def test_symlink_target_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(InitError) as exc_info:
        resolve_init_target(
            name=None,
            project_dir=str(link),
            debug=False,
            force=True,
            cwd=tmp_path,
        )
    assert exc_info.value.exit_code == InitExit.TARGET_STATE
    assert "symlink" in str(exc_info.value)
    # Confirm the real directory was NOT touched
    assert real.exists()


# ---------- _is_nested_in_git ----------

def test_is_nested_in_git_detects_ancestor(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    child = tmp_path / "sub"
    child.mkdir()
    assert _is_nested_in_git(child) is True


def test_is_nested_in_git_false_for_standalone(tmp_path: Path) -> None:
    child = tmp_path / "sub"
    child.mkdir()
    assert _is_nested_in_git(child) is False


# ---------- maybe_git_init ----------

def test_git_init_runs_when_not_nested(tmp_path: Path) -> None:
    from cli._init_helpers import InitTarget

    target = InitTarget(path=tmp_path, debug=False, forced_empty=False, nested_in_git=False)
    result = maybe_git_init(target, enabled=True)
    assert result.ran is True
    assert (tmp_path / ".git").exists()


def test_git_init_skipped_when_nested() -> None:
    from cli._init_helpers import InitTarget

    # Use coding-os repo itself — it's inside a git repo.
    target = InitTarget(
        path=CODING_OS_ROOT, debug=False, forced_empty=False, nested_in_git=True,
    )
    result = maybe_git_init(target, enabled=True)
    assert result.ran is False
    assert result.skipped_reason == "nested in existing git repo"


def test_no_git_flag_skips_init(tmp_path: Path) -> None:
    from cli._init_helpers import InitTarget

    target = InitTarget(path=tmp_path, debug=False, forced_empty=False, nested_in_git=False)
    result = maybe_git_init(target, enabled=False)
    assert result.ran is False
    assert result.skipped_reason == "--no-git flag"
    assert not (tmp_path / ".git").exists()
