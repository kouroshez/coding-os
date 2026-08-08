"""Tests for the testing-strategy coverage_gate.py parsers."""

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
        / "testing-strategy"
        / "scripts"
    ),
)

import coverage_gate as cg


def test_coveragepy_json() -> None:
    assert cg.percent_from_coveragepy('{"totals": {"percent_covered": 87.5}}') == 87.5


def test_cobertura_xml() -> None:
    xml = '<?xml version="1.0"?><coverage line-rate="0.823"></coverage>'
    assert abs(cg.percent_from_cobertura(xml) - 82.3) < 0.01


def test_cobertura_missing_rate_raises() -> None:
    with pytest.raises(ValueError):
        cg.percent_from_cobertura("<coverage></coverage>")


def test_gate_pass(tmp_path: Path) -> None:
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {"percent_covered": 90}}', encoding="utf-8")
    assert cg.main([str(p), "--min", "80"]) == 0


def test_gate_fail(tmp_path: Path) -> None:
    p = tmp_path / "coverage.json"
    p.write_text('{"totals": {"percent_covered": 70}}', encoding="utf-8")
    assert cg.main([str(p), "--min", "80"]) == 1
