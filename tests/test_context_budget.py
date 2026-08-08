"""context_budget.last_context_tokens — compaction-boundary awareness.

Guards the bug where the ctx=Nk>200k banner marker reported the stale
pre-compact usage total on the first prompt after /compact (TASK-580).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

import context_budget


def _usage(total: int) -> dict:
    return {"type": "assistant", "message": {"usage": {"input_tokens": total}}}


def _write(tmp_path: Path, records: list[dict]) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return str(path)


def test_usage_after_compact_is_reported(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _usage(516_000),
            {"type": "system", "subtype": "compact_boundary"},
            {"type": "user", "isCompactSummary": True, "message": {"content": "summary"}},
            _usage(110_000),
        ],
    )
    assert context_budget.last_context_tokens(path) == 110_000


def test_compact_boundary_suppresses_stale_pre_compact_total(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _usage(516_000),
            {"type": "system", "subtype": "compact_boundary"},
            {"type": "user", "message": {"content": "next prompt"}},
        ],
    )
    assert context_budget.last_context_tokens(path) == 0


def test_compact_summary_record_alone_suppresses(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _usage(516_000),
            {"type": "user", "isCompactSummary": True, "message": {"content": "summary"}},
            {"type": "user", "message": {"content": "next prompt"}},
        ],
    )
    assert context_budget.last_context_tokens(path) == 0


def test_message_mentioning_marker_text_is_not_a_boundary(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            _usage(516_000),
            {
                "type": "user",
                "message": {"content": "why does compact_boundary / isCompactSummary do this?"},
            },
        ],
    )
    assert context_budget.last_context_tokens(path) == 516_000


def test_sums_all_three_token_fields(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "type": "assistant",
                "message": {
                    "usage": {
                        "input_tokens": 100,
                        "cache_creation_input_tokens": 200,
                        "cache_read_input_tokens": 300,
                    }
                },
            }
        ],
    )
    assert context_budget.last_context_tokens(path) == 600
