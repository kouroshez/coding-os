"""Tests for the exhaustive-intent classifier (TASK-004 Phase P Group 1).

Covers _helpers/extract_intent.py and detect-exhaustive-intent.sh.

Source of truth for vocabulary: docs/engineering/intent-vocabulary.md.
The mirror in extract_intent.py is the live SSOT for runtime — these
tests pin the contract that the parser honors the doc.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HELPER = REPO_ROOT / "src" / "core" / "hooks" / "_helpers" / "extract_intent.py"
HOOK = REPO_ROOT / "src" / "core" / "hooks" / "detect-exhaustive-intent.sh"


def _run_helper(prompt: str) -> dict:
    payload = json.dumps({"prompt": prompt})
    proc = subprocess.run(
        [sys.executable, str(HELPER)],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=5,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    return json.loads(proc.stdout.decode("utf-8"))


def _run_hook(prompt: str) -> tuple[int, str, str]:
    payload = json.dumps({"prompt": prompt})
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload.encode("utf-8"),
        capture_output=True,
        timeout=5,
    )
    return proc.returncode, proc.stdout.decode("utf-8"), proc.stderr.decode("utf-8")


class TestExhaustiveEnglish:
    def test_all_with_scope_verb_triggers(self) -> None:
        result = _run_helper("rename all callers of foo")
        assert result["exhaustive"] is True
        assert "all" in result["matched_exhaustive"]
        assert "rename" in result["matched_scope"]
        assert "coverage_100" in result["predicates"]

    def test_completely_with_fix_triggers(self) -> None:
        result = _run_helper("fix completely the broken imports")
        assert result["exhaustive"] is True
        assert "completely" in result["matched_exhaustive"]
        assert "strict_zero_residual" in result["predicates"]

    def test_until_done_with_iterate(self) -> None:
        result = _run_helper("fix until done")
        assert result["exhaustive"] is True
        assert "iterate_until_zero_residual" in result["predicates"]

    def test_down_to_the_last_one_with_audit(self) -> None:
        result = _run_helper("audit the codebase down to the last one")
        assert result["exhaustive"] is True
        assert "down to the last one" in result["matched_exhaustive"]
        assert "strict_zero_residual" in result["predicates"]


class TestExhaustivePersian:
    def test_hame_with_fix_triggers(self) -> None:
        result = _run_helper("fix همه the broken hooks")
        assert result["exhaustive"] is True
        assert "همه" in result["matched_exhaustive"]
        assert "coverage_100" in result["predicates"]

    def test_ta_doone_akhar_full_fa(self) -> None:
        result = _run_helper("تا دونه آخر فیکس کن این رو")
        assert result["exhaustive"] is True
        assert "تا دونه آخر" in result["matched_exhaustive"]
        assert "فیکس" in result["matched_scope"]
        assert "iterate_until_zero_residual" in result["predicates"]
        assert "strict_zero_residual" in result["predicates"]

    def test_kamel_with_audit(self) -> None:
        result = _run_helper("audit بکن کامل پروژه رو")
        assert result["exhaustive"] is True
        assert "کامل" in result["matched_exhaustive"]
        assert "all_categories_evidence" in result["predicates"]


class TestFalsePositives:
    def test_all_good_without_scope_verb(self) -> None:
        result = _run_helper("all good thanks")
        assert result["exhaustive"] is False

    def test_find_singular_no_exhaustive(self) -> None:
        result = _run_helper("find me one example")
        assert result["exhaustive"] is False
        assert "find" in result["matched_scope"]

    def test_empty_prompt(self) -> None:
        result = _run_helper("")
        assert result["exhaustive"] is False
        assert result["token_count"] == 0


class TestWindowConstraint:
    def test_exhaustive_far_from_scope_does_not_trigger(self) -> None:
        # 'all' at position 0, 'fix' at position 25 (>20 token window).
        # 'completely' must NOT appear or it would co-occur with 'fix'.
        far_prompt = (
            "all of this is good and i agree mostly with you that "
            "the design is sound but separately later on can you "
            "now look at and fix the typo"
        )
        result = _run_helper(far_prompt)
        assert result["exhaustive"] is False

    def test_exhaustive_within_window_triggers(self) -> None:
        result = _run_helper("fix all the failing tests")
        assert result["exhaustive"] is True


class TestPredicateUnion:
    def test_multiple_exhaustive_verbs_union_predicates(self) -> None:
        result = _run_helper("rename all callers completely")
        assert result["exhaustive"] is True
        # 'all' contributes coverage_100, iterate_until_zero_residual
        # 'completely' contributes all_categories_evidence, strict_zero_residual
        for predicate in (
            "coverage_100",
            "iterate_until_zero_residual",
            "all_categories_evidence",
            "strict_zero_residual",
        ):
            assert predicate in result["predicates"], predicate


class TestHookEnvelope:
    def test_exhaustive_prompt_emits_envelope(self) -> None:
        code, stdout, _ = _run_hook("fix همه the broken hooks please")
        assert code == 0
        payload = json.loads(stdout)
        assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        ctx = payload["hookSpecificOutput"]["additionalContext"]
        assert "Intent: exhaustive detected" in ctx
        assert "Evidence-required mode active" in ctx
        assert "intent-vocabulary.md" in ctx

    def test_non_exhaustive_prompt_silent(self) -> None:
        code, stdout, _ = _run_hook("hello, just saying hi")
        assert code == 0
        assert stdout == ""

    def test_short_prompt_skipped(self) -> None:
        code, stdout, _ = _run_hook("hi")
        assert code == 0
        assert stdout == ""


class TestSchemaShape:
    def test_result_has_all_required_keys(self) -> None:
        result = _run_helper("fix all the bugs")
        for key in (
            "exhaustive",
            "matched_exhaustive",
            "matched_scope",
            "predicates",
            "prompt_length",
            "token_count",
            "detected_at",
        ):
            assert key in result, key

    def test_detected_at_is_iso_utc(self) -> None:
        result = _run_helper("rename all functions")
        assert result["detected_at"].endswith("Z")
        assert "T" in result["detected_at"]


@pytest.mark.parametrize(
    "verb",
    [
        "all", "every", "everything", "everywhere", "completely",
        "comprehensive", "exhaustive", "thoroughly", "100%",
    ],
)
def test_each_en_exhaustive_verb_recognized(verb: str) -> None:
    result = _run_helper(f"fix {verb} broken")
    assert result["exhaustive"] is True, verb
    assert verb in result["matched_exhaustive"], verb


@pytest.mark.parametrize(
    "verb",
    [
        "همه", "همگی", "کامل", "صد در صد", "هیچی نپره",
        "بدون استثنا", "تمام",
    ],
)
def test_each_fa_exhaustive_verb_recognized(verb: str) -> None:
    result = _run_helper(f"فیکس {verb} این")
    assert result["exhaustive"] is True, verb
    assert verb in result["matched_exhaustive"], verb
