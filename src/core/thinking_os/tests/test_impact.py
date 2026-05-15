"""
Tests for impact scoring (digital amygdala) (TASK-157).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from impact import calculate_impact, calculate_pattern_impact


class TestCalculateImpact:
    def test_auth_file_high_impact(self) -> None:
        score = calculate_impact(file_path="backend/apps/auth/views.py")
        assert score >= 0.6

    def test_test_file_low_impact(self) -> None:
        score = calculate_impact(file_path="backend/apps/products/tests/test_models.py")
        assert score <= 0.5

    def test_migration_high_impact(self) -> None:
        score = calculate_impact(file_path="backend/apps/products/migrations/0001.py")
        assert score >= 0.6

    def test_settings_high_impact(self) -> None:
        score = calculate_impact(file_path="backend/settings/production.py")
        assert score >= 0.6

    def test_readme_low_impact(self) -> None:
        score = calculate_impact(file_path="README.md")
        assert score <= 0.5

    def test_rework_outcome_boosts(self) -> None:
        base = calculate_impact(file_path="some_file.py")
        rework = calculate_impact(file_path="some_file.py", outcome="rework")
        assert rework > base

    def test_blocked_outcome_boosts(self) -> None:
        base = calculate_impact(file_path="some_file.py")
        blocked = calculate_impact(file_path="some_file.py", outcome="blocked")
        assert blocked > base

    def test_success_outcome_no_boost(self) -> None:
        base = calculate_impact(file_path="some_file.py")
        success = calculate_impact(file_path="some_file.py", outcome="success")
        assert success == base

    def test_security_domain_boost(self) -> None:
        base = calculate_impact(file_path="some_file.py")
        sec = calculate_impact(file_path="some_file.py", domain="SECURITY")
        assert sec > base

    def test_bounded_0_to_1(self) -> None:
        # Extreme case: all high-impact signals
        score = calculate_impact(
            file_path="backend/auth/security/migration/models.py",
            domain="SECURITY",
            outcome="rework",
        )
        assert 0.0 <= score <= 1.0

    def test_minimum_floor(self) -> None:
        # Extreme low case
        score = calculate_impact(file_path="tests/test_mock_conftest.py")
        assert score >= 0.1


class TestPatternImpact:
    def test_average_of_scores(self) -> None:
        result = calculate_pattern_impact([0.8, 0.6, 0.4])
        assert result == pytest.approx(0.6)

    def test_empty_returns_default(self) -> None:
        assert calculate_pattern_impact([]) == 0.5

    def test_single_score(self) -> None:
        assert calculate_pattern_impact([0.9]) == 0.9
