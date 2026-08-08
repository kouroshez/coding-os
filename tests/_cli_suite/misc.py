"""Part of tests/test_cli.py — collected via the aggregator, not directly."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import ClassVar

import pytest
import yaml
from click.testing import CliRunner

from _cli_suite.shared import (
    cli,
)


class TestGraphReindexFailureClassification:
    # TASK-395: per-file graph-layer failures must be classified (and lock-
    # shaped ones counted toward the circuit breaker), never absorbed as
    # "processed" — the 2026-06-11 silent-stall root cause.
    def test_graph_layer_error_surfaces_reason(self):
        from cli.graph_commands import _report_failure_reason

        report = {
            "status": "ok",
            "path": "docs/tasks/T.md",
            "layers": {"graph": {"status": "error", "reason": "database is locked"}},
        }
        assert _report_failure_reason(report) == "database is locked"

    def test_top_level_error_surfaces_reason(self):
        from cli.graph_commands import _report_failure_reason

        report = {"status": "error", "reason": "read_failed: boom", "layers": {}}
        assert _report_failure_reason(report) == "read_failed: boom"

    def test_clean_report_returns_none(self):
        from cli.graph_commands import _report_failure_reason

        report = {"status": "ok", "layers": {"graph": {"status": "ok"}}}
        assert _report_failure_reason(report) is None

    def test_lock_shape_detection(self):
        from cli.graph_commands import _is_lock_shaped

        assert _is_lock_shaped("database is locked")
        assert _is_lock_shaped("SQLITE_BUSY: db busy")
        assert not _is_lock_shaped("read_failed: missing")


# ---------------------------------------------------------------------------
# Per-project extra skills — TASK-370
# ---------------------------------------------------------------------------


class TestProjectExtraSkills:
    def _make_project(self, runner: CliRunner, tmp_path: Path) -> Path:
        project = tmp_path / "proj"
        project.mkdir()
        result = runner.invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        return project

    def test_disable_enable_round_trip_core_skill(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """F4: a core skill (redis) ships by default; disable records the opt-out
        AND unlinks its adapter symlink; re-enable clears it + relinks."""
        import yaml as _yaml

        project = self._make_project(runner, tmp_path)
        monkeypatch.chdir(project)
        link = project / ".claude" / "skills" / "redis" / "SKILL.md"
        assert link.exists()  # core skill linked by init

        disabled = runner.invoke(cli, ["skill", "disable", "redis"])
        assert disabled.exit_code == 0, disabled.output
        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert "redis" in config["disabled_skills"]
        assert not link.exists()  # symlink unlinked inline

        listing = runner.invoke(cli, ["skill", "project"])
        assert "disabled (core): redis" in listing.output

        enabled = runner.invoke(cli, ["skill", "enable", "redis"])
        assert enabled.exit_code == 0, enabled.output
        config = _yaml.safe_load((project / ".coding-os.yaml").read_text(encoding="utf-8"))
        assert "redis" not in (config.get("disabled_skills") or [])
        assert link.exists()  # relinked inline

    def test_unknown_skill_and_idempotent_disable(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = self._make_project(runner, tmp_path)
        monkeypatch.chdir(project)
        unknown = runner.invoke(cli, ["skill", "enable", "no-such-skill"])
        assert unknown.exit_code != 0 and "unknown skill" in unknown.output
        first = runner.invoke(cli, ["skill", "disable", "redis"])
        assert first.exit_code == 0
        again = runner.invoke(cli, ["skill", "disable", "redis"])
        assert again.exit_code == 0 and "already disabled" in again.output

    def test_community_skill_links_into_adapter_and_survives_update(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COS_USER_SKILLS_DIR", str(tmp_path / "community"))
        source = tmp_path / "src-skill" / "team-style"
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            "---\nname: team-style\ndescription: House review conventions imported from a teammate.\n---\nbody\n",
            encoding="utf-8",
        )
        assert runner.invoke(cli, ["skill", "add", str(source), "--yes"]).exit_code == 0

        project = self._make_project(runner, tmp_path)
        monkeypatch.chdir(project)
        enabled = runner.invoke(cli, ["skill", "enable", "team-style"])
        assert enabled.exit_code == 0, enabled.output
        link = project / ".claude" / "skills" / "team-style"
        assert link.is_symlink() and (link / "SKILL.md").is_file()

        # cos update must not clobber the community link (it relinks core only).
        updated = runner.invoke(cli, ["update", "-d", str(project), "--yes"])
        assert updated.exit_code == 0, updated.output
        assert link.is_symlink() and (link / "SKILL.md").is_file()

        disabled = runner.invoke(cli, ["skill", "disable", "team-style"])
        assert disabled.exit_code == 0
        assert not link.exists()


# ---------------------------------------------------------------------------
# doctor --tokens — transcript token-usage audit
# ---------------------------------------------------------------------------


class TestDoctorTokens:
    @staticmethod
    def _usage_line(cache_read: int, output: int = 100) -> str:
        import json as json_module

        return json_module.dumps(
            {
                "message": {
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": output,
                        "cache_creation_input_tokens": 50,
                        "cache_read_input_tokens": cache_read,
                    }
                }
            }
        )

    def _make_transcripts(self, root: Path) -> Path:
        transcripts = root / "transcripts"
        transcripts.mkdir()
        main = transcripts / "aaaa1111.jsonl"
        main.write_text(
            "\n".join(
                [
                    self._usage_line(80_000),
                    "not json at all",
                    self._usage_line(200_000),
                ]
            ),
            encoding="utf-8",
        )
        sub_dir = transcripts / "aaaa1111" / "subagents"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent-bb22.jsonl").write_text(self._usage_line(30_000), encoding="utf-8")
        return transcripts

    def test_analyze_sums_usage_and_flags_budget(self, tmp_path: Path) -> None:
        from cli.doctor_tokens import analyze_tokens

        transcripts = self._make_transcripts(tmp_path)
        report = analyze_tokens(tmp_path, transcripts_dir=transcripts)
        assert report["found"] is True
        assert report["sessions"] == 2
        assert report["subagent_sessions"] == 1
        assert report["turns"] == 3
        assert report["totals"]["cache_read_input_tokens"] == 310_000
        # 310_000 cache-read / 3 turns > 100K — over the 150K default? 103K is under.
        assert report["avg_context_per_turn"] == 310_000 // 3
        # first main turn: 10 + 50 + 80_000 (output excluded)
        assert report["median_session_baseline"] == 80_060

    def test_missing_transcript_dir_reports_not_found(self, tmp_path: Path) -> None:
        from cli.doctor_tokens import analyze_tokens, format_tokens_text

        report = analyze_tokens(tmp_path, transcripts_dir=tmp_path / "nope")
        assert report["found"] is False
        assert "nothing to analyze" in format_tokens_text(report)

    def test_cli_flag_text_and_json(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json as json_module

        import cli.doctor_tokens as tokens_module

        transcripts = self._make_transcripts(tmp_path)
        monkeypatch.setattr(tokens_module, "transcript_dir_for", lambda project: transcripts)
        result = runner.invoke(cli, ["doctor", "--tokens", "-d", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "Token usage" in result.output
        assert "avg context per turn" in result.output

        json_result = runner.invoke(
            cli, ["doctor", "--tokens", "--format", "json", "-d", str(tmp_path)]
        )
        assert json_result.exit_code == 0, json_result.output
        payload = json_module.loads(json_result.output)
        assert payload["turns"] == 3

    def test_over_budget_warns(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from cli.doctor_tokens import analyze_tokens, format_tokens_text

        monkeypatch.setenv("COS_CONTEXT_BUDGET", "50000")
        transcripts = self._make_transcripts(tmp_path)
        report = analyze_tokens(tmp_path, transcripts_dir=transcripts)
        assert report["over_budget"] is True
        assert "WARN: avg context/turn exceeds budget" in format_tokens_text(report)


class TestAdopt:
    """`cos adopt` — brownfield overlay onto an existing repo (TASK-387)."""

    ADOPT_FLAGS: ClassVar[list[str]] = [
        "--agent",
        "claude",
        "--yes",
        "--no-git",
        "--no-index",
        "--no-register",
    ]

    def _seed_brownfield(self, root: Path) -> dict[str, str]:
        """Seed representative user files (build markers + code); return hashes."""
        files = {
            "pyproject.toml": '[project]\nname = "userapp"\nversion = "0.1.0"\n',
            "package.json": '{\n  "name": "userapp",\n  "version": "0.1.0"\n}\n',
            "src/app.py": "def main() -> None:\n    print('user code')\n",
        }
        hashes: dict[str, str] = {}
        for rel, content in files.items():
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            hashes[rel] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return hashes

    def _run_adopt(self, runner: CliRunner, root: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.chdir(root)
        monkeypatch.setenv("PWD", str(root))
        return runner.invoke(cli, ["adopt", *self.ADOPT_FLAGS])

    def test_adopt_overlays_without_touching_user_code(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hashes = self._seed_brownfield(tmp_path)
        result = self._run_adopt(runner, tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        # Overlay landed.
        assert (tmp_path / ".coding-os.yaml").exists()
        assert (tmp_path / "AGENTS.md").exists()
        assert (tmp_path / ".claude").is_dir()
        # No pre-existing user file was modified or deleted.
        for rel, digest in hashes.items():
            current = tmp_path / rel
            assert current.exists(), f"adopt deleted {rel}"
            actual = hashlib.sha256(current.read_bytes()).hexdigest()
            assert actual == digest, f"adopt modified pre-existing {rel}"

    def test_adopt_detects_stacks_from_markers(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
        result = self._run_adopt(runner, tmp_path, monkeypatch)
        assert result.exit_code == 0, result.output
        assert "Detected stacks:" in result.output
        config = yaml.safe_load((tmp_path / ".coding-os.yaml").read_text(encoding="utf-8"))
        templates = config.get("templates") or []
        assert templates, "detected stacks were not recorded in .coding-os.yaml"
        # python + typescript markers each resolve to a plain stack via registry.
        from cli.main import _detect_stacks_from_markers

        assert set(_detect_stacks_from_markers(tmp_path)) <= set(templates)

    def test_adopt_pivots_to_sync_when_already_installed(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        first = self._run_adopt(runner, tmp_path, monkeypatch)
        assert first.exit_code == 0, first.output
        second = self._run_adopt(runner, tmp_path, monkeypatch)
        assert second.exit_code == 0, second.output
        assert "already present" in second.output
        assert "sync" in second.output.lower()


class TestBrainSweepChangelog:
    def test_help_lists_owner_gated_flags(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["brain-sweep-changelog", "--help"])
        assert result.exit_code == 0
        assert "dry-run by default" in result.output
        for flag in ("--confirm", "--undo", "--vacuum", "--grace-days"):
            assert flag in result.output

    def test_dry_run_dispatches_end_to_end(
        self, runner: CliRunner, initialized_project: Path
    ) -> None:
        # The wrapper subprocesses memory_gc.py; CliRunner can't capture that
        # child's stdout, so exit 0 is the contract here (the JSON shape + the
        # archive/undo cycle are asserted in test_brain_hardening). Default is a
        # dry run — it must never mutate.
        result = runner.invoke(cli, ["brain-sweep-changelog", "-d", str(initialized_project)])
        assert result.exit_code == 0, result.output
