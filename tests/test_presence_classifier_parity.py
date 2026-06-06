"""Parity between the two presence surfaces (TASK-190).

web/routes/sessions.py now delegates its core verdict to the single
board_os.presence SSOT, only refining its `offline` into the dashboard's
`ended`/`idle`. So the two never contradict each other.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.board_os import presence
from core.web.routes import sessions

NOW = 1_000_000
ALIVE = os.getpid()
DEAD = 999_999_999


def test_active_agrees():
    p = {"last_tool_at": NOW - 5, "pid": ALIVE}
    assert presence.session_presence(p, NOW) == "active"
    assert sessions._classify(p, NOW) == "active"


def test_present_agrees():
    p = {"last_tool_at": NOW - 600, "pid": ALIVE}
    assert presence.session_presence(p, NOW) == "present"
    assert sessions._classify(p, NOW) == "present"


def test_working_maps_to_active_lifecycle():
    p = {"last_prompt_at": NOW - 600, "pid": ALIVE}
    assert presence.session_presence(p, NOW) == "working"
    assert sessions._classify(p, NOW) == "active"


def test_ended_refines_board_offline():
    p = {"ended_at": NOW - 1, "pid": ALIVE}
    assert presence.session_presence(p, NOW) == "offline"
    assert sessions._classify(p, NOW) == "ended"


def test_idle_refines_board_offline_when_alive():
    p = {"last_tool_at": NOW - 99999, "last_prompt_at": NOW - 99999, "started_at": NOW - 99999, "pid": ALIVE}
    assert presence.session_presence(p, NOW) == "offline"
    assert sessions._classify(p, NOW) == "idle"


def test_offline_when_pid_dead():
    p = {"last_tool_at": NOW - 99999, "pid": DEAD}
    assert presence.session_presence(p, NOW) == "offline"
    assert sessions._classify(p, NOW) == "offline"
