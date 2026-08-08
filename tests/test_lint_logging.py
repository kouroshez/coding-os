"""Tests for the observability lint_logging.py hygiene linter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "core"
        / "skills"
        / "observability"
        / "scripts"
    ),
)

import lint_logging as ll


def test_structured_log_clean() -> None:
    assert ll.scan_text('logger.info("evt", extra={"user_id": uid})', filename="ok.py") == []


def test_print_flagged() -> None:
    assert any("print()" in f for f in ll.scan_text("print('hi')", filename="x.py"))


def test_console_log_flagged() -> None:
    assert any("console.log" in f for f in ll.scan_text("console.log('x')", filename="x.ts"))


def test_pii_in_log_flagged() -> None:
    out = ll.scan_text('logger.info("login", password=pw)', filename="x.py")
    assert any("PII" in f for f in out)


def test_fstring_in_log_flagged() -> None:
    out = ll.scan_text('logger.info(f"user {uid}")', filename="x.py")
    assert any("f-string" in f for f in out)


def test_comment_ignored() -> None:
    assert ll.scan_text("# print('debug')", filename="x.py") == []
