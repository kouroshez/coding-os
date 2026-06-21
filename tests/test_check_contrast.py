"""Tests for the frontend-design check_contrast.py WCAG calculator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / "src"
        / "core"
        / "skills"
        / "frontend-design"
        / "scripts"
    ),
)

import check_contrast as cc  # noqa: E402


def test_black_on_white_is_max() -> None:
    ratio = cc.contrast_ratio((0, 0, 0), (255, 255, 255))
    assert abs(ratio - 21.0) < 0.1


def test_white_on_white_is_min() -> None:
    assert abs(cc.contrast_ratio((255, 255, 255), (255, 255, 255)) - 1.0) < 0.01


def test_symmetric() -> None:
    a = cc.contrast_ratio((20, 20, 20), (200, 200, 200))
    b = cc.contrast_ratio((200, 200, 200), (20, 20, 20))
    assert abs(a - b) < 1e-9


def test_parse_hex_short_and_long() -> None:
    assert cc.parse_color("#fff") == (255, 255, 255)
    assert cc.parse_color("#1a1a1a") == (26, 26, 26)


def test_parse_rgb_tuple() -> None:
    assert cc.parse_color("37, 99, 235") == (37, 99, 235)


def test_parse_bad_color_raises() -> None:
    with pytest.raises(ValueError):
        cc.parse_color("#xyz")


def test_main_pass_fail(capsys) -> None:
    assert cc.main(["#000000", "#ffffff"]) == 0  # AA passes
    assert cc.main(["#777777", "#888888"]) == 1  # fails AA
