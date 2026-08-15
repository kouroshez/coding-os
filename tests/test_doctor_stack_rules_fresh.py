"""A stack rule that drifts from its template must be visible.

Core rules are symlinks and reach every project on edit. Stack rules are copies
by design, so the user can tailor them — but nothing refreshed them and nothing
reported the divergence, so an edit to `src/templates/<stack>/rules/` could look
propagated while reaching no install at all. Confirmed by executing: replacing an
installed copy with a stale marker survived `cos update` untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cli._doctor_shared import SEV_PASS, SEV_WARN, DoctorReport
from cli._doctor_stacks import _check_stack_rules_fresh

STACK = "meta"
RULE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "templates" / STACK / "rules"


def _report(project: Path, *, agent: str | None = "claude", templates: list[str] | None = None):
    return DoctorReport(
        project_dir=str(project),
        agent=agent,
        templates=[STACK] if templates is None else templates,
    )


def _install(project: Path, source: Path, *, body: str | None = None) -> Path:
    rules_dir = project / ".claude" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    installed = rules_dir / f"{STACK}-{source.name}"
    installed.write_text(
        source.read_text(encoding="utf-8") if body is None else body, encoding="utf-8"
    )
    return installed


@pytest.fixture
def rule_source() -> Path:
    sources = sorted(RULE_SOURCE.glob("*.md"))
    if not sources:
        pytest.skip(f"no stack rules under {RULE_SOURCE}")
    return sources[0]


def test_faithful_copy_passes(tmp_path: Path, rule_source: Path) -> None:
    _install(tmp_path, rule_source)
    report = _report(tmp_path)
    _check_stack_rules_fresh(tmp_path, report)
    assert report.checks[-1].severity == SEV_PASS


def test_drifted_copy_warns_and_names_the_file(tmp_path: Path, rule_source: Path) -> None:
    installed = _install(
        tmp_path, rule_source, body=rule_source.read_text(encoding="utf-8") + "\ndrift\n"
    )
    report = _report(tmp_path)
    _check_stack_rules_fresh(tmp_path, report)

    check = report.checks[-1]
    assert check.severity == SEV_WARN, "drift must not pass silently"
    assert installed.name in check.message
    assert check.details["drifted"] == [installed.name]


def test_drift_warns_rather_than_fails(tmp_path: Path, rule_source: Path) -> None:
    """Ownership stays with the user — the check surfaces, it does not veto."""
    _install(tmp_path, rule_source, body="deliberately customised\n")
    report = _report(tmp_path)
    _check_stack_rules_fresh(tmp_path, report)
    assert report.exit_code(strict=False) == 0


def test_no_stacks_is_a_stated_skip(tmp_path: Path) -> None:
    report = _report(tmp_path, templates=[])
    _check_stack_rules_fresh(tmp_path, report)
    assert report.checks[-1].severity == SEV_PASS
    assert "skipped" in report.checks[-1].message


def test_no_agent_is_a_stated_skip(tmp_path: Path) -> None:
    report = _report(tmp_path, agent=None)
    _check_stack_rules_fresh(tmp_path, report)
    assert report.checks[-1].severity == SEV_PASS
    assert "skipped" in report.checks[-1].message


def test_uninstalled_rule_is_not_drift(tmp_path: Path) -> None:
    """A stack rule the project never installed is absent, not divergent."""
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    report = _report(tmp_path)
    _check_stack_rules_fresh(tmp_path, report)
    assert report.checks[-1].severity == SEV_PASS
