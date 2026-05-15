"""Coverage for doctor suppression glob + --explain."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src" / "core") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src" / "core"))

from cli.doctor import (
    CheckResult,
    DoctorReport,
    SEV_PASS,
    SEV_WARN,
    _explain_check,
    _ignore_globs_from_config,
    _suppress_checks,
    doctor as doctor_cli,
)


def _report() -> DoctorReport:
    report = DoctorReport(project_dir=".", agent=None, templates=[])
    report.checks = [
        CheckResult("graph.freshness", SEV_WARN, "msg"),
        CheckResult("graph.parse_error_rate", SEV_PASS, "msg"),
        CheckResult("hook.cos_env_sourced", SEV_PASS, "msg"),
        CheckResult("adapter.configured", SEV_PASS, "msg"),
    ]
    return report


def test_suppress_drops_only_matching_globs() -> None:
    report = _report()
    dropped = _suppress_checks(report, ["graph.*"])
    assert dropped == 2
    assert [c.id for c in report.checks] == ["hook.cos_env_sourced", "adapter.configured"]


def test_suppress_supports_multiple_globs() -> None:
    report = _report()
    dropped = _suppress_checks(report, ["graph.*", "adapter.*"])
    assert dropped == 3
    assert [c.id for c in report.checks] == ["hook.cos_env_sourced"]


def test_suppress_noop_when_no_match() -> None:
    report = _report()
    dropped = _suppress_checks(report, ["nonexistent.*"])
    assert dropped == 0
    assert len(report.checks) == 4


def test_suppress_empty_list_is_safe() -> None:
    report = _report()
    dropped = _suppress_checks(report, [])
    assert dropped == 0
    assert len(report.checks) == 4


def test_ignore_globs_from_config_extracts_strings() -> None:
    config = {"doctor": {"ignore": ["graph.*", "hook.*"]}}
    assert _ignore_globs_from_config(config) == ["graph.*", "hook.*"]


def test_ignore_globs_from_config_drops_non_strings() -> None:
    config = {"doctor": {"ignore": ["graph.*", 42, None, "ok"]}}
    assert _ignore_globs_from_config(config) == ["graph.*", "ok"]


def test_ignore_globs_from_config_missing_block() -> None:
    assert _ignore_globs_from_config({}) == []
    assert _ignore_globs_from_config({"doctor": None}) == []
    assert _ignore_globs_from_config({"doctor": {}}) == []


def test_explain_known_id_returns_section() -> None:
    out = _explain_check("hook.cos_env_sourced")
    assert "hook.cos_env_sourced" in out
    assert "Rule 3" in out or "cos-env.sh" in out
    assert "doctor-checks.md" in out


def test_explain_unknown_id_returns_helpful_message() -> None:
    out = _explain_check("nonexistent.fake")
    assert "no entry" in out.lower() or "not found" in out.lower()


def test_cli_explain_prints_section_and_exits_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    result = runner.invoke(doctor_cli, ["--explain", "hook.cos_env_sourced"])
    assert result.exit_code == 0
    assert "hook.cos_env_sourced" in result.output


def test_cli_explain_unknown_id_still_exits_clean() -> None:
    runner = CliRunner()
    result = runner.invoke(doctor_cli, ["--explain", "fake.nope"])
    assert result.exit_code == 0
    assert "fake.nope" in result.output
