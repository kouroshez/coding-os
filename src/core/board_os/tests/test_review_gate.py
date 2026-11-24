"""The review gate: a task cannot close while its current round's review runs or found issues."""

from __future__ import annotations

import os
import sqlite3
import subprocess
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

    assert _verdict(ledger, now=later).line() == (
        "⚠️ TASK-7 closing without review — reviewer@codex could not run"
    )


def test_a_round_with_no_review_says_so(tmp_path: Path) -> None:
    assert _verdict(tmp_path / review_gate.LEDGER_NAME).line() == (
        "⚠️ TASK-7 closing without review — no review was recorded for this testing round"
    )


def test_a_role_that_failed_beside_a_clean_review_warns_without_blocking(tmp_path: Path) -> None:
    # An errored audit beside a pass must still show, or the change reads as audited.
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "done", passed=True)
    _record(ledger, "security_auditor", "error")

    review = _verdict(ledger)
    code, blocks, _message = review_gate.dod_review_outcome(review) or ("", True, "")

    assert (code, blocks) == ("DOD_REVIEW_SKIPPED", False)
    assert "closing without a full review — security_auditor@" in (review.line() or "")


def test_findings_name_the_first_issue(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "running")
    _record(
        ledger, "reviewer", "done", passed=False, findings=["medium: token unchecked", "low: typo"]
    )
    _record(ledger, "security_auditor", "done", passed=True, findings=[])

    result = _verdict(ledger)

    assert result.findings == ("medium: token unchecked", "low: typo")
    assert result.line() == "🔍 TASK-7 review found 2 issues, 1 blocking — medium: token unchecked"


def test_a_failed_pass_without_text_still_blocks(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "done", passed=False)

    assert _verdict(ledger).findings == ("reviewer did not pass the work",)


def test_a_dispatch_that_failed_to_run_is_not_a_verdict(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    _record(ledger, "reviewer", "error", passed=False, findings=["out of scope"])

    result = _verdict(ledger)

    assert result.findings == ()
    assert result.skipped == "closing without review — reviewer@codex could not run"


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


def test_rounds_count_testing_entries_and_restart_after_an_unblock(tmp_path: Path) -> None:
    db = tmp_path / "coding-os.db"
    moves = [
        ("icebox", "in_progress"),
        ("in_progress", "testing"),
        ("testing", "in_progress"),
        ("in_progress", "testing"),
        ("testing", "blocked"),
        ("blocked", "in_progress"),
        ("in_progress", "testing"),
    ]
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE task_status_history (id INTEGER PRIMARY KEY, task_id TEXT,"
            " old_status TEXT, new_status TEXT)"
        )
        conn.executemany(
            "INSERT INTO task_status_history (task_id, old_status, new_status) VALUES ('TASK-7', ?, ?)",
            moves,
        )
    conn.close()

    assert review_gate.current_round(db, "TASK-7") == 3
    # The operator's unblock buys a fresh three rounds before the next escalation.
    assert review_gate.rounds_since_unblock(db, "TASK-7") == 1
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
            "🔍 TASK-7 review found 1 issue, 1 blocking — medium: token unchecked",
        ),
        (
            review_gate.ReviewVerdict(
                "TASK-7", findings=("high: a", "low: b"), round_no=5, streak=3
            ),
            "DOD_REVIEW_ESCALATE",
            "🛑 TASK-7 still has 1 blocking issue after 3 review rounds — needs your decision",
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


def test_a_missing_review_warns_but_never_strands_the_task() -> None:
    review = review_gate.ReviewVerdict(
        "TASK-7", skipped="closing without review — reviewer@claude could not run"
    )

    result = _complete(review)

    assert not result.blocked
    message = next(m for m in result.messages if m.code == "DOD_REVIEW_SKIPPED")
    assert message.severity is Verdict.WARN
    assert message.message.endswith(
        "⚠️ TASK-7 closing without review — reviewer@claude could not run"
    )


def test_every_finding_reaches_the_author_in_one_list() -> None:
    findings = tuple(f"medium: issue {n}" for n in range(1, 8))

    result = _complete(review_gate.ReviewVerdict("TASK-7", findings=findings, round_no=1))

    message = next(m for m in result.messages if m.code == "DOD_REVIEW_FINDINGS").message
    assert all(f"{n}. medium: issue {n}" in message for n in range(1, 8))
    assert "review found 7 issues, 7 blocking" in message


def test_minor_notes_alone_never_send_the_task_back() -> None:
    review = review_gate.ReviewVerdict("TASK-7", findings=("low: rename x", "info: doc typo"))

    result = _complete(review)

    assert not result.blocked
    message = next(m for m in result.messages if m.code == "DOD_REVIEW_NOTES").message
    assert message.endswith("📝 TASK-7 review passed with 2 minor notes — low: rename x")


@pytest.mark.parametrize(
    "finding", ["the cache never expires", "Low-level crypto misuse", "high-risk path unchecked"]
)
def test_only_a_severity_label_makes_a_finding_minor(finding: str) -> None:
    review = review_gate.ReviewVerdict("TASK-7", findings=(finding,))

    assert review.blocking == (finding,)


def test_the_cap_keeps_the_most_severe_and_counts_the_rest(tmp_path: Path) -> None:
    ledger = tmp_path / review_gate.LEDGER_NAME
    notes = [f"low: note {n}" for n in range(24)]
    _record(ledger, "reviewer", "done", passed=False, findings=[*notes, "critical: secret leaked"])

    result = _verdict(ledger)

    assert result.findings[0] == "critical: secret leaked"
    assert len(result.findings) == review_gate.MAX_FINDINGS and result.overflow == 5
    assert "+5 lower-severity findings not shown" in review_gate.dod_review_outcome(result)[2]


def test_a_false_positive_is_overridden_with_a_reason() -> None:
    review = review_gate.ReviewVerdict("TASK-7", findings=("medium: style nit",))
    reason = "Reviewer flagged a style nit the project lint already accepts as intended."

    with _env(COS_VERIFY_OVERRIDE="1"):
        result = _complete(review, override_reason=reason)

    assert result.verdict is Verdict.WARN


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_the_package_carries_only_the_tasks_own_diff_and_criteria(tmp_path: Path) -> None:
    repo = tmp_path
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "T")
    (repo / "mine.py").write_text("x = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix: mine")
    mine = _git(repo, "rev-parse", "--short=10", "HEAD")
    (repo / "sibling.py").write_text("y = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: a sibling session's")
    (repo / "docs" / "tasks").mkdir(parents=True)
    (repo / "docs" / "tasks" / "TASK-7-demo.md").write_text(
        '---\ntitle: "fix: guard the cache"\n---\n\n'
        "## Outcome\nThe cache expires.\n\nQuoting commit abcdef1234 — must not count.\n\n"
        "## Acceptance (G/W/T)\n- **Given** a stale entry\n- **When** read\n- **Then** it reloads\n\n"
        f"## Work Log\n- 2026 [claude]: commit {mine} — fix: mine\n",
        encoding="utf-8",
    )

    package = review_gate.review_package("TASK-7", repo)

    assert package["task_title"] == "fix: guard the cache"
    assert package["task_outcome"] == "The cache expires."
    assert "**Given** a stale entry" in package["acceptance_criteria"]
    scope = package["review_scope"]
    assert scope["commits"] == [mine] and scope["files"] == ["mine.py"]
    assert "+x = 1" in scope["diff"] and "sibling.py" not in scope["diff"]


def test_a_task_without_linked_commits_gets_no_scope(tmp_path: Path) -> None:
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    (tmp_path / "docs" / "tasks" / "TASK-7-demo.md").write_text("## Outcome\nx\n", encoding="utf-8")

    assert "review_scope" not in review_gate.review_package("TASK-7", tmp_path)
    assert review_gate.review_package("TASK-404", tmp_path) == {}


def test_the_reviewer_prompt_maps_every_criterion_to_a_test() -> None:
    # The acceptance check lives in the reviewer's instructions; losing the
    # sentence would silently drop it from every review.
    prompt = (
        Path(__file__).resolve().parents[2] / "thinking_os" / "agents" / "reviewer.md"
    ).read_text(encoding="utf-8")
    assert "For every line of `acceptance_criteria`, name the test that covers it." in prompt
    assert "A criterion\nno test covers is a `medium` finding" in prompt
