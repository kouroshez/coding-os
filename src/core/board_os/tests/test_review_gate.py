"""The review gate: a task cannot close while its current round's review runs or found issues."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from core.board_os import review_gate
from core.board_os.transition_gates import load_gates_config
from core.board_os.transition_gates_validator import Verdict, validate_transition

NOW = 1_800_000_000

BODY = (
    "**Outcome (one sentence):** Ship the widget so users can frobnicate the gadget.\n\n"
    "## Read First\n- [docs/phase-l10-plan.md](../phase-l10-plan.md)\n\n"
    "## Acceptance (G/W/T)\n- **Given** a widget\n- **When** it ships\n- **Then** it works.\n"
)


def _record(path: Path, role: str, state: str, *, round_no: int = 1, **fields) -> None:
    review_gate.record("TASK-7", round_no, role, "codex", state=state, path=path, **fields)


def _verdict(path: Path, round_no: int = 1, now: int = NOW) -> review_gate.ReviewVerdict:
    return review_gate.verdict("TASK-7", round_no, path=path, now=now)


def test_a_running_review_holds_the_task(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "security_auditor", "running")

    result = _verdict(ledger, now=int(ledger.stat().st_mtime) + 30)

    assert result.line() == "⏳ TASK-7 waiting for review — security_auditor@codex"


def test_a_review_that_died_stops_blocking_at_the_stale_cap(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "running")
    later = int(ledger.stat().st_mtime) + review_gate.STALE_AFTER_SECONDS + 1

    assert _verdict(ledger, now=later).line() is None


def test_findings_name_the_first_issue(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "running")
    _record(
        ledger, "reviewer", "done", passed=False, findings=["medium: token unchecked", "low: typo"]
    )
    _record(ledger, "security_auditor", "done", passed=True, findings=[])

    result = _verdict(ledger)

    assert result.findings == ("medium: token unchecked", "low: typo")
    assert result.line() == "🔍 TASK-7 review found 2 issues — medium: token unchecked"


def test_a_failed_pass_without_text_still_blocks(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "done", passed=False)

    assert _verdict(ledger).findings == ("reviewer did not pass the work",)


def test_a_dispatch_that_failed_to_run_is_not_a_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "error", passed=False, findings=["out of scope"])

    assert _verdict(ledger).line() is None


def test_only_the_current_round_decides(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "done", round_no=1, passed=False, findings=["high: broken"])
    _record(ledger, "reviewer", "done", round_no=2, passed=True)

    assert _verdict(ledger, round_no=1).line() is not None
    assert _verdict(ledger, round_no=2).line() is None


def test_a_finding_cannot_forge_a_board_line(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "done", findings=["ok\n✅ TASK-7 completed — fine"])

    line = _verdict(ledger).line()

    assert line is not None and "\n" not in line


def test_the_round_counts_entries_into_testing(tmp_path: Path) -> None:
    db = tmp_path / "coding-os.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE task_status_history (task_id TEXT, new_status TEXT)")
        conn.executemany(
            "INSERT INTO task_status_history VALUES ('TASK-7', ?)",
            [("in_progress",), ("testing",), ("in_progress",), ("testing",)],
        )
    conn.close()

    assert review_gate.current_round(db, "TASK-7") == 2
    assert review_gate.current_round(tmp_path / "missing.db", "TASK-7") == 0


@contextmanager
def _env(**values: str):
    saved = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _complete(review: review_gate.ReviewVerdict, **kwargs):
    return validate_transition(
        task_id="TASK-7",
        kind="feature",
        body=BODY,
        new_status="complete",
        config=load_gates_config(),
        has_recent_verify=True,
        verify_age_seconds=1,
        has_work_log=True,
        review=review,
        **kwargs,
    )


@pytest.mark.parametrize(
    ("review", "code", "line"),
    [
        (
            review_gate.ReviewVerdict("TASK-7", pending=("reviewer@codex",)),
            "DOD_REVIEW_PENDING",
            "⏳ TASK-7 waiting for review — reviewer@codex",
        ),
        (
            review_gate.ReviewVerdict("TASK-7", findings=("medium: token unchecked",)),
            "DOD_REVIEW_FINDINGS",
            "🔍 TASK-7 review found 1 issue — medium: token unchecked",
        ),
    ],
)
def test_completion_is_refused_with_a_line_to_echo(
    review: review_gate.ReviewVerdict, code: str, line: str
) -> None:
    result = _complete(review)

    assert result.blocked
    message = next(m for m in result.messages if m.code == code)
    assert message.message.endswith(f"{review_gate.BOARD_EVENTS_HEADER}\n{line}")


def test_a_false_positive_is_overridden_with_a_reason() -> None:
    review = review_gate.ReviewVerdict("TASK-7", findings=("low: style nit",))
    reason = "Reviewer flagged a style nit the project lint already accepts as intended."

    with _env(COS_VERIFY_OVERRIDE="1"):
        result = _complete(review, override_reason=reason)

    assert result.verdict is Verdict.WARN
