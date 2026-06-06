"""Unit tests for the Stop-recap narrative template (TASK-182 / U1).

The recap is a deterministic, no-LLM line. _narrate turns the three session
counts into a plain-language accomplishment summary.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HELPER = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "core"
    / "hooks"
    / "_helpers"
    / "session_recap.py"
)
_spec = importlib.util.spec_from_file_location("session_recap", _HELPER)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_narrate = _mod._narrate


def test_insights_with_clean_run() -> None:
    assert _narrate(34, 0, 0) == "34 insights captured, clean run"


def test_singular_insight() -> None:
    assert _narrate(1, 0, 0) == "1 insight captured, clean run"


def test_backtracks_suppress_clean_run() -> None:
    assert _narrate(2, 1, 3) == "2 insights captured, 1 role step, 3 backtracks"


def test_empty_session() -> None:
    assert _narrate(0, 0, 0) == "no new cognitive activity this session"


def test_role_steps_only_no_clean_run() -> None:
    # disp-only with no insight: "clean run" would read oddly, so it is omitted.
    assert _narrate(0, 2, 0) == "2 role steps"


def test_plurals_and_clean_run() -> None:
    assert _narrate(3, 2, 0) == "3 insights captured, 2 role steps, clean run"


def test_backtracks_only() -> None:
    assert _narrate(0, 0, 2) == "2 backtracks"
