"""Budget-capped autonomous repair loop — the verify-suite exit code is the fitness.

Flag-gated by COS_REPAIRER. Reuses the in-process SDK dispatcher + the daily/chain
budget gates + the board verify-suites — NO standalone binary, NO re-spawned claude
subprocess. The orchestration (this module) injects the suite runner + the dispatch
function so the loop is unit-testable without a real subprocess or API call.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

logger = logging.getLogger("thinking_os.repair")

DEFAULT_MAX_ATTEMPTS = 3
_VERIFY_SUITES = Path(__file__).resolve().parent.parent / "board_os" / "verify-suites.yaml"


@dataclass
class RepairResult:
    suite: str
    attempts: int
    repaired: bool
    final_exit_code: int
    reason: str = ""
    dispatched: bool = False


def verify_suite_command(suite: str) -> str | None:
    """Resolve a verify-suite name to its shell command (the fitness probe)."""
    try:
        import yaml

        data = yaml.safe_load(_VERIFY_SUITES.read_text(encoding="utf-8")) or {}
        entry = (data.get("suites") or {}).get(suite) or {}
        cmd = entry.get("command")
        return str(cmd) if cmd else None
    except Exception as exc:
        logger.debug("verify-suite lookup failed for %s: %s", suite, exc)
        return None


def _run_suite(command: str, cwd: str | None = None) -> int:
    try:
        proc = subprocess.run(command, shell=True, cwd=cwd, capture_output=True, timeout=1800)
        return proc.returncode
    except subprocess.TimeoutExpired:
        return 124
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("verify-suite run failed: %s", exc)
        return 1


def repair_loop(
    suite: str,
    command: str,
    *,
    dispatch_fn: Callable[[int], bool],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    cwd: str | None = None,
    run_suite: Callable[[str, str | None], int] = _run_suite,
) -> RepairResult:
    """Dispatch the repairer until the verify-suite passes (exit 0) or a cap is hit.

    Refuses (no-op) when the suite is already green — no churn. dispatch_fn(attempt)
    runs one in-process repairer dispatch and returns False to abort the loop (e.g.
    the budget gate denied it). Flag-gated by COS_REPAIRER.
    """
    if not os.environ.get("COS_REPAIRER"):
        return RepairResult(suite, 0, False, -1, reason="disabled")

    exit_code = run_suite(command, cwd)
    if exit_code == 0:
        return RepairResult(suite, 0, False, 0, reason="already-green")

    attempts = 0
    dispatched = False
    while exit_code != 0 and attempts < max_attempts:
        attempts += 1
        proceed = dispatch_fn(attempts)
        dispatched = True
        if not proceed:
            return RepairResult(
                suite,
                attempts,
                False,
                exit_code,
                reason="budget-or-dispatch-abort",
                dispatched=True,
            )
        exit_code = run_suite(command, cwd)

    return RepairResult(
        suite,
        attempts,
        exit_code == 0,
        exit_code,
        reason="repaired" if exit_code == 0 else "max-attempts",
        dispatched=dispatched,
    )
