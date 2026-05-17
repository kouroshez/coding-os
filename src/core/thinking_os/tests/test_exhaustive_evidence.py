"""Tests for ExhaustiveEvidence schema + validate_exhaustive_evidence (G3).

Lives next to existing cognition_schemas tests so the bundle-field +
predicate-validation contract is co-tested with the broader schema layer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Match the import style used by sibling tests (sys.path is already set up
# by conftest at thinking_os/conftest.py).
REPO_ROOT = Path(__file__).resolve().parents[3]
THINKING_OS = REPO_ROOT / "src" / "core" / "thinking_os"
if str(THINKING_OS) not in sys.path:
    sys.path.insert(0, str(THINKING_OS))

from cognition_schemas import (  # noqa: E402
    EvidenceBundle,
    ExhaustiveEvidence,
    validate_exhaustive_evidence,
)


def _full_evidence() -> ExhaustiveEvidence:
    return ExhaustiveEvidence(
        categories_declared=["imports", "symlinks", "hooks"],
        categories_covered=["imports", "symlinks", "hooks"],
        counts_before={"imports": 5, "symlinks": 2, "hooks": 1},
        counts_after={"imports": 0, "symlinks": 0, "hooks": 0},
        files_searched=["src/foo.py", "src/bar.py"],
        tests_run=["pytest tests/test_imports.py"],
        gaps_remaining=[],
        confidence=0.9,
        reviewer_check="pass",
        audit_artifact_path="docs/tasks/audits/audit-x.md",
    )


class TestExhaustiveEvidenceSchema:
    def test_defaults_are_empty(self) -> None:
        e = ExhaustiveEvidence()
        assert e.categories_declared == []
        assert e.categories_covered == []
        assert e.counts_before == {}
        assert e.counts_after == {}
        assert e.confidence == 0.0
        assert e.reviewer_check == "pending"
        assert e.audit_artifact_path is None

    def test_reviewer_check_literal_restricts_values(self) -> None:
        with pytest.raises(Exception):
            ExhaustiveEvidence(reviewer_check="approved")  # type: ignore[arg-type]

    def test_round_trip_json(self) -> None:
        e = _full_evidence()
        data = e.model_dump_json()
        restored = ExhaustiveEvidence.model_validate_json(data)
        assert restored == e


class TestEvidenceBundleField:
    def test_bundle_accepts_exhaustive_evidence(self) -> None:
        b = EvidenceBundle(
            task_marker="TASK-004",
            persona_id="implementer",
            exhaustive_evidence=_full_evidence(),
        )
        assert b.exhaustive_evidence is not None
        assert "imports" in b.exhaustive_evidence.categories_declared

    def test_bundle_default_field_is_none(self) -> None:
        b = EvidenceBundle(task_marker="t", persona_id="p")
        assert b.exhaustive_evidence is None


class TestValidatorEmptyPredicates:
    def test_empty_predicates_short_circuit_to_no_gaps(self) -> None:
        assert validate_exhaustive_evidence(None, []) == []
        assert validate_exhaustive_evidence(_full_evidence(), []) == []


class TestValidatorMissingEvidence:
    def test_predicates_present_but_no_evidence_is_gap(self) -> None:
        gaps = validate_exhaustive_evidence(None, ["coverage_100"])
        assert gaps == ["no_exhaustive_evidence_submitted"]


class TestValidatorCoverage100:
    def test_missing_categories_caught(self) -> None:
        e = ExhaustiveEvidence(
            categories_declared=["a", "b", "c"],
            categories_covered=["a"],
            counts_before={"a": 1, "b": 1, "c": 1},
            counts_after={"a": 0, "b": 0, "c": 0},
            reviewer_check="pass",
        )
        gaps = validate_exhaustive_evidence(e, ["coverage_100"])
        joined = " ".join(gaps)
        assert "coverage_100" in joined
        assert "'b'" in joined or "'c'" in joined

    def test_no_categories_declared_is_gap(self) -> None:
        e = ExhaustiveEvidence(reviewer_check="pass")
        gaps = validate_exhaustive_evidence(e, ["coverage_100"])
        assert any("no categories declared" in g for g in gaps)


class TestValidatorZeroResidual:
    def test_nonzero_counts_after_caught(self) -> None:
        e = ExhaustiveEvidence(
            categories_declared=["a"],
            categories_covered=["a"],
            counts_before={"a": 5},
            counts_after={"a": 2},
            files_searched=["x.py"],
            reviewer_check="pass",
        )
        gaps = validate_exhaustive_evidence(e, ["strict_zero_residual"])
        assert any("strict_zero_residual" in g and "residual" in g for g in gaps)

    def test_missing_counts_after_for_declared_caught(self) -> None:
        e = ExhaustiveEvidence(
            categories_declared=["a", "b"],
            categories_covered=["a", "b"],
            counts_before={"a": 1, "b": 1},
            counts_after={"a": 0},  # b missing
            files_searched=["x.py"],
            reviewer_check="pass",
        )
        gaps = validate_exhaustive_evidence(e, ["iterate_until_zero_residual"])
        assert any("no counts_after for b" in g for g in gaps)


class TestValidatorExhaustiveGrep:
    def test_empty_files_searched_caught(self) -> None:
        e = ExhaustiveEvidence(
            categories_declared=["a"],
            categories_covered=["a"],
            counts_before={"a": 0},
            counts_after={"a": 0},
            reviewer_check="pass",
        )
        gaps = validate_exhaustive_evidence(e, ["exhaustive_grep"])
        assert any("files_searched is empty" in g for g in gaps)


class TestValidatorReviewerCheck:
    def test_pending_reviewer_is_gap(self) -> None:
        e = _full_evidence()
        e.reviewer_check = "pending"
        gaps = validate_exhaustive_evidence(e, ["coverage_100"])
        assert any("reviewer_check: pending" in g for g in gaps)

    def test_failed_reviewer_is_gap(self) -> None:
        e = _full_evidence()
        e.reviewer_check = "fail"
        gaps = validate_exhaustive_evidence(e, ["coverage_100"])
        assert any("reviewer_check: failed" in g for g in gaps)


class TestValidatorAllPass:
    def test_fully_populated_evidence_returns_empty_gaps(self) -> None:
        gaps = validate_exhaustive_evidence(
            _full_evidence(),
            [
                "coverage_100",
                "iterate_until_zero_residual",
                "strict_zero_residual",
                "all_categories_evidence",
                "exhaustive_grep",
                "per_item_evidence",
            ],
        )
        assert gaps == []


class TestSelfReportedGaps:
    def test_evidence_self_reports_gaps(self) -> None:
        e = _full_evidence()
        e.gaps_remaining = ["category-x not yet swept"]
        gaps = validate_exhaustive_evidence(e, ["coverage_100"])
        assert any("self_reported_gaps" in g for g in gaps)
