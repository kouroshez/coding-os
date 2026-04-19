"""Tests for `cos doctor` check functions.

Uses real `cos init` scaffolds (via subprocess) as fixtures because doctor's
value is in observing real scaffold state. Tests are parameterized on agent
to cover both Claude and Codex parity.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli.doctor import (
    DoctorReport,
    EXPECTED_SCHEMA_VERSION,
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    _check_placeholders,
    run_doctor,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _cos_init(target: Path, agent: str = "claude", template: str | None = None) -> None:
    cmd = [
        sys.executable, "-m", "cli.main", "init",
        "--agent", agent,
        "--project-dir", str(target.parent),
        "--name", target.name,
        "--no-git",
        "--force",
    ]
    if template:
        cmd.extend(["--template", template])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(
        cmd, cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=120, check=True,
    )


def _severity_map(report: DoctorReport) -> dict[str, str]:
    return {c.id: c.severity for c in report.checks}


# ---------- C1: missing config ----------

def test_doctor_missing_config_fails(tmp_path: Path) -> None:
    report = run_doctor(tmp_path)
    sevs = _severity_map(report)
    assert sevs["C1"] == SEV_FAIL
    # Fatal: downstream checks should not run
    assert "C2" not in sevs


def test_doctor_invalid_yaml_fails(tmp_path: Path) -> None:
    (tmp_path / ".coding-os.yaml").write_text("::: not yaml ::: [")
    report = run_doctor(tmp_path)
    assert _severity_map(report)["C1"] == SEV_FAIL


# ---------- Fresh scaffold → all PASS ----------

@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_doctor_fresh_scaffold_all_pass(tmp_path: Path, agent: str) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent=agent, template="nextjs")
    report = run_doctor(target)

    sevs = _severity_map(report)
    for check_id in ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10"):
        assert sevs.get(check_id) == SEV_PASS, (
            f"{check_id} not PASS for agent={agent}: "
            f"{[c for c in report.checks if c.id == check_id]}"
        )


@pytest.mark.parametrize("agent", ["claude", "codex"])
def test_doctor_base_template_pass(tmp_path: Path, agent: str) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent=agent, template=None)
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C8"] == SEV_PASS


# ---------- C8: drift detection ----------

def test_doctor_missing_file_fails_c8(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="nextjs")
    # Delete AGENTS.md → C6 will catch it, C8 will also catch missing path
    (target / "AGENTS.md").unlink()
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C6"] == SEV_FAIL  # scaffold root missing
    assert sevs["C8"] == SEV_FAIL  # manifest diff missing


def test_doctor_extra_file_warns_c8(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="nextjs")
    (target / "docs" / "custom-user-file.md").write_text("added by user")
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C8"] == SEV_WARN


# ---------- C9: placeholder detection ----------

def test_doctor_unresolved_placeholder_fails(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="nextjs")
    # Inject an unresolved placeholder into AGENTS.md
    agents_md = target / "AGENTS.md"
    agents_md.write_text(agents_md.read_text() + "\n{{leaked_placeholder}}\n")
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C9"] == SEV_FAIL


def test_check_placeholders_clean_project(tmp_path: Path) -> None:
    # Minimal scaffold with no placeholders
    (tmp_path / "AGENTS.md").write_text("# Clean\nNo placeholders here.\n")
    (tmp_path / "Makefile").write_text("help:\n\t@echo ok\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("plain")

    report = DoctorReport(project_dir=str(tmp_path), agent=None, templates=[])
    _check_placeholders(tmp_path, report)
    assert report.checks[0].severity == SEV_PASS


# ---------- C4: schema version ----------

def test_expected_schema_version_is_reasonable() -> None:
    # Sourced from db.MIGRATIONS — must be a positive int.
    assert isinstance(EXPECTED_SCHEMA_VERSION, int)
    assert EXPECTED_SCHEMA_VERSION >= 1


# ---------- JSON output ----------

def test_doctor_json_format_valid_schema(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template=None)

    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "doctor",
         "--project-dir", str(target), "--format", "json"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60, check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    payload = json.loads(result.stdout)
    assert "checks" in payload
    assert "summary" in payload
    assert {"pass", "warn", "fail", "exit_code"}.issubset(payload["summary"].keys())
    assert payload["summary"]["fail"] == 0


# ---------- C11: stack registry consistency ----------

def test_doctor_c11_base_only_passes(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template=None)
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C11"] == SEV_PASS


def test_doctor_c11_known_stack_passes(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="django")
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C11"] == SEV_PASS


def test_doctor_c11_unknown_stack_fails(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="django")
    # Simulate someone adding a ghost stack to the project config
    import yaml as _yaml
    cfg_path = target / ".coding-os.yaml"
    cfg = _yaml.safe_load(cfg_path.read_text())
    cfg["templates"].append("ghoststack")
    cfg_path.write_text(_yaml.dump(cfg))
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C11"] == SEV_FAIL


# ---------- C12: category balance ----------

def test_doctor_c12_single_stack_passes(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="django")
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C12"] == SEV_PASS


def test_doctor_c12_multi_backend_warns(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="django")
    # Force a second backend stack by editing the config directly.
    import yaml as _yaml
    cfg_path = target / ".coding-os.yaml"
    cfg = _yaml.safe_load(cfg_path.read_text())
    cfg["templates"].append("fastapi")
    cfg_path.write_text(_yaml.dump(cfg))
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C12"] == SEV_WARN


def test_doctor_c12_backend_plus_frontend_passes(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="django")
    import yaml as _yaml
    cfg_path = target / ".coding-os.yaml"
    cfg = _yaml.safe_load(cfg_path.read_text())
    cfg["templates"].append("nextjs")
    cfg_path.write_text(_yaml.dump(cfg))
    report = run_doctor(target)
    sevs = _severity_map(report)
    assert sevs["C12"] == SEV_PASS


def test_doctor_strict_mode_exits_nonzero_on_warn(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    _cos_init(target, agent="claude", template="nextjs")
    (target / "docs" / "extra.md").write_text("user add")

    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "doctor",
         "--project-dir", str(target), "--strict"],
        cwd=str(REPO_ROOT),
        capture_output=True, text=True, timeout=60, check=False,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
    )
    assert result.returncode == 1
