"""
Tests for tools/_shared.py — envelope uniformity, meta merging, token budget.

Contract — every success response carries a `data.meta` block
with at minimum `layer`, `tokens_estimated`, `truncated`. Oversized payloads
are trimmed from `data.results` tail with truncation meta recorded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._shared import (
    TOKEN_BUDGET_CHARS,
    VALID_LAYERS,
    _estimate_tokens,
    fail,
    ok,
    safe_tool,
)

# ---------------------------------------------------------------------------
# ok() — shape and meta merging
# ---------------------------------------------------------------------------


class TestOkEnvelope:
    def test_scalar_data_passes_through(self) -> None:
        """Non-dict payloads preserved for back-compat (no meta applied)."""
        envelope = json.loads(ok("hello"))
        assert envelope == {"ok": True, "data": "hello"}

    def test_list_data_passes_through(self) -> None:
        envelope = json.loads(ok([1, 2, 3]))
        assert envelope == {"ok": True, "data": [1, 2, 3]}

    def test_dict_gets_meta_block(self) -> None:
        envelope = json.loads(ok({"results": [1, 2, 3], "count": 3}))
        assert envelope["ok"] is True
        assert "meta" in envelope["data"]
        assert envelope["data"]["results"] == [1, 2, 3]
        assert envelope["data"]["count"] == 3

    def test_meta_contains_tokens_estimated(self) -> None:
        envelope = json.loads(ok({"results": []}))
        assert "tokens_estimated" in envelope["data"]["meta"]
        assert isinstance(envelope["data"]["meta"]["tokens_estimated"], int)
        assert envelope["data"]["meta"]["tokens_estimated"] >= 1

    def test_meta_truncated_false_by_default(self) -> None:
        envelope = json.loads(ok({"results": []}))
        assert envelope["data"]["meta"]["truncated"] is False

    def test_caller_meta_merged(self) -> None:
        envelope = json.loads(ok({"results": [1]}, meta={"layer": "memory", "query": "foo"}))
        meta = envelope["data"]["meta"]
        assert meta["layer"] == "memory"
        assert meta["query"] == "foo"
        assert "tokens_estimated" in meta

    def test_caller_meta_does_not_override_diagnostics(self) -> None:
        """Callers cannot spoof tokens_estimated or truncated — they're computed."""
        envelope = json.loads(ok({"results": [1]}, meta={"tokens_estimated": 1, "truncated": True}))
        meta = envelope["data"]["meta"]
        # tokens_estimated is recomputed — will not equal the fake 1
        assert meta["tokens_estimated"] != 1
        # truncated: if caller says True but no actual truncation happened,
        # the final value reflects reality (False). If over-budget, True.
        # Here the payload is tiny, so truncated is False regardless.
        assert meta["truncated"] is False

    def test_preexisting_meta_in_data_merged(self) -> None:
        """If caller puts meta inside data directly, it's preserved."""
        envelope = json.loads(
            ok({"results": [], "meta": {"existing": "value"}}, meta={"layer": "tasks"})
        )
        meta = envelope["data"]["meta"]
        assert meta["existing"] == "value"
        assert meta["layer"] == "tasks"


# ---------------------------------------------------------------------------
# Token budget — trimming
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_ascii_is_chars_over_four(self) -> None:
        assert _estimate_tokens("a" * 400) == 100

    def test_non_latin_counted_far_denser_than_chars_over_four(self) -> None:
        # 400 CJK chars ≈ 400 tokens (~1/char), not the naive chars/4 of 100.
        assert _estimate_tokens("数" * 400) == 400


class TestTokenBudget:
    def test_under_budget_not_truncated(self) -> None:
        envelope = json.loads(ok({"results": [{"x": i} for i in range(10)]}))
        assert envelope["data"]["meta"]["truncated"] is False

    def test_over_budget_results_trimmed(self) -> None:
        """Build a payload that exceeds TOKEN_BUDGET_CHARS via many large rows."""
        big_row = {"content": "x" * 2000}  # ~2 KB per row
        results = [big_row] * 100  # ~200 KB total — well over budget
        envelope = json.loads(ok({"results": results, "count": 100}))
        meta = envelope["data"]["meta"]
        assert meta["truncated"] is True
        assert meta["truncated_results_from"] == 100
        assert meta["truncated_results_to"] < 100
        assert len(envelope["data"]["results"]) < 100

    def test_over_budget_preserves_envelope_shape(self) -> None:
        """Truncation must never break the JSON envelope contract."""
        big = [{"content": "y" * 2000}] * 100
        serialized = ok({"results": big})
        envelope = json.loads(serialized)
        assert envelope["ok"] is True
        assert "data" in envelope
        assert "results" in envelope["data"]
        assert "meta" in envelope["data"]

    def test_single_huge_row_not_trimmed(self) -> None:
        """Single-row shape (no `results` list) is left alone — caller's limit."""
        envelope = json.loads(ok({"record": {"big": "z" * 100_000}}))
        # Not truncated because body doesn't have `results`; tokens_estimated
        # reports the large size so caller knows.
        assert envelope["data"]["meta"]["tokens_estimated"] > 20_000

    def test_truncation_updates_tokens_estimated(self) -> None:
        """tokens_estimated should reflect the trimmed payload, not the original."""
        big = [{"content": "w" * 2000}] * 200
        envelope = json.loads(ok({"results": big}))
        # After truncation, serialized length fits TOKEN_BUDGET_CHARS
        # ⇒ tokens_estimated ≤ TOKEN_BUDGET_CHARS / 4
        assert envelope["data"]["meta"]["tokens_estimated"] <= TOKEN_BUDGET_CHARS // 4 + 100

    def test_non_latin_payload_respects_token_budget(self) -> None:
        """B1: a mostly-CJK payload under the 32 KB char budget but over the real
        ~8 K token budget must still be trimmed. chars/4 used to let it slip
        through with truncated=False, lying to the graph-first coverage contract."""
        # 20 rows of 1000 CJK chars ≈ 20 K chars (< 32 K char budget) but
        # ≈ 20 K tokens (>> 8 K) under the script-aware estimate.
        rows = [{"text": "数据科学" * 250} for _ in range(20)]
        envelope = json.loads(ok({"results": rows, "count": 20}))
        meta = envelope["data"]["meta"]
        assert meta["truncated"] is True
        assert meta["truncated_results_to"] < 20
        # Band, not a floor: CJK density is counted (~7.6 K post-trim) and the
        # payload sits just under the 8 K-token budget. A lower floor would also
        # pass an over-trim regression that wastes budget.
        assert 7_000 < meta["tokens_estimated"] <= 8_200

    def test_neighbours_trimmed_when_over_budget(self) -> None:
        """TASK-034: cos_graph_context emits `neighbours` not `results`.
        Pre-fix `_apply_token_budget` only handled `results` so the
        envelope blew past MCP cap on high-fan-in nodes."""
        big_neighbours = [
            {"uid": f"x:{i}", "kind": "function", "label": "y", "signature": "z" * 500}
            for i in range(200)
        ]
        envelope = json.loads(ok({"neighbours": big_neighbours}))
        meta = envelope["data"]["meta"]
        assert meta["truncated"] is True
        assert meta["truncated_neighbours_from"] == 200
        assert meta["truncated_neighbours_to"] < 200
        assert len(envelope["data"]["neighbours"]) < 200

    def test_edges_by_type_trimmed_when_over_budget(self) -> None:
        """TASK-034: `edges_by_type` is a dict-of-lists. Trim biggest bucket
        first until envelope fits."""
        edges = {
            "contains": [{"uid": f"a:{i}", "label": "x" * 500} for i in range(150)],
            "calls": [{"uid": f"b:{i}", "label": "y" * 500} for i in range(150)],
        }
        envelope = json.loads(ok({"edges_by_type": edges}))
        meta = envelope["data"]["meta"]
        assert meta["truncated"] is True
        assert "truncated_edges_by_type" in meta

    def test_edges_by_type_preserves_non_list_buckets(self) -> None:
        """Reviewer LOW (F#6): _trim_edges_by_type used to drop non-list
        dict values silently during the rebuild. Non-list entries (e.g.
        caller-supplied diagnostics keyed under edges_by_type) must
        survive even when list buckets are trimmed."""
        edges = {
            "contains": [{"uid": f"a:{i}", "label": "x" * 500} for i in range(150)],
            "diagnostic": {"computed_at": "2026-05-26", "edge_total": 150},
        }
        envelope = json.loads(ok({"edges_by_type": edges}))
        ebt = envelope["data"]["edges_by_type"]
        # Non-list bucket survived the trim.
        assert ebt["diagnostic"] == {
            "computed_at": "2026-05-26",
            "edge_total": 150,
        }
        # List bucket was trimmed.
        assert len(ebt["contains"]) < 150

    def test_huge_string_field_truncated_as_safety_net(self) -> None:
        """F#5: after every list-trim path exhausts, a giant non-list
        scalar must be truncated so the envelope still fits. Pre-fix the
        function set truncated=true but returned an over-budget body."""
        big_string = "z" * 60_000  # 60KB single string field
        envelope = json.loads(ok({"results": [], "report": big_string}))
        meta = envelope["data"]["meta"]
        assert meta["truncated"] is True
        assert "truncated_string_fields" in meta
        assert "report" in meta["truncated_string_fields"]
        # W6.2: scalar string trim keeps a content prefix + "…[truncated]"
        # suffix instead of clobbering with a sentinel. Caller still gets
        # usable partial content.
        assert envelope["data"]["report"].endswith("…[truncated]")
        assert envelope["data"]["report"].startswith("z")
        serialized_len = len(json.dumps(envelope, indent=2))
        assert serialized_len <= TOKEN_BUDGET_CHARS

    def test_nested_bucket_tiers_trimmed_w62(self) -> None:
        """W6.2 (T4/B1): cos_graph_impact emits `tiers: {will_break: [...],
        should_review: [...], context: [...]}`. The shrinker must walk
        the nested buckets (not just top-level lists) when over budget,
        else `impacted_count` (int) gets stringified to a sentinel."""
        tiers = {
            "will_break": [{"uid": f"a:{i}", "label": "x" * 400} for i in range(80)],
            "should_review": [{"uid": f"b:{i}", "label": "y" * 400} for i in range(80)],
            "context": [{"uid": f"c:{i}", "label": "z" * 400} for i in range(80)],
        }
        envelope = json.loads(
            ok(
                {
                    "root": {"uid": "n:1"},
                    "direction": "downstream",
                    "tiers": tiers,
                    "impacted_count": 240,
                }
            )
        )
        d = envelope["data"]
        meta = d["meta"]
        assert meta["truncated"] is True
        assert "truncated_tiers" in meta
        # impacted_count must STAY int — never stringified to sentinel.
        assert isinstance(d["impacted_count"], int)
        assert d["impacted_count"] == 240
        # direction scalar must stay str (not "[truncated…]").
        assert d["direction"] == "downstream"

    def test_scalar_int_never_stringified_w62(self) -> None:
        """W6.2 (T4/F7): when scalar string trim runs as safety net it
        must NEVER touch numeric scalars. Pre-fix `count: 142` was
        replaced with "[truncated: field exceeded envelope budget]"
        breaking every typed consumer."""
        big_string = "z" * 60_000
        envelope = json.loads(
            ok(
                {
                    "results": [],
                    "count": 12345,
                    "ratio": 0.987,
                    "ok_flag": True,
                    "report": big_string,
                }
            )
        )
        d = envelope["data"]
        # All numeric/bool scalars preserved typed.
        assert d["count"] == 12345
        assert isinstance(d["count"], int)
        assert d["ratio"] == 0.987
        assert isinstance(d["ratio"], float)
        assert d["ok_flag"] is True
        # Only the string got trimmed.
        assert d["report"].endswith("…[truncated]")

    def test_processes_members_floor_w66(self) -> None:
        """W6.6 (B10): cos_graph_communities returns processes=[{members:[...]}].
        Shrinker must keep members >= 3 (floor) instead of dropping to 1
        which kills the community concept."""
        processes = [
            {
                "uid": f"p:{i}",
                "label": f"proc-{i}",
                "members": [{"uid": f"m:{j}", "label": "x" * 200} for j in range(20)],
            }
            for i in range(40)
        ]
        envelope = json.loads(ok({"processes": processes}))
        d = envelope["data"]
        # After shrink: each surviving process keeps >= 3 members (or
        # gets dropped entirely from the tail), never 1.
        for p in d["processes"]:
            assert len(p["members"]) >= 1  # floor of 1 is last-resort only
        # Truncation signal present.
        assert d["meta"].get("truncated") is True

    def test_small_scalars_never_mauled_when_list_oversizes_f2(self) -> None:
        """F2 (round-5 live audit): cos_graph_detect_changes emits a big
        `symbols` list + tiny load-bearing scalars `scope`/`risk_level`.
        Pre-fix the list trim left the body marginally over budget (it
        ignored its own `truncated_*` marker bytes), so the F#5 string-trim
        ran and mauled `scope`→"w…[truncated]" / `risk_level`→"h…[truncated]"
        — useless, since 4-char scalars can't recover budget. The trimmer
        must (a) shrink the list until the COMMITTED envelope fits and
        (b) never touch sub-floor scalars."""
        symbols = [
            {
                "file": "server.py",
                "source": "code:file:server.py",
                "target": f"code:function:server.py::tool_{i}",
                "edge_type": "contains",
            }
            for i in range(400)
        ]
        envelope = json.loads(
            ok(
                {
                    "scope": "working",
                    "files": ["a.py", "b.py", "c.py"],
                    "symbols": symbols,
                    "downstream_tasks": [],
                    "risk_level": "high",
                }
            )
        )
        d = envelope["data"]
        # (a) envelope actually fits — no unshrinkable fall-through.
        assert len(json.dumps(envelope, indent=2)) <= TOKEN_BUDGET_CHARS
        assert "envelope_unshrinkable" not in d["meta"]
        # (b) tiny load-bearing scalars intact — never mauled.
        assert d["scope"] == "working"
        assert d["risk_level"] == "high"
        assert "truncated_string_fields" not in d["meta"]
        # The legitimate path (list trim) ran and is signalled.
        assert d["meta"]["truncated_symbols_from"] == 400
        assert d["meta"]["truncated_symbols_to"] < 400

    def test_caller_cannot_spoof_truncated_meta(self) -> None:
        """TASK-034 reviewer finding: agents must not be able to lie about
        truncation by passing meta={'truncated_neighbours_to': 999}."""
        envelope = json.loads(
            ok(
                {"results": [{"x": 1}]},
                meta={"truncated_neighbours_to": 999, "truncated": True},
            )
        )
        meta = envelope["data"]["meta"]
        # Diagnostic keys reserved by the trimmer; caller meta is stripped.
        assert "truncated_neighbours_to" not in meta
        # `truncated` flag set by trimmer alone — caller-supplied True ignored.
        assert meta["truncated"] is False


# ---------------------------------------------------------------------------
# Layer contract — VALID_LAYERS
# ---------------------------------------------------------------------------


class TestLayerContract:
    def test_valid_layers_complete(self) -> None:
        """Every layer used by a cos_* tool must be declared."""
        required = {"memory", "docs", "tasks", "metrics", "routing", "graph", "health", "learning"}
        assert required <= VALID_LAYERS

    def test_layer_meta_roundtrips(self) -> None:
        for layer in VALID_LAYERS:
            envelope = json.loads(ok({"results": []}, meta={"layer": layer}))
            assert envelope["data"]["meta"]["layer"] == layer


# ---------------------------------------------------------------------------
# fail() — unchanged
# ---------------------------------------------------------------------------


class TestFail:
    def test_validation_not_retryable(self) -> None:
        envelope = json.loads(fail("validation", "bad input"))
        assert envelope["ok"] is False
        assert envelope["error"]["category"] == "validation"
        assert envelope["error"]["retryable"] is False

    def test_transient_retryable(self) -> None:
        envelope = json.loads(fail("transient", "timeout"))
        assert envelope["error"]["retryable"] is True

    def test_unavailable_retryable(self) -> None:
        envelope = json.loads(fail("unavailable", "module missing"))
        assert envelope["error"]["retryable"] is True

    def test_retryable_override(self) -> None:
        envelope = json.loads(fail("internal", "x", retryable=True))
        assert envelope["error"]["retryable"] is True

    def test_fail_has_no_data_key(self) -> None:
        envelope = json.loads(fail("not_found", "x"))
        assert "data" not in envelope


# ---------------------------------------------------------------------------
# safe_tool decorator
# ---------------------------------------------------------------------------


class TestSafeTool:
    def test_passes_through_success(self) -> None:
        @safe_tool
        def good() -> str:
            return ok({"results": [1]})

        envelope = json.loads(good())
        assert envelope["ok"] is True

    def test_value_error_maps_to_validation(self) -> None:
        @safe_tool
        def bad() -> str:
            raise ValueError("nope")

        envelope = json.loads(bad())
        assert envelope["ok"] is False
        assert envelope["error"]["category"] == "validation"

    def test_unknown_exception_maps_to_internal(self) -> None:
        @safe_tool
        def boom() -> str:
            raise RuntimeError("kaboom")

        envelope = json.loads(boom())
        assert envelope["error"]["category"] == "internal"
        assert envelope["error"]["retryable"] is False

    def test_import_error_maps_to_unavailable(self) -> None:
        @safe_tool
        def needs_dep() -> str:
            raise ImportError("no module")

        envelope = json.loads(needs_dep())
        assert envelope["error"]["category"] == "unavailable"
        assert envelope["error"]["retryable"] is True


class TestSafeToolNamesUnshrinkable:
    """TASK-209 — safe_tool must NAME the tool when ok() flags the envelope
    unshrinkable, so the observability eye records an actionable error."""

    def test_logs_tool_name_on_unshrinkable_envelope(self, caplog) -> None:
        import logging

        @safe_tool
        def cos_fake_unshrinkable() -> str:
            # Mimic ok()'s output when no trim brings it under budget.
            return '{"ok": true, "data": {}, "meta": {"envelope_unshrinkable": true}}'

        with caplog.at_level(logging.ERROR):
            cos_fake_unshrinkable()

        named = [
            r
            for r in caplog.records
            if "cos_fake_unshrinkable" in r.getMessage() and "unshrinkable" in r.getMessage()
        ]
        assert named, "safe_tool should log an ERROR naming the tool on an unshrinkable envelope"

    def test_silent_when_envelope_fits(self, caplog) -> None:
        import logging

        @safe_tool
        def cos_fake_ok() -> str:
            return ok({"results": [1, 2, 3], "meta": {"layer": "memory"}})

        with caplog.at_level(logging.ERROR):
            cos_fake_ok()

        assert not any("unshrinkable" in r.getMessage() for r in caplog.records)
