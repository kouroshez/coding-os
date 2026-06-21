"""TASK-078 — core-version stamp + doctor drift check."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cli.core_version import (  # noqa: E402
    STAMP_FILENAME,
    current_core_version,
    read_stamped_version,
    stamp_core_version,
)
from cli.doctor import (  # noqa: E402
    SEV_PASS,
    SEV_WARN,
    DoctorReport,
    _check_core_version,
)


def _state(tmp_path: Path) -> Path:
    s = tmp_path / ".coding-os"
    s.mkdir()
    return s


def _report() -> DoctorReport:
    return DoctorReport(project_dir=".", agent=None, templates=[])


def _stamp_check(state: Path):
    report = _report()
    _check_core_version(state, report)
    return next(c for c in report.checks if c.id == "core.version_stamp")


def test_stamp_roundtrip(tmp_path: Path) -> None:
    state = _state(tmp_path)
    path = stamp_core_version(state)
    assert path.name == STAMP_FILENAME
    assert read_stamped_version(state) == current_core_version()
    data = json.loads(path.read_text())
    assert data["core_version"] == current_core_version()
    assert "stamped_at" in data


def test_read_missing_returns_none(tmp_path: Path) -> None:
    assert read_stamped_version(tmp_path / "nope") is None


def test_read_corrupt_returns_none(tmp_path: Path) -> None:
    state = _state(tmp_path)
    (state / STAMP_FILENAME).write_text("{ not json", encoding="utf-8")
    assert read_stamped_version(state) is None


def test_doctor_pass_when_match(tmp_path: Path) -> None:
    state = _state(tmp_path)
    stamp_core_version(state)
    assert _stamp_check(state).severity == SEV_PASS


def test_doctor_warn_on_drift(tmp_path: Path) -> None:
    state = _state(tmp_path)
    (state / STAMP_FILENAME).write_text(json.dumps({"core_version": "0.0.1-old"}), encoding="utf-8")
    check = _stamp_check(state)
    assert check.severity == SEV_WARN
    assert "drift" in check.message


def test_doctor_warn_when_missing(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert _stamp_check(state).severity == SEV_WARN
