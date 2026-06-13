"""Tests for `cos doctor --structure` — project anatomy validation (TASK-366).

Fast unit + CLI tests: they build a bare src/ tree in tmp_path and call the
check directly / via CliRunner — no full `cos init` scaffold needed.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from cli.doctor import (
    SEV_FAIL,
    SEV_PASS,
    DoctorReport,
    _check_structure,
    _declared_src_segments,
    doctor,
)


def _report(project: Path) -> DoctorReport:
    return DoctorReport(project_dir=str(project), agent=None, templates=[])


def _mkdirs(project: Path, *rel: str) -> None:
    for r in rel:
        (project / r).mkdir(parents=True, exist_ok=True)


def _write_boundary(project: Path, stacks: list[dict]) -> None:
    state = project / ".coding-os"
    state.mkdir(parents=True, exist_ok=True)
    (state / "scaffold-boundary.yaml").write_text(
        yaml.safe_dump({"stacks": stacks}), encoding="utf-8"
    )


# ---------- _declared_src_segments ----------


def test_declared_segments_from_boundary(tmp_path: Path) -> None:
    _write_boundary(
        tmp_path,
        [
            {"stack": "fastapi", "roots": ["src/services/fastapi/"]},
            {"stack": "nextjs", "roots": ["src/frontend/"]},
        ],
    )
    assert _declared_src_segments(tmp_path, None) == {"services", "frontend"}


def test_declared_segments_empty_without_boundary(tmp_path: Path) -> None:
    assert _declared_src_segments(tmp_path, None) == set()


# ---------- _check_structure ----------


def test_no_src_tree_passes(tmp_path: Path) -> None:
    report = _report(tmp_path)
    _check_structure(tmp_path, report)
    assert report.exit_code(strict=False) == 0
    assert all(c.severity == SEV_PASS for c in report.checks)


def test_compliant_tree_with_boundary_passes(tmp_path: Path) -> None:
    _write_boundary(
        tmp_path,
        [
            {"stack": "fastapi", "roots": ["src/backend/"]},
            {"stack": "nextjs", "roots": ["src/frontend/"]},
        ],
    )
    _mkdirs(tmp_path, "src/backend", "src/frontend", "src/shared/contracts")
    report = _report(tmp_path)
    _check_structure(tmp_path, report, {"state_dir": ".coding-os"})
    assert report.exit_code(strict=False) == 0
    assert any(c.id == "structure.anatomy" and c.severity == SEV_PASS for c in report.checks)


def test_no_boundary_skips_validation(tmp_path: Path) -> None:
    # A project that never declared an anatomy (no scaffold-boundary.yaml) — e.g.
    # the meta-repo itself with src/{core,cli,adapters,...} — must not be flagged.
    _mkdirs(tmp_path, "src/core", "src/cli", "src/adapters", "src/scripts", "src/templates")
    report = _report(tmp_path)
    _check_structure(tmp_path, report)
    assert report.exit_code(strict=False) == 0
    assert [c.id for c in report.checks] == ["structure.not_declared"]


def test_stray_top_level_dir_fails_with_expected_location(tmp_path: Path) -> None:
    _write_boundary(tmp_path, [{"stack": "fastapi", "roots": ["src/backend/"]}])
    _mkdirs(tmp_path, "src/backend", "src/weirdthing")
    report = _report(tmp_path)
    _check_structure(tmp_path, report, {"state_dir": ".coding-os"})
    assert report.exit_code(strict=False) == 1
    fails = [c for c in report.checks if c.severity == SEV_FAIL]
    assert len(fails) == 1
    assert fails[0].id == "structure.stray.weirdthing"
    assert "src/weirdthing/" in fails[0].message
    assert "expected:" in fails[0].message
    assert fails[0].details["expected"]


def test_multi_backend_flags_backend_outside_services(tmp_path: Path) -> None:
    _write_boundary(
        tmp_path,
        [
            {"stack": "fastapi", "roots": ["src/services/fastapi/"]},
            {"stack": "go-fiber", "roots": ["src/services/go-fiber/"]},
        ],
    )
    # boundary says this is multi-backend (services/), but a stray src/backend/ exists
    _mkdirs(tmp_path, "src/services/fastapi", "src/services/go-fiber", "src/backend")
    report = _report(tmp_path)
    config = {"state_dir": ".coding-os"}
    _check_structure(tmp_path, report, config)
    fails = [c for c in report.checks if c.severity == SEV_FAIL]
    assert [c.id for c in fails] == ["structure.stray.backend"]
    assert "src/services/" in fails[0].message


def test_known_anatomy_slot_without_stack_is_not_flagged(tmp_path: Path) -> None:
    # boundary declares only a backend; a hand-added src/frontend/ is still a
    # known anatomy slot, so it must NOT be reported as a stray subtree.
    _write_boundary(tmp_path, [{"stack": "fastapi", "roots": ["src/backend/"]}])
    _mkdirs(tmp_path, "src/backend", "src/frontend", "src/shared")
    report = _report(tmp_path)
    _check_structure(tmp_path, report, {"state_dir": ".coding-os"})
    assert report.exit_code(strict=False) == 0
    assert all(c.severity == SEV_PASS for c in report.checks)


def test_services_tree_with_boundary_is_compliant(tmp_path: Path) -> None:
    _write_boundary(
        tmp_path,
        [{"stack": "fastapi", "roots": ["src/services/fastapi/"]}],
    )
    _mkdirs(tmp_path, "src/services/fastapi", "src/shared/contracts")
    report = _report(tmp_path)
    _check_structure(tmp_path, report, {"state_dir": ".coding-os"})
    assert report.exit_code(strict=False) == 0


# ---------- CLI wiring ----------


def test_multiple_stray_subtrees_all_reported(tmp_path: Path) -> None:
    _write_boundary(tmp_path, [{"stack": "fastapi", "roots": ["src/backend/"]}])
    _mkdirs(tmp_path, "src/backend", "src/aaa", "src/bbb", "src/ccc")
    report = _report(tmp_path)
    _check_structure(tmp_path, report, {"state_dir": ".coding-os"})
    fails = sorted(c.id for c in report.checks if c.severity == SEV_FAIL)
    assert fails == ["structure.stray.aaa", "structure.stray.bbb", "structure.stray.ccc"]


def test_cli_structure_compliant_exit_zero(tmp_path: Path) -> None:
    _write_boundary(tmp_path, [{"stack": "fastapi", "roots": ["src/backend/"]}])
    _mkdirs(tmp_path, "src/backend", "src/shared/contracts")
    result = CliRunner().invoke(doctor, ["--structure", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "structure" in result.output.lower()


def test_cli_structure_violation_exit_one(tmp_path: Path) -> None:
    _write_boundary(tmp_path, [{"stack": "fastapi", "roots": ["src/backend/"]}])
    _mkdirs(tmp_path, "src/backend", "src/rogue")
    result = CliRunner().invoke(doctor, ["--structure", "--project-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "src/rogue/" in result.output
    assert "expected:" in result.output
