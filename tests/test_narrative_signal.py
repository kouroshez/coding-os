"""Unit coverage for the narrative-signal helper used by nudge-learn-narrative.sh.

Verifies the signal gate: emit a reason on rework churn (a file edited >=3x),
stay silent otherwise. This is what keeps the Stop nudge from firing on trivial
sessions. Contract: docs/engineering/learning-extraction.md (C path).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_HELPER = _ROOT / "src" / "core" / "hooks" / "_helpers" / "narrative_signal.py"
sys.path.insert(0, str(_ROOT / "src" / "core" / "thinking_os"))

from database import init_db

_OBS = (
    "INSERT INTO observations (session_id, tool_name, observation_type, memory_type, "
    "impact_score, title, narrative, content_hash, files_modified) "
    "VALUES (?, 'Edit', 'edit', 'discovery', 0.5, 't', 'n', ?, ?)"
)


def _run(db: Path, session: str) -> str:
    r = subprocess.run(
        [sys.executable, str(_HELPER), str(db), session],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return r.stdout.strip()


def test_rework_churn_emits_signal(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    c = init_db(db)
    for i in range(3):
        c.execute(_OBS, ("ses-1", f"h{i}", "/r/hot.py"))
    c.commit()
    c.close()
    out = _run(db, "ses-1")
    assert "hot.py" in out and "3x" in out


def test_no_churn_is_silent(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    c = init_db(db)
    c.execute(_OBS, ("ses-2", "h1", "/r/a.py"))
    c.execute(_OBS, ("ses-2", "h2", "/r/b.py"))
    c.commit()
    c.close()
    assert _run(db, "ses-2") == ""


def test_missing_db_is_silent(tmp_path: Path) -> None:
    assert _run(tmp_path / "nope.db", "ses-x") == ""
