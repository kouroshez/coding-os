"""
Tests for sanitizer.py — injection detection, length capping, audit wiring.

Brain hardening. Every write path into agent memory (observations,
learned_patterns, outcome_history narratives) must route through
`sanitize_write` before the INSERT. These tests pin the contract.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import init_db
from sanitizer import (
    scrub_username,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> sqlite3.Connection:
    conn = init_db(tmp_path / "test.db")
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Injection detection — true positives
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Injection detection — true negatives (legitimate code/doc text)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# sanitize_write — happy path
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# sanitize_write — length cap
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# sanitize_write — reject path
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# sanitize_write — secret / PII redaction
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Audit wiring — fire-and-forget contract
# ---------------------------------------------------------------------------


class TestScrubUsername:
    """The OS username is PII (memory.md § Privacy). scrub_username is the SSOT,
    folded into sanitize_write so every memory write is username-safe."""

    def test_home_prefix_becomes_tilde(self) -> None:
        out = scrub_username(f"{Path.home()}/secret/file.py")
        assert out == "~/secret/file.py"
        assert Path.home().name not in out

    def test_dash_encoded_home_scrubbed(self) -> None:
        dash = str(Path.home()).replace("/", "-")  # /Users/<u> -> -Users-<u>
        out = scrub_username(f"~/.claude/projects/{dash}-Files-x/m.md")
        assert Path.home().name not in out
        assert dash not in out

    def test_no_home_no_change(self) -> None:
        assert scrub_username("/tmp/foo.py") == "/tmp/foo.py"
        assert scrub_username("") == ""

    def test_bare_home_no_trailing_slash_scrubbed(self) -> None:
        # Regression (verification audit): a path that TERMINATES at $HOME, or is
        # followed by a non-slash char, leaked the username (only h+'/' was replaced).
        assert scrub_username("/Users/alice", home="/Users/alice") == "~"
        assert scrub_username("failed at /Users/alice", home="/Users/alice") == "failed at ~"
        assert scrub_username("/Users/alice.bak", home="/Users/alice") == "~.bak"
        assert "alice" not in scrub_username("see /Users/alice now", home="/Users/alice")

    def test_does_not_mangle_extending_username(self) -> None:
        # A DIFFERENT user whose name extends home's must be left intact.
        assert scrub_username("/Users/alice2/x.py", home="/Users/alice") == "/Users/alice2/x.py"
