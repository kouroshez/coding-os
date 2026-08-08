"""Tests for the incident-response classify_severity.py decision logic."""

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
        / "incident-response"
        / "scripts"
    ),
)

import classify_severity as cs


def _c(**kw) -> int:
    base = {
        "users_affected": 0.0,
        "data_loss": False,
        "security_breach": False,
        "core_down": False,
        "workaround": False,
    }
    base.update(kw)
    return cs.classify(**base)[0]


def test_data_loss_is_sev1() -> None:
    assert _c(data_loss=True) == 1


def test_security_breach_is_sev1() -> None:
    assert _c(security_breach=True, users_affected=1) == 1


def test_core_down_majority_no_workaround_sev1() -> None:
    assert _c(core_down=True, users_affected=80) == 1


def test_core_down_with_workaround_drops_to_sev3() -> None:
    assert _c(core_down=True, users_affected=80, workaround=True) == 3


def test_core_down_minority_sev2() -> None:
    assert _c(core_down=True, users_affected=10) == 2


def test_quarter_users_no_core_sev2() -> None:
    assert _c(users_affected=30) == 2


def test_minor_impact_sev3() -> None:
    assert _c(users_affected=5) == 3


def test_no_impact_sev4() -> None:
    assert _c() == 4
