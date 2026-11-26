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


def test_an_untrusted_project_warns_with_the_fix(project: Path) -> None:
    (result,) = _check(project)
    assert result.severity == "WARN" and "trust_level" in result.message


def _trust(tmp_path: Path, entries: dict[Path, str]) -> None:
    body = "".join(
        f'[projects."{path.resolve()}"]\ntrust_level = "{level}"\n'
        for path, level in entries.items()
    )
    (tmp_path / "codex-home" / "config.toml").write_text(body)


def test_a_trusted_project_passes(project: Path, tmp_path: Path) -> None:
    _trust(tmp_path, {project: "trusted"})
    (result,) = _check(project)
    assert result.severity == "PASS"


def test_a_trusted_git_root_passes_but_a_plain_ancestor_does_not(
    project: Path, tmp_path: Path
) -> None:
    _trust(tmp_path, {tmp_path: "trusted"})
    assert _check(project)[0].severity == "WARN"
    (tmp_path / ".git").mkdir()
    assert _check(project)[0].severity == "PASS"


def test_an_explicit_untrusted_entry_on_the_project_wins(project: Path, tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _trust(tmp_path, {tmp_path: "trusted", project: "untrusted"})
    assert _check(project)[0].severity == "WARN"


def test_a_project_without_codex_config_is_not_checked(tmp_path: Path) -> None:
    assert _check(tmp_path) == []
