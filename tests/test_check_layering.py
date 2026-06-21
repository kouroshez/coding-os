"""Tests for the backend-fundamentals check_layering.py."""

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
        / "backend-fundamentals"
        / "scripts"
    ),
)

import check_layering as cl  # noqa: E402


def test_clean_service_passes() -> None:
    code = "def apply_discount(price, pct):\n    return price * (1 - pct)\n"
    assert cl.scan_text(code, filename="service.py") == []


def test_fastapi_import_flagged() -> None:
    out = cl.scan_text("from fastapi import APIRouter\n", filename="service.py")
    assert any("web framework" in f for f in out)


def test_orm_import_flagged() -> None:
    out = cl.scan_text("import sqlalchemy\n", filename="domain.py")
    assert any("ORM/driver" in f for f in out)


def test_express_require_flagged() -> None:
    out = cl.scan_text("const express = require('express')\n", filename="service.js")
    assert any("Express" in f for f in out)


def test_comment_ignored() -> None:
    assert cl.scan_text("# from fastapi import x\n", filename="service.py") == []
