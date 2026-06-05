"""Tests for the agent-memory check_observation.py validator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "agent-memory" / "scripts"))

import check_observation as co  # noqa: E402


def _obs(**kw) -> dict:
    base = {"type": "error", "summary": "migration needed a backfill first",
            "confidence": 0.5, "impact": 0.6}
    base.update(kw)
    return base


def test_valid_observation_ok() -> None:
    assert co.validate(_obs()) == []


def test_bad_type_flagged() -> None:
    assert any("type must be" in i for i in co.validate(_obs(type="random")))


def test_short_summary_flagged() -> None:
    assert any("summary" in i for i in co.validate(_obs(summary="x")))


def test_confidence_out_of_range_flagged() -> None:
    assert any("confidence" in i for i in co.validate(_obs(confidence=1.5)))


def test_pii_email_flagged() -> None:
    assert any("PII" in i for i in co.validate(_obs(summary="user jane@example.com hit the bug")))


def test_secret_flagged() -> None:
    assert any("secret" in i for i in co.validate(_obs(summary="set api_key=abc123 to fix it ok")))


def test_missing_confidence_flagged() -> None:
    obs = _obs()
    del obs["confidence"]
    assert any("confidence missing" in i for i in co.validate(obs))
