"""Tests for the claude-sdk-integration check_model_ids.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "templates" / "meta" / "skills"
                       / "claude-sdk-integration" / "scripts"))

import check_model_ids as cm  # noqa: E402


def test_current_opus_clean() -> None:
    assert cm.scan_text('model = "claude-opus-4-8"', filename="ok.py") == []


def test_current_haiku_dated_clean() -> None:
    assert cm.scan_text('model = "claude-haiku-4-5-20251001"', filename="ok.py") == []


def test_stale_claude3_flagged() -> None:
    out = cm.scan_text('model = "claude-3-opus-20240229"', filename="x.py")
    assert any("stale model id" in f and "claude-opus-4-8" in f for f in out)


def test_stale_sonnet_suggests_current_sonnet() -> None:
    out = cm.scan_text('m = "claude-3-5-sonnet-20241022"', filename="x.py")
    assert any("claude-sonnet-4-6" in f for f in out)


def test_comment_ignored() -> None:
    assert cm.scan_text('# old: claude-3-opus-20240229', filename="x.py") == []
