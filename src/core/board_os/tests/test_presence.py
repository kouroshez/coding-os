"""session_inventory — sdk_uuid bridge exposure + poisoned-value sanitation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from board_os.presence import session_inventory


def _write_session(presence_dir: Path, sid: str, **fields) -> None:
    now = int(time.time())
    data = {
        "agent": "claude",
        "session_id": sid,
        "pid": 1,
        "started_at": now,
        "last_prompt_at": now,
        "last_tool_at": now,
        "last_stop_at": None,
        "ended_at": None,
        **fields,
    }
    (presence_dir / f"{sid}.json").write_text(json.dumps(data), encoding="utf-8")


def test_inventory_exposes_sdk_uuid_bridge(tmp_path: Path) -> None:
    _write_session(tmp_path, "ses-claude-1", sdk_uuid="f0a71515-dead-beef")
    rows = session_inventory("claude", tmp_path)
    assert rows[0]["sid"] == "ses-claude-1"
    assert rows[0]["sdk_uuid"] == "f0a71515-dead-beef"


def test_inventory_drops_path_poisoned_sdk_uuid(tmp_path: Path) -> None:
    """Files written before the presence-hook TSV fix hold a transcript PATH."""
    _write_session(tmp_path, "ses-claude-2", sdk_uuid="/Users/x/.claude/projects/t.jsonl")
    rows = session_inventory("claude", tmp_path)
    assert rows[0]["sdk_uuid"] is None


def test_inventory_null_sdk_uuid_stays_null(tmp_path: Path) -> None:
    _write_session(tmp_path, "ses-claude-3")
    rows = session_inventory("claude", tmp_path)
    assert rows[0]["sdk_uuid"] is None
