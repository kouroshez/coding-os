"""Tests for the llm-patterns estimate_tokens.py heuristic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "llm-patterns" / "scripts"))

import estimate_tokens as et  # noqa: E402


def test_empty_text() -> None:
    assert et.estimate("") == (0, 0, 0)


def test_low_le_mid_le_high() -> None:
    low, mid, high = et.estimate("the quick brown fox jumps over the lazy dog " * 20)
    assert low <= mid <= high


def test_scales_with_length() -> None:
    short = et.estimate("hello world")[1]
    long = et.estimate("hello world " * 100)[1]
    assert long > short


def test_brackets_realistic_range() -> None:
    # ~100 short words -> hundreds of tokens, not thousands
    low, mid, high = et.estimate("word " * 100)
    assert 100 <= mid <= 200
