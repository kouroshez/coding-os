"""codex.project_trusted: Codex reads the project .codex/ layer only once trusted.

Spec: docs/engineering/adapter-parity.md § Trust And Installation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._doctor_adapters import _check_codex_project_trusted
from cli.doctor import DoctorReport


def _check(project: Path) -> list:
    report = DoctorReport(project_dir=project, agent="codex", templates=[])
    _check_codex_project_trusted(project, report)
    return report.checks


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "project"
    (root / ".codex").mkdir(parents=True)
    (root / ".codex" / "config.toml").write_text("[features]\nhooks = true\n")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    (tmp_path / "codex-home").mkdir()
    return root


def test_an_untrusted_project_warns_with_the_fix(project: Path, tmp_path: Path) -> None:
    (result,) = _check(project)
    assert result.severity == "WARN" and "trust_level" in result.message


@pytest.mark.parametrize("trusted", ["self", "ancestor"])
def test_a_trusted_project_or_ancestor_passes(project: Path, tmp_path: Path, trusted: str) -> None:
    path = project.resolve() if trusted == "self" else tmp_path.resolve()
    (tmp_path / "codex-home" / "config.toml").write_text(
        f'[projects."{path}"]\ntrust_level = "trusted"\n'
    )
    (result,) = _check(project)
    assert result.severity == "PASS"


def test_a_project_without_codex_config_is_not_checked(tmp_path: Path) -> None:
    assert _check(tmp_path) == []
