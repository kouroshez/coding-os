"""Stack commands: materialize into .coding-os.yaml, retire legacy make files, `cos run`."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from cli._data_types import AggregatedWorld, StackCommand
from cli._init_helpers import materialize_commands
from cli.main import cli


def _world(*commands: StackCommand) -> AggregatedWorld:
    return AggregatedWorld(
        project_name="p",
        agent_id="claude",
        stack_ids=(),
        substitutions={},
        skills=(),
        verify_rows=(),
        routing_entries=(),
        ref_codes=(),
        commands=tuple(commands),
        rules=(),
        dimensions=(),
        skill_enforcement=(),
        agents_md_sections=(),
        hooks=(),
    )


def _project(tmp_path: Path, verify: dict | None = None) -> Path:
    (tmp_path / ".coding-os").mkdir()
    (tmp_path / ".coding-os.yaml").write_text(yaml.dump({"version": 1, "verify": verify or {}}))
    return tmp_path / ".coding-os"


def _config(tmp_path: Path) -> dict:
    return yaml.safe_load((tmp_path / ".coding-os.yaml").read_text())


def _legacy(tmp_path: Path, state: Path, user_lines: str = "") -> None:
    (state / "Makefile.base").write_text("# base\n")
    (state / "Makefile.stacks").write_text("# stacks\n")
    (tmp_path / "Makefile").write_text(
        "# Project Makefile\n# coding-os universal targets\ninclude .coding-os/Makefile.base\n"
        "-include .coding-os/Makefile.stacks\n\n# Add your project-specific targets below:\n\n"
        + user_lines
    )


def test_commands_land_in_config_and_a_second_run_changes_nothing(tmp_path: Path) -> None:
    state = _project(tmp_path)
    world = _world(StackCommand("lint-backend", "cd src/backend && ruff check ."))
    assert materialize_commands(tmp_path, state, world) is True
    assert _config(tmp_path)["commands"] == {"lint-backend": "cd src/backend && ruff check ."}
    assert materialize_commands(tmp_path, state, world) is False


def test_no_stack_commands_leaves_no_key_and_writes_no_makefile(tmp_path: Path) -> None:
    state = _project(tmp_path)
    assert materialize_commands(tmp_path, state, _world()) is False
    assert "commands" not in _config(tmp_path)
    assert not (tmp_path / "Makefile").exists()


def test_legacy_files_go_and_user_targets_stay(tmp_path: Path) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state, "deploy:\n\t./deploy.sh\n")
    materialize_commands(tmp_path, state, _world(StackCommand("lint-backend", "ruff check .")))
    assert not (state / "Makefile.base").exists()
    assert not (state / "Makefile.stacks").exists()
    assert (tmp_path / "Makefile").read_text() == "deploy:\n\t./deploy.sh\n"


def test_a_makefile_with_only_cos_lines_is_deleted(tmp_path: Path) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    materialize_commands(tmp_path, state, _world())
    assert not (tmp_path / "Makefile").exists()


def test_migration_rewrites_only_the_make_commands_cos_wrote(tmp_path: Path) -> None:
    state = _project(tmp_path, verify={"docs": "make docs-lint", "backend": "make lint-backend"})
    _legacy(tmp_path, state, "deploy:\n\t./deploy.sh\n")
    (tmp_path / "AGENTS.md").write_text(
        "1. `make session-init` (ONCE per session).\n"
        "| `src/backend/` | lint | `make lint-backend` |\n"
        "| `.claude/hooks/` | verify-hooks | `make verify-hooks` |\n"
        "Ours: `make deploy`.\n"
    )
    materialize_commands(tmp_path, state, _world(StackCommand("lint-backend", "ruff check .")))
    assert (tmp_path / "AGENTS.md").read_text() == (
        "1. `cos daily` (ONCE per session).\n| `src/backend/` | lint | `cos run lint-backend` |\nOurs: `make deploy`.\n"
    )
    assert _config(tmp_path)["verify"] == {
        "docs": "cos doc-lint",
        "backend": "cos run lint-backend",
    }


def test_without_legacy_files_agents_md_is_never_touched(tmp_path: Path) -> None:
    state = _project(tmp_path)
    (tmp_path / "AGENTS.md").write_text("`make docs-lint`\n")
    materialize_commands(tmp_path, state, _world())
    assert (tmp_path / "AGENTS.md").read_text() == "`make docs-lint`\n"


def _runnable_project(tmp_path: Path, monkeypatch) -> Path:
    (tmp_path / ".coding-os.yaml").write_text(
        yaml.dump({"commands": {"ok": "echo ran > marker.txt", "fails": "exit 3"}})
    )
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path / "src")
    return tmp_path


def test_cos_run_lists_commands(tmp_path: Path, monkeypatch) -> None:
    _runnable_project(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["run"])
    assert result.exit_code == 0
    assert "ok" in result.output and "exit 3" in result.output


def test_cos_run_runs_from_the_project_root_and_keeps_the_exit_code(
    tmp_path: Path, monkeypatch
) -> None:
    project = _runnable_project(tmp_path, monkeypatch)
    assert CliRunner().invoke(cli, ["run", "ok"]).exit_code == 0
    assert (project / "marker.txt").read_text().strip() == "ran"
    assert CliRunner().invoke(cli, ["run", "fails"]).exit_code == 3


def test_cos_run_unknown_name_names_the_known_ones(tmp_path: Path, monkeypatch) -> None:
    _runnable_project(tmp_path, monkeypatch)
    result = CliRunner().invoke(cli, ["run", "nope"])
    assert result.exit_code != 0
    assert "fails" in result.output and "ok" in result.output


def test_project_checks_run_from_a_subfolder(tmp_path: Path, monkeypatch) -> None:
    project = _runnable_project(tmp_path, monkeypatch)
    (project / ".coding-os").mkdir()
    runner = CliRunner()
    logged = runner.invoke(
        cli, ["log-write", "--type", "fix", "--msg", "probe", "--what", "w", "--files", "f.py"]
    )
    assert logged.exit_code == 0
    assert "probe" in next(project.rglob("changes.log")).read_text()
    assert runner.invoke(cli, ["memory-lint"]).exit_code == 0
    assert runner.invoke(cli, ["check-file-size"]).exit_code == 0


def test_a_symlinked_makefile_is_left_alone(tmp_path: Path) -> None:
    state = _project(tmp_path)
    shared = tmp_path / "shared.mk"
    shared.write_text("include .coding-os/Makefile.base\n")
    (tmp_path / "Makefile").symlink_to(shared)
    (state / "Makefile.base").write_text("# base\n")
    materialize_commands(tmp_path, state, _world())
    assert shared.read_text() == "include .coding-os/Makefile.base\n"
    assert (state / "Makefile.base").is_file()


def test_an_include_cos_did_not_write_keeps_the_file_and_warns(tmp_path: Path, capsys) -> None:
    state = _project(tmp_path)
    (state / "Makefile.base").write_text("# base\n")
    (tmp_path / "Makefile").write_text(
        "include $(CURDIR)/.coding-os/Makefile.base\nship:\n\t@true\n"
    )
    materialize_commands(tmp_path, state, _world())
    assert (state / "Makefile.base").is_file()
    assert "still includes Makefile.base" in capsys.readouterr().err


def test_migration_matches_whole_command_names_only(tmp_path: Path) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    (tmp_path / "AGENTS.md").write_text("`make test-backend` and `make test-backend-integration`\n")
    materialize_commands(tmp_path, state, _world(StackCommand("test-backend", "pytest")))
    assert (tmp_path / "AGENTS.md").read_text() == (
        "`cos run test-backend` and `make test-backend-integration`\n"
    )


def test_config_comments_survive_a_commands_refresh(tmp_path: Path) -> None:
    state = _project(tmp_path)
    config = tmp_path / ".coding-os.yaml"
    config.write_text("# keep me\n" + config.read_text() + "# and me\n")
    materialize_commands(tmp_path, state, _world(StackCommand("lint", "ruff check .")))
    materialize_commands(tmp_path, state, _world(StackCommand("lint", "ruff check src")))
    text = config.read_text()
    assert "# keep me" in text and "# and me" in text
    assert _config(tmp_path)["commands"] == {"lint": "ruff check src"}


def test_migration_maps_old_task_and_log_commands_and_warns_on_the_rest(
    tmp_path: Path, capsys
) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    (tmp_path / "AGENTS.md").write_text(
        "Start: `make task-start TASK=<num>`.\n"
        'Log: `log-latest [N]`, `log-write TYPE=t MSG="m" WHAT="w" FILES="f"`, `log-search QUERY="q"`.\n'
        "Health: `cos-health`, `verify-hooks`.\n"
        "Legacy: `task-context`.\n"
    )
    materialize_commands(tmp_path, state, _world())
    assert (tmp_path / "AGENTS.md").read_text() == (
        "Start: `cos task-start TASK-<num>`.\n"
        'Log: `cos log-latest [N]`, `cos log-write --type t --msg "m" --what "w" --files "f"`, `cos log-search "q"`.\n'
        "Health: `cos health`, `cos doctor`.\n"
        "Legacy: `task-context`.\n"
    )
    assert "task-context" in capsys.readouterr().err


def test_orphan_warning_ignores_comments_and_echo_text(tmp_path: Path, capsys) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state, "# deploy the board\nship:\n\t@echo daily build\n")
    materialize_commands(tmp_path, state, _world())
    assert "no longer provides" not in capsys.readouterr().err
    _legacy(tmp_path, state, "ci: docs-lint\n\t@true\n")
    materialize_commands(tmp_path, state, _world())
    assert "docs-lint" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("legacy", "current"),
    [
        ("make task-next", "cos task-pick"),
        ("make task-context TASK=7", "cos task-show TASK-7"),
        ("make task-list", "cos board"),
        ("make task-resync", "cos task-sync --force"),
        ("make board-web", "cos board --web"),
        ('make task-block TASK=7 REASON="why"', 'cos task-block TASK-7 --reason "why"'),
        ("make daily", "cos daily"),
    ],
)
def test_migration_maps_each_old_task_target_to_its_cos_command(
    tmp_path: Path, legacy: str, current: str
) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    (tmp_path / "AGENTS.md").write_text(f"Run `{legacy}`.\n")
    materialize_commands(tmp_path, state, _world())
    assert (tmp_path / "AGENTS.md").read_text() == f"Run `{current}`.\n"


def test_a_task_target_cos_cannot_express_stays_make_and_warns(tmp_path: Path, capsys) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    (tmp_path / "AGENTS.md").write_text(
        "Run `make task-list STATUS=open`. Make sure `make deploy` ships.\n"
    )
    materialize_commands(tmp_path, state, _world())
    assert (tmp_path / "AGENTS.md").read_text() == (
        "Run `make task-list STATUS=open`. Make sure `make deploy` ships.\n"
    )
    warning = capsys.readouterr().err
    assert "make task-list STATUS=open" in warning
    assert "deploy" not in warning and "make sure" not in warning.lower()


def test_log_latest_rejects_a_count_that_is_not_a_number(tmp_path: Path, monkeypatch) -> None:
    _project(tmp_path)
    (tmp_path / "changes.log").write_text("## 2026-01-01\n- entry\n")
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["log-latest", "__import__('os').system('touch pwned')"])
    assert result.exit_code == 2
    assert not (tmp_path / "pwned").exists()


_LEGACY_CI = """# Auto-generated by coding-os `cos init` — consumer-owned (edit freely; not a symlink).
# Body delegates to the generated make targets so it never rots with tool
# versions; adding a stack re-renders this with the new targets.
jobs:
  verify:
    strategy:
      matrix:
        include:
          - language: typescript
            targets: "lint-frontend test-frontend"
    steps:
      - name: verify
        run: make ${{ matrix.targets }}
"""


def _legacy_ci(tmp_path: Path) -> Path:
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    ci.parent.mkdir(parents=True)
    ci.write_text(_LEGACY_CI)
    return ci


def test_a_legacy_ci_workflow_runs_the_stack_commands_instead_of_make(tmp_path: Path) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    ci = _legacy_ci(tmp_path)
    world = _world(
        StackCommand("lint-frontend", "npm run lint"), StackCommand("test-frontend", "npm test")
    )
    materialize_commands(tmp_path, state, world)
    text = ci.read_text()
    assert "make" not in text
    assert "run: '(npm run lint) && (npm test)'" in text
    assert 'run: bash -c "$STACK_COMMANDS"' in text
    assert not (state / "Makefile.stacks").exists()


def test_a_legacy_ci_target_cos_cannot_map_keeps_the_make_files(tmp_path: Path, capsys) -> None:
    state = _project(tmp_path)
    _legacy(tmp_path, state)
    ci = _legacy_ci(tmp_path)
    materialize_commands(tmp_path, state, _world(StackCommand("lint-frontend", "npm run lint")))
    assert ci.read_text() == _LEGACY_CI
    assert (state / "Makefile.stacks").is_file() and (state / "Makefile.base").is_file()
    assert "ci.yml still runs" in capsys.readouterr().err


def test_log_write_takes_one_line_and_ignores_stray_environment(
    tmp_path: Path, monkeypatch
) -> None:
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TASK", "999")
    runner = CliRunner()
    forged = runner.invoke(
        cli, ["log-write", "--type", "fix", "--msg", "a\n## 2020-01-01\n- forged"]
    )
    assert forged.exit_code == 2
    assert runner.invoke(cli, ["log-write", "--type", "fix", "--msg", "probe"]).exit_code == 0
    log = next(tmp_path.rglob("changes.log")).read_text()
    assert "probe" in log and "999" not in log and "forged" not in log
