"""Shell→log_events durable bridge (audit-2026-06 F8, TASK-447).

cos_say_json.py (the single shell→DB writer cos_say + cos_log_hook share) must
land a hook BLOCK / WARN in the SQLite log_events store the logging_os sink owns,
so cos_log_query / error_sweep surface it — not only the text/jsonl tail. Below
the configured floor it must NOT touch the store (the hot info/ok path).

Subprocess-light (init_db + a couple bash/python spawns). Run:
  uv run --extra rag pytest tests/test_cos_say_db_bridge.py -q
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "src" / "core" / "hooks" / "_helpers" / "cos_say_json.py"
_COS_ENV = _REPO / "src" / "core" / "hooks" / "cos-env.sh"


def _migrated_db(tmp_path: Path) -> Path:
    try:
        from core.thinking_os.database import init_db
    except ImportError:
        sys.path.insert(0, str(_REPO / "src" / "core" / "thinking_os"))
        from thinking_os.database import init_db
    db = tmp_path / "coding-os.db"
    init_db(db).close()
    return db


def _rows(db: Path) -> list[tuple]:
    return (
        sqlite3.connect(str(db))
        .execute("SELECT lvl, scope, msg, kv, session_id FROM log_events ORDER BY id")
        .fetchall()
    )


def test_helper_persists_warn_plus_and_skips_below_floor(tmp_path: Path) -> None:
    db = _migrated_db(tmp_path)
    env = {"COS_DB_PATH": str(db), "COS_LOG_DB_MIN_LEVEL": "WARN", "PATH": _env_path()}

    subprocess.run(
        [sys.executable, str(_HELPER), "2026-06-18T00:00:00Z", "ERROR",
         "hook.demo", "blocked by demo", "action=block session=sX task=T9"],
        env=env, stdout=subprocess.DEVNULL, check=True,
    )
    rows = _rows(db)
    assert len(rows) == 1, "ERROR must persist exactly one durable row"
    lvl, scope, _msg, kv, session = rows[0]
    assert lvl == "ERROR" and scope == "hook.demo"
    assert session == "sX", "session= from kv lands in session_id"
    assert kv and "block" in kv, "kv blob lands in the kv column"

    subprocess.run(
        [sys.executable, str(_HELPER), "2026-06-18T00:00:01Z", "INFO", "hook.demo", "chatter", ""],
        env=env, stdout=subprocess.DEVNULL, check=True,
    )
    assert len(_rows(db)) == 1, "below-floor INFO must NOT touch the durable store"


def test_cos_log_hook_block_lands_in_log_events(tmp_path: Path) -> None:
    db = _migrated_db(tmp_path)
    env = {
        "COS_DB_PATH": str(db),
        "COS_LOG_DB_MIN_LEVEL": "WARN",
        "COS_STATE_DIR": str(tmp_path),
        "PATH": _env_path(),
    }
    script = (
        f'source "{_COS_ENV}" 2>/dev/null || true; '
        'cos_log_hook block-secrets block "rule=demo-secret"'
    )
    subprocess.run(["bash", "-c", script], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    block_rows = [r for r in _rows(db) if r[1] == "hook.block-secrets"]
    assert block_rows, "a hook BLOCK must be durable in log_events for cos_log_query"
    assert block_rows[0][0] == "ERROR"
    assert "block" in (block_rows[0][3] or ""), "action=block recorded in kv"


def _env_path() -> str:
    import os

    return os.environ.get("PATH", "/usr/bin:/bin")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
