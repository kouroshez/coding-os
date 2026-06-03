"""Unit tests for formula_composer pure helpers (role-chain composition).

The composer is integration-tested by tests/test_formula_composer.py +
the phase-N suites (~75% combined); this targets the reachable
pure-logic branches: trigger / preset matching operators, canonical
ordering, threshold resolution, deep-merge, situation-chain extraction.
Signals are stubbed with SimpleNamespace to decouple from the schema.
"""

from __future__ import annotations

from types import SimpleNamespace

import formula_composer as fc


def _sig(**kw):
    return SimpleNamespace(**kw)


# ---------------------------------------------------------------------------
# _trigger_matches — every operator
# ---------------------------------------------------------------------------


class TestTriggerMatches:
    def test_no_signal_key_false(self):
        assert fc._trigger_matches({}, _sig(action="x")) is False

    def test_equals(self):
        assert fc._trigger_matches({"signal": "action", "equals": "debug"}, _sig(action="debug"))
        assert not fc._trigger_matches({"signal": "action", "equals": "debug"}, _sig(action="ship"))

    def test_in_scalar(self):
        t = {"signal": "action", "in": ["debug", "fix"]}
        assert fc._trigger_matches(t, _sig(action="fix"))
        assert not fc._trigger_matches(t, _sig(action="ship"))

    def test_in_list_value(self):
        t = {"signal": "domains", "in": ["security", "api"]}
        assert fc._trigger_matches(t, _sig(domains=["api", "ui"]))
        assert not fc._trigger_matches(t, _sig(domains=["ui"]))

    def test_contains_scalar_needle(self):
        t = {"signal": "domains", "contains": "security"}
        assert fc._trigger_matches(t, _sig(domains=["security", "api"]))
        assert not fc._trigger_matches(t, _sig(domains="security"))  # val not a list

    def test_contains_list_needle(self):
        t = {"signal": "domains", "contains": ["x", "api"]}
        assert fc._trigger_matches(t, _sig(domains=["api"]))

    def test_gte_and_lte(self):
        assert fc._trigger_matches({"signal": "dims", "gte": 3}, _sig(dims=5))
        assert not fc._trigger_matches({"signal": "dims", "gte": 3}, _sig(dims=1))
        assert fc._trigger_matches({"signal": "dims", "lte": 3}, _sig(dims=2))

    def test_gte_bad_value_false(self):
        assert not fc._trigger_matches({"signal": "dims", "gte": 3}, _sig(dims="nope"))

    def test_unknown_operator_false(self):
        assert fc._trigger_matches({"signal": "action"}, _sig(action="x")) is False

    def test_trigger_desc(self):
        assert fc._trigger_desc({"signal": "action", "equals": "debug"}) == "action:equals='debug'"


# ---------------------------------------------------------------------------
# _preset_match_satisfied — suffix operators
# ---------------------------------------------------------------------------


class TestPresetMatch:
    def test_any_suffix(self):
        assert fc._preset_match_satisfied({"domains_any": ["api"]}, _sig(domains=["api", "ui"]))
        assert not fc._preset_match_satisfied({"domains_any": ["x"]}, _sig(domains=["ui"]))

    def test_any_suffix_non_list_value_false(self):
        assert not fc._preset_match_satisfied({"domains_any": ["api"]}, _sig(domains="api"))

    def test_in_suffix(self):
        assert fc._preset_match_satisfied({"action_in": ["debug", "fix"]}, _sig(action="fix"))
        assert not fc._preset_match_satisfied({"action_in": ["debug"]}, _sig(action="ship"))

    def test_gte_suffix(self):
        assert fc._preset_match_satisfied({"dims_gte": 3}, _sig(dims=4))
        assert not fc._preset_match_satisfied({"dims_gte": 3}, _sig(dims=1))

    def test_gte_suffix_bad_value_false(self):
        assert not fc._preset_match_satisfied({"dims_gte": 3}, _sig(dims=None))

    def test_lte_suffix(self):
        assert fc._preset_match_satisfied({"dims_lte": 3}, _sig(dims=2))
        assert not fc._preset_match_satisfied({"dims_lte": 3}, _sig(dims=9))

    def test_plain_equals(self):
        assert fc._preset_match_satisfied({"action": "debug"}, _sig(action="debug"))
        assert not fc._preset_match_satisfied({"action": "debug"}, _sig(action="ship"))

    def test_plain_list_overlap(self):
        assert fc._preset_match_satisfied({"domains": ["api"]}, _sig(domains=["api", "ui"]))

    def test_all_keys_must_pass(self):
        match = {"action": "debug", "dims_gte": 3}
        assert fc._preset_match_satisfied(match, _sig(action="debug", dims=4))
        assert not fc._preset_match_satisfied(match, _sig(action="debug", dims=1))


# ---------------------------------------------------------------------------
# _match_best_preset — scoring + threshold
# ---------------------------------------------------------------------------


class TestMatchBestPreset:
    def test_picks_highest_score(self):
        presets = [
            {"id": "a", "match": {"action": "debug"}, "score": 5},
            {"id": "b", "match": {"action": "debug"}, "score": 9},
        ]
        best = fc._match_best_preset(_sig(action="debug"), presets, threshold=1)
        assert best["id"] == "b"

    def test_below_threshold_excluded(self):
        presets = [{"id": "a", "match": {"action": "debug"}, "score": 2}]
        assert fc._match_best_preset(_sig(action="debug"), presets, threshold=5) is None

    def test_empty_match_skipped(self):
        presets = [{"id": "a", "match": {}, "score": 9}]
        assert fc._match_best_preset(_sig(action="x"), presets, threshold=1) is None


# ---------------------------------------------------------------------------
# Misc pure helpers
# ---------------------------------------------------------------------------


class TestMiscHelpers:
    def test_order_canonical_dedups(self):
        out = fc._order_canonical(["reviewer", "researcher", "reviewer"])
        assert len(out) == 2
        assert set(out) == {"reviewer", "researcher"}

    def test_extract_situation_chain(self):
        sit = {"dispatch_chain": [{"dispatch": "f1"}, {"dispatch": "f2"}, {"noise": 1}]}
        assert fc._extract_situation_chain(sit) == ["f1", "f2"]

    def test_extract_situation_chain_empty(self):
        assert fc._extract_situation_chain({}) == []

    def test_resolve_threshold_override_clamped(self):
        assert fc._resolve_threshold(99) == 15
        assert fc._resolve_threshold(-5) == 0
        assert fc._resolve_threshold(7) == 7

    def test_deep_merge_nested(self):
        base = {"a": {"x": 1, "y": 2}, "b": 1}
        fc._deep_merge(base, {"a": {"y": 9, "z": 3}, "c": 4})
        assert base == {"a": {"x": 1, "y": 9, "z": 3}, "b": 1, "c": 4}

    def test_deep_merge_list_replaced(self):
        base = {"items": [1, 2, 3]}
        fc._deep_merge(base, {"items": [9]})
        assert base == {"items": [9]}
