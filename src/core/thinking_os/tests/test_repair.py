"""TASK-642 autonomous repairer: budget-capped repair loop, verify-suite exit code as fitness."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import repair


def test_disabled_when_flag_off(monkeypatch) -> None:
    monkeypatch.delenv("COS_REPAIRER", raising=False)
    calls: list[int] = []
    r = repair.repair_loop(
        "s", "cmd", dispatch_fn=lambda a: calls.append(a) or True, run_suite=lambda c, w: 1
    )
    assert r.reason == "disabled" and not r.dispatched and calls == []


def test_already_green_is_no_op(monkeypatch) -> None:
    monkeypatch.setenv("COS_REPAIRER", "1")
    calls: list[int] = []
    r = repair.repair_loop(
        "s", "cmd", dispatch_fn=lambda a: calls.append(a) or True, run_suite=lambda c, w: 0
    )
    assert r.reason == "already-green" and r.attempts == 0 and not r.dispatched and calls == []


def test_repairs_when_suite_goes_green(monkeypatch) -> None:
    monkeypatch.setenv("COS_REPAIRER", "1")
    seq = iter([1, 1, 0])  # initial fail, fail after attempt 1, pass after attempt 2
    r = repair.repair_loop(
        "s", "cmd", dispatch_fn=lambda a: True, run_suite=lambda c, w: next(seq), max_attempts=5
    )
    assert r.repaired and r.reason == "repaired" and r.attempts == 2 and r.dispatched


def test_stops_at_max_attempts(monkeypatch) -> None:
    monkeypatch.setenv("COS_REPAIRER", "1")
    r = repair.repair_loop(
        "s", "cmd", dispatch_fn=lambda a: True, run_suite=lambda c, w: 1, max_attempts=3
    )
    assert not r.repaired and r.reason == "max-attempts" and r.attempts == 3


def test_aborts_on_budget_denied(monkeypatch) -> None:
    monkeypatch.setenv("COS_REPAIRER", "1")
    r = repair.repair_loop("s", "cmd", dispatch_fn=lambda a: False, run_suite=lambda c, w: 1)
    assert not r.repaired and r.reason == "budget-or-dispatch-abort" and r.attempts == 1


def test_verify_suite_command_resolves_known_suite() -> None:
    cmd = repair.verify_suite_command("test-thinking_os")
    assert cmd and "pytest" in cmd
    assert repair.verify_suite_command("no-such-suite") is None
