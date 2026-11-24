"""The audit block is English; the reply it asks for follows the user's language."""

from __future__ import annotations

from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "enforce-humanizer-audit.sh"


def test_the_block_message_keeps_the_users_language() -> None:
    # An English block message switched a Persian conversation to English twice.
    assert "in the language of the user's latest message" in HOOK.read_text(encoding="utf-8")
