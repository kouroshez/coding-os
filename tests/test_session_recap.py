"""Unit tests for the Stop-recap narrative template (TASK-182 / U1).

The recap is a deterministic, no-LLM line. _narrate turns the session's dispatch
count into a plain-language summary.
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


def test_one_role_step() -> None:
    assert _narrate(1) == "1 role step"


def test_empty_session() -> None:
    assert _narrate(0) == "no new cognitive activity this session"


def test_role_steps_only() -> None:
    assert _narrate(2) == "2 role steps"
