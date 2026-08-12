"""`cos init`'s setup-mode question and the completion panel.

Before this, an interactive `cos init` asked three questions (agent, stacks,
name) and never surfaced the 21 presets or the module profiles that existed only
as flags — and it finished without naming the command that upgrades coding-os.
"""

from __future__ import annotations

import sys
from pathlib import Path

from click.testing import CliRunner

SRC = Path(__file__).resolve().parent.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import click

from cli import _init_summary, _init_world
from cli.core_version import UPGRADE_COMMAND


def _run_prompt(answers: str) -> tuple[tuple[str | None, str | None], str]:
    """Drive _prompt_setup_mode through click's isolated stdin."""
    captured: dict = {}

    @click.command()
    def _driver() -> None:
        captured["result"] = _init_world._prompt_setup_mode(preset_id=None, profile=None)

    result = CliRunner().invoke(_driver, input=answers)
    return captured.get("result", (None, None)), result.output


class TestSetupMode:
    def test_quick_prints_the_defaults_it_applied(self) -> None:
        # An installer that silently decides leaves no way to learn what is
        # configurable — the defaults have to be visible to be changeable.
        (preset, profile), output = _run_prompt("1\n")

        assert preset is None and profile is None
        assert "Applied recommended defaults" in output
        assert "Module profile:" in output
        assert "cos init --help" in output

    def test_quick_is_the_default_answer(self) -> None:
        _, output = _run_prompt("\n")
        assert "Applied recommended defaults" in output

    def test_custom_offers_presets_and_profiles(self) -> None:
        # "0" = no preset, then accept the default profile.
        (preset, profile), output = _run_prompt("2\n0\n\n")

        assert "Ready-made stack compositions:" in output
        assert "Module profile — curates" in output
        assert preset is None
        assert profile is not None

    def test_custom_accepts_a_preset_by_name(self) -> None:
        (preset, _profile), _ = _run_prompt("2\nmern\n\n")
        assert preset == "mern"

    def test_an_unknown_preset_name_falls_back_to_none(self) -> None:
        # Never scaffold something the user did not ask for on a typo.
        (preset, _profile), _ = _run_prompt("2\nnot-a-real-preset\n\n")
        assert preset is None

    def test_an_aborted_prompt_says_so_and_keeps_the_flags(self, monkeypatch) -> None:
        def _abort(*_args, **_kwargs):
            raise click.exceptions.Abort()

        monkeypatch.setattr(_init_world, "_ask_setup_mode", _abort)
        runner = CliRunner()

        @click.command()
        def _driver() -> None:
            result = _init_world._prompt_setup_mode(preset_id="mern", profile="lean")
            click.echo(f"kept={result}")

        outcome = runner.invoke(_driver)
        assert "kept=('mern', 'lean')" in outcome.output
        assert "setup questions skipped" in (outcome.output + (outcome.stderr or ""))


class TestCompletionPanel:
    def _panel(self, tmp_path: Path, **overrides) -> str:
        kwargs = {
            "agents": ["claude"],
            "templates": ("django",),
            "files_created": 329,
            "disabled_modules": [],
        }
        kwargs.update(overrides)

        @click.command()
        def _driver() -> None:
            _init_summary.print_completion_panel(tmp_path, **kwargs)

        return CliRunner().invoke(_driver).output

    def test_names_the_command_that_upgrades_coding_os(self, tmp_path: Path) -> None:
        output = self._panel(tmp_path)
        assert UPGRADE_COMMAND in output
        assert "cos update" in output

    def test_reports_the_installed_version(self, tmp_path: Path) -> None:
        assert "Version:" in self._panel(tmp_path)

    def test_warns_when_no_stack_was_selected(self, tmp_path: Path) -> None:
        assert "No stack template selected" in self._panel(tmp_path, templates=())

    def test_stays_quiet_about_stacks_when_one_was_selected(self, tmp_path: Path) -> None:
        assert "No stack template selected" not in self._panel(tmp_path)

    def test_points_at_module_list_when_the_board_is_off(self, tmp_path: Path) -> None:
        output = self._panel(tmp_path, disabled_modules=["tasks"])
        assert "cos module list" in output
        assert "cos daily" not in output
