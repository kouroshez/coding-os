"""Guards for /api/scheduled — TASK-834 hardening.

Locks the run-now env scrub (subprocess isolation) and next_run_at reading the
installed launchd hour rather than a hardcoded 3.
"""

from __future__ import annotations

import plistlib
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes import scheduled as sched


def _write_plist(path: Path, hour: int) -> None:
    path.write_bytes(
        plistlib.dumps({"StartCalendarInterval": {"Hour": hour, "Minute": 0}})
    )


def test_plist_hour_reads_installed_schedule(tmp_path, monkeypatch):
    plist = tmp_path / "nightly.plist"
    _write_plist(plist, 5)
    monkeypatch.setattr(sched, "_PLIST_DEST", plist)
    assert sched._plist_hour() == 5


def test_plist_hour_defaults_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sched, "_PLIST_DEST", tmp_path / "missing.plist")
    assert sched._plist_hour(default=3) == 3


def test_next_run_at_honors_plist_hour(tmp_path, monkeypatch):
    plist = tmp_path / "nightly.plist"
    _write_plist(plist, 5)
    monkeypatch.setattr(sched, "_PLIST_DEST", plist)
    iso = sched._next_run_at()
    assert iso is not None
    # The next fire is at the configured hour (5), never the old hardcoded 3.
    fires_at = datetime.fromisoformat(iso).astimezone().hour
    assert fires_at == 5


def test_clean_child_env_strips_scoping_overrides(monkeypatch):
    monkeypatch.setenv("COS_STATE_DIR", "/a/.coding-os")
    monkeypatch.setenv("COS_DB_PATH", "/a/.coding-os/coding-os.db")
    monkeypatch.setenv("COS_PROJECT_ROOT", "/a")
    monkeypatch.setenv("PATH", "/usr/bin")  # a non-scope var survives
    env = sched._clean_child_env()
    assert "COS_STATE_DIR" not in env
    assert "COS_DB_PATH" not in env
    assert "COS_PROJECT_ROOT" not in env
    assert env.get("PATH") == "/usr/bin"
