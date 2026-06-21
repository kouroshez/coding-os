"""Unit tests for materialize_makefile_targets (TASK-392) — fast, no full init."""

from __future__ import annotations

from pathlib import Path

from cli._data_types import AggregatedWorld, MakefileTarget
from cli._init_helpers import materialize_makefile_targets


def _world(*targets: MakefileTarget) -> AggregatedWorld:
    return AggregatedWorld(
        project_name="p",
        agent_id="claude",
        stack_ids=(),
        substitutions={},
        skills=(),
        verify_rows=(),
        routing_entries=(),
        ref_codes=(),
        makefile_targets=tuple(targets),
        rules=(),
        dimensions=(),
        skill_enforcement=(),
        agents_md_sections=(),
        hooks=(),
    )


def _setup(tmp_path: Path) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "Makefile.base").write_text("# base\n", encoding="utf-8")
    (tmp_path / "Makefile").write_text(
        "# Project Makefile\ninclude .coding-os/Makefile.base\n\n# user targets:\n",
        encoding="utf-8",
    )
    return state


def test_writes_stacks_include_and_target(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    world = _world(MakefileTarget("lint-backend", "cd src/backend && ruff check .", "lint"))
    assert materialize_makefile_targets(tmp_path, state, world) is True
    stacks = (state / "Makefile.stacks").read_text(encoding="utf-8")
    assert "lint-backend:" in stacks
    assert "cd src/backend && ruff check ." in stacks
    assert "-include .coding-os/Makefile.stacks" in (tmp_path / "Makefile").read_text(
        encoding="utf-8"
    )


def test_include_is_idempotent(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    world = _world(MakefileTarget("lint-backend", "cmd"))
    materialize_makefile_targets(tmp_path, state, world)
    before = (tmp_path / "Makefile").read_text(encoding="utf-8")
    materialize_makefile_targets(tmp_path, state, world)  # second run
    after = (tmp_path / "Makefile").read_text(encoding="utf-8")
    assert before == after
    assert after.count("Makefile.stacks") == 1


def test_user_targets_untouched(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        makefile.read_text(encoding="utf-8") + "\nmy-target:\n\techo hi\n", encoding="utf-8"
    )
    materialize_makefile_targets(tmp_path, state, _world(MakefileTarget("lint-backend", "cmd")))
    text = makefile.read_text(encoding="utf-8")
    assert "my-target:" in text
    assert "\techo hi" in text


def test_include_wired_directly_after_base_marker(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    materialize_makefile_targets(tmp_path, state, _world(MakefileTarget("t", "c")))
    lines = (tmp_path / "Makefile").read_text(encoding="utf-8").splitlines()
    base_i = next(i for i, line in enumerate(lines) if "Makefile.base" in line)
    stacks_i = next(i for i, line in enumerate(lines) if "Makefile.stacks" in line)
    assert stacks_i == base_i + 1


def test_empty_world_writes_placeholder(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    materialize_makefile_targets(tmp_path, state, _world())
    assert "No stack-contributed" in (state / "Makefile.stacks").read_text(encoding="utf-8")


def test_no_project_makefile_still_writes_stacks(tmp_path: Path) -> None:
    # fresh init writes the project Makefile separately; the helper must still
    # produce the include file when no Makefile exists yet.
    state = tmp_path / ".coding-os"
    state.mkdir()
    assert materialize_makefile_targets(tmp_path, state, _world(MakefileTarget("t", "c"))) is True
    assert (state / "Makefile.stacks").exists()


def test_second_run_no_changes_returns_false(tmp_path: Path) -> None:
    state = _setup(tmp_path)
    world = _world(MakefileTarget("lint-backend", "cmd"))
    materialize_makefile_targets(tmp_path, state, world)
    # nothing changed on the second identical run → no churn reported
    assert materialize_makefile_targets(tmp_path, state, world) is False
