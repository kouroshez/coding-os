"""The two guards that keep a published savings number defensible.

Both encode a defect the first harness shipped with: it scored an envelope whose
traversal had been capped (so a 508-caller answer stood in for a 1,494-caller one),
and it measured against a baseline that read every matching file end to end.
"""

from __future__ import annotations

import json
from pathlib import Path

from graph_os.bench._baselines import (
    Baseline,
    Corpus,
    baseline_characters,
    find_hits,
)
from graph_os.bench._coverage import (
    COMPLETE,
    COUNT_PLUS_SAMPLE,
    INCOMPLETE,
    read,
    resolve_complete,
)
from graph_os.bench._oracle import (
    BUCKET_NO_ORACLE,
    BUCKET_RESOLVABLE,
    MAX_ADJUDICATED_SITES,
    MAX_ORACLE_FILES,
    OracleResult,
    grade,
    score,
)


def _envelope(*, total: int, rows: int, walk_truncated: bool = False, tokens: int = 100) -> str:
    return json.dumps(
        {
            "ok": True,
            "data": {
                "total_count": total,
                "references": [{"i": i} for i in range(rows)],
                "meta": {
                    "tokens_estimated": tokens,
                    "walk_truncated": walk_truncated,
                    "result_truncated": rows < total,
                    "truncated": rows < total,
                },
            },
        }
    )


class TestCoverageGate:
    def test_capped_walk_is_never_scored(self) -> None:
        envelope = resolve_complete(
            lambda budget: _envelope(total=budget, rows=10, walk_truncated=True)
        )
        assert envelope.answer_shape == INCOMPLETE
        assert not envelope.scorable

    def test_growing_total_keeps_widening_until_it_settles(self) -> None:
        # 508 at the default cap, 1,494 once the walk can finish — the real defect.
        totals = {500: 508, 2_000: 1_494, 10_000: 1_494, 50_000: 1_494}
        seen: list[int] = []

        def call(budget: int) -> str:
            seen.append(budget)
            return _envelope(total=totals[budget], rows=60)

        envelope = resolve_complete(call)
        assert envelope.total_count == 1_494
        assert seen == [500, 2_000, 10_000]
        assert envelope.answer_shape == COUNT_PLUS_SAMPLE

    def test_settled_total_with_partial_rows_is_a_sample_not_a_failure(self) -> None:
        envelope = resolve_complete(lambda _budget: _envelope(total=96, rows=75))
        assert envelope.answer_shape == COUNT_PLUS_SAMPLE
        assert envelope.scorable

    def test_full_row_set_is_complete(self) -> None:
        envelope = resolve_complete(lambda _budget: _envelope(total=12, rows=12))
        assert envelope.answer_shape == COMPLETE

    def test_failed_call_is_never_scored_as_a_saving(self) -> None:
        # A fail() envelope has no `data`: 0 rows of 0 total, not truncated, and
        # the token floor of 1. That settles instantly and would publish ~100%.
        failure = json.dumps(
            {"ok": False, "error": {"category": "not_found", "message": "no such uid"}}
        )
        envelope = resolve_complete(lambda _budget: failure)
        assert envelope.answer_shape == INCOMPLETE
        assert not envelope.scorable

    def test_unparseable_response_is_never_scored(self) -> None:
        envelope = resolve_complete(lambda _budget: "not json at all")
        assert envelope.answer_shape == INCOMPLETE

    def test_budgetless_tool_is_called_once(self) -> None:
        calls: list[int] = []

        def call(budget: int) -> str:
            calls.append(budget)
            return _envelope(total=61, rows=61)

        assert resolve_complete(call, widens=False).answer_shape == COMPLETE
        assert len(calls) == 1


def _corpus(tmp_path: Path) -> Corpus:
    body = "\n".join(f"line {i}" for i in range(200))
    (tmp_path / "hot.py").write_text(
        f"def target():\n    pass\n{body}\ntarget()\n", encoding="utf-8"
    )
    (tmp_path / "cold.py").write_text(f"{body}\ntarget()\n", encoding="utf-8")
    return Corpus.load(sorted(tmp_path.glob("*.py")))


class TestBaselines:
    def test_cost_is_ordered_floor_to_ceiling(self, tmp_path: Path) -> None:
        corpus = _corpus(tmp_path)
        costs = {baseline: baseline_characters(corpus, "target", baseline) for baseline in Baseline}
        assert costs[Baseline.GREP_ONLY] < costs[Baseline.GREP_WINDOWS] < costs[Baseline.READ_ALL]

    def test_read_all_is_the_shape_that_inflates_savings(self, tmp_path: Path) -> None:
        corpus = _corpus(tmp_path)
        windows = baseline_characters(corpus, "target", Baseline.GREP_WINDOWS)
        read_all = baseline_characters(corpus, "target", Baseline.READ_ALL)
        assert read_all > windows * 2

    def test_hit_order_is_deterministic(self, tmp_path: Path) -> None:
        corpus = _corpus(tmp_path)
        first = [str(hit.document.path) for hit in find_hits(corpus, "target")]
        assert first == [str(hit.document.path) for hit in find_hits(corpus, "target")]
        assert first[0].endswith("hot.py")

    def test_absent_symbol_costs_nothing(self, tmp_path: Path) -> None:
        corpus = _corpus(tmp_path)
        assert baseline_characters(corpus, "no_such_symbol", Baseline.READ_ALL) == 0


class TestSiteExtraction:
    def test_source_span_becomes_a_comparable_location(self) -> None:
        envelope = json.dumps(
            {
                "ok": True,
                "data": {
                    "total_count": 2,
                    "references": [
                        {"source_span": "pkg/mod.py:12"},
                        {"source_span": "pkg/other.py:3"},
                    ],
                    "meta": {"tokens_estimated": 10},
                },
            }
        )
        assert read(envelope, budget=500).sites == {("pkg/mod.py", 12), ("pkg/other.py", 3)}

    def test_a_span_without_a_line_is_dropped_not_guessed(self) -> None:
        envelope = json.dumps(
            {
                "ok": True,
                "data": {
                    "total_count": 2,
                    "references": [{"source_span": "pkg/mod.py"}, {"source_span": "x:notaline"}],
                    "meta": {"tokens_estimated": 10},
                },
            }
        )
        assert read(envelope, budget=500).sites == frozenset()

    def test_a_windows_style_path_keeps_its_drive_letter(self) -> None:
        envelope = json.dumps(
            {
                "ok": True,
                "data": {
                    "total_count": 1,
                    "references": [{"source_span": "C:/pkg/mod.py:7"}],
                    "meta": {"tokens_estimated": 10},
                },
            }
        )
        assert read(envelope, budget=500).sites == {("C:/pkg/mod.py", 7)}

    def test_sites_survive_the_widening_ladder(self) -> None:
        envelope = json.dumps(
            {
                "ok": True,
                "data": {
                    "total_count": 1,
                    "references": [{"source_span": "pkg/mod.py:5"}],
                    "meta": {"tokens_estimated": 10},
                },
            }
        )
        assert resolve_complete(lambda _b: envelope).sites == {("pkg/mod.py", 5)}


class TestOracleScoring:
    def test_an_unavailable_oracle_scores_nothing_rather_than_zero(self) -> None:
        graph = frozenset({("a.py", 1), ("b.py", 2)})
        result = score(graph, OracleResult(note="jedi not installed"))
        assert result["bucket"] == BUCKET_NO_ORACLE
        assert result["recall"] is None
        assert result["precision"] is None
        # The graph's own count is still reported — it is knowable without jedi.
        assert result["graph_sites"] == 2

    def test_truth_unions_what_either_side_found(self) -> None:
        oracle = OracleResult(
            enumerated=frozenset({("a.py", 1)}),
            confirmed=frozenset({("b.py", 2)}),
            bucket=BUCKET_RESOLVABLE,
        )
        assert oracle.truth == {("a.py", 1), ("b.py", 2)}

    def test_recall_counts_a_site_jedi_enumerated_and_the_graph_missed(self) -> None:
        graph = frozenset({("b.py", 2)})
        oracle = OracleResult(
            enumerated=frozenset({("a.py", 1), ("b.py", 2)}),
            confirmed=frozenset({("b.py", 2)}),
            bucket=BUCKET_RESOLVABLE,
        )
        result = score(graph, oracle)
        assert result["oracle_sites"] == 2
        assert result["matched_sites"] == 1
        assert result["recall"] == 0.5
        assert result["precision"] == 1.0

    def test_a_refuted_claim_lowers_precision_without_touching_recall(self) -> None:
        graph = frozenset({("a.py", 1), ("ghost.py", 9)})
        oracle = OracleResult(
            enumerated=frozenset({("a.py", 1)}),
            confirmed=frozenset({("a.py", 1)}),
            refuted=frozenset({("ghost.py", 9)}),
            bucket=BUCKET_RESOLVABLE,
        )
        result = score(graph, oracle)
        assert result["precision"] == 0.5
        assert result["recall"] == 1.0

    def test_a_hub_past_the_adjudication_cap_declines_instead_of_sampling(self) -> None:
        sites = frozenset((f"f{i}.py", i) for i in range(MAX_ADJUDICATED_SITES + 1))
        result = grade(Path("/nonexistent"), "x.py", 1, "X", sites, file_count=10)
        assert result.bucket == BUCKET_NO_ORACLE
        assert "cap" in result.note

    def test_a_repo_past_the_file_cap_declines(self) -> None:
        result = grade(
            Path("/nonexistent"), "x.py", 1, "X", frozenset(), file_count=MAX_ORACLE_FILES + 1
        )
        assert result.bucket == BUCKET_NO_ORACLE
        assert "files" in result.note
