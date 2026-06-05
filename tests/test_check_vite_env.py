"""Tests for the react-vite-hub check_vite_env.py."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "templates" / "meta" / "skills"
                       / "react-vite-hub" / "scripts"))

import check_vite_env as cve  # noqa: E402


def test_vite_prefixed_clean() -> None:
    assert cve.scan_text("const url = import.meta.env.VITE_API_URL;", filename="ok.ts") == []


def test_builtin_env_clean() -> None:
    assert cve.scan_text("if (import.meta.env.DEV) {}", filename="ok.ts") == []


def test_process_env_flagged() -> None:
    assert any("process.env" in f for f in cve.scan_text("const k = process.env.API_KEY;", filename="x.ts"))


def test_non_vite_meta_env_flagged() -> None:
    out = cve.scan_text("const x = import.meta.env.API_URL;", filename="x.ts")
    assert any("not VITE_-prefixed" in f for f in out)


def test_comment_ignored() -> None:
    assert cve.scan_text("// process.env.X", filename="x.ts") == []
