"""Codex token→USD pricing — the table, the tier switch, and the refusals.

Codex reports tokens and no dollar figure, so this is the only thing standing
between "13 codex dispatches" and a rollup that reads as if codex were free.
The numbers are asserted against the published table rather than against the
implementation, so a silent edit to either one fails here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.codex._codex_pricing import cost_usd, pricing_for
from thinking_os.dispatcher_helpers import price_tokens

DESCRIPTOR = SRC / "adapters" / "codex" / "adapter.yaml"

# Read from https://platform.openai.com/docs/pricing on 2026-08-21, standard
# tier, gpt-5.6-sol. Restated here so a change to the descriptor has to be a
# deliberate edit in two places rather than a typo in one.
SHORT = {"input": 5.00, "cached_input": 0.50, "cache_write": 6.25, "output": 30.00}
LONG = {"input": 10.00, "cached_input": 1.00, "cache_write": 12.50, "output": 45.00}
THRESHOLD = 272_000


class TestDescriptor:
    def test_the_declared_table_matches_the_published_one(self) -> None:
        manifest = yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))
        pricing = manifest["models"][0]["pricing"]
        assert pricing["unit"] == "usd_per_mtok"
        assert pricing["rates"]["short"] == SHORT
        assert pricing["rates"]["long"] == LONG
        assert pricing["long_context_input_tokens"] == THRESHOLD

    def test_cache_writes_are_the_documented_multiple_of_input(self) -> None:
        # OpenAI states cache writes bill at 1.25x the uncached input rate. The
        # table was read independently of that sentence; the two agreeing is the
        # only reason to trust either.
        for tier in (SHORT, LONG):
            assert tier["cache_write"] == pytest.approx(tier["input"] * 1.25)

    def test_the_table_records_where_and_when_it_came_from(self) -> None:
        pricing = yaml.safe_load(DESCRIPTOR.read_text(encoding="utf-8"))["models"][0]["pricing"]
        assert pricing["source"].startswith("https://")
        assert len(pricing["retrieved"]) == 10


class TestTierSelection:
    def test_below_the_threshold_bills_short(self) -> None:
        assert price_tokens({"input": 100_000}, pricing_for("gpt-5.6-sol")) == 0.5

    def test_at_the_threshold_is_still_short(self) -> None:
        # The published wording is "exceeds", so the boundary itself is short.
        assert price_tokens({"input": THRESHOLD}, pricing_for("gpt-5.6-sol")) == pytest.approx(1.36)

    def test_one_token_over_switches_the_whole_call_to_long(self) -> None:
        assert price_tokens({"input": THRESHOLD + 1}, pricing_for("gpt-5.6-sol")) == pytest.approx(
            (THRESHOLD + 1) * 10 / 1e6
        )

    def test_output_alone_never_trips_the_input_tier(self) -> None:
        # The tier is metered on input; a long answer to a short prompt is not
        # a long-context request.
        assert price_tokens({"output": 1_000_000}, pricing_for("gpt-5.6-sol")) == 30.0

    def test_cached_and_written_tokens_count_toward_the_tier(self) -> None:
        buckets = {"input": 100_000, "cached_input": 100_000, "cache_write": 100_000}
        assert price_tokens(buckets, pricing_for("gpt-5.6-sol")) == pytest.approx(
            (100_000 * 10 + 100_000 * 1 + 100_000 * 12.5) / 1e6
        )


class TestUsageMapping:
    def test_prices_a_real_recorded_turn(self) -> None:
        # Copied from a rollout this machine actually wrote.
        usage = {
            "input_tokens": 24970,
            "cached_input_tokens": 11008,
            "cache_write_input_tokens": 0,
            "output_tokens": 557,
            "reasoning_output_tokens": 206,
            "total_tokens": 25527,
        }
        expected = ((24970 - 11008) * 5.00 + 11008 * 0.50 + 557 * 30.00) / 1e6
        assert cost_usd(usage, "gpt-5.6-sol") == pytest.approx(expected)

    def test_reasoning_tokens_are_not_charged_twice(self) -> None:
        # They are already inside output_tokens; adding them again would inflate
        # every reasoning-heavy run.
        with_reasoning = {"output_tokens": 1000, "reasoning_output_tokens": 900}
        assert cost_usd(with_reasoning, "gpt-5.6-sol") == cost_usd(
            {"output_tokens": 1000}, "gpt-5.6-sol"
        )

    def test_cached_tokens_are_subtracted_from_the_full_rate_bucket(self) -> None:
        all_cached = {"input_tokens": 1000, "cached_input_tokens": 1000}
        assert cost_usd(all_cached, "gpt-5.6-sol") == pytest.approx(1000 * 0.50 / 1e6)

    def test_a_cached_count_larger_than_input_floors_instead_of_going_negative(self) -> None:
        odd = {"input_tokens": 100, "cached_input_tokens": 500}
        assert cost_usd(odd, "gpt-5.6-sol") == pytest.approx(500 * 0.50 / 1e6)


class TestRefusals:
    def test_an_undeclared_model_is_priceless_not_priced_off_a_neighbour(self) -> None:
        # Reporting a confident wrong number is worse than the empty cell an
        # unpriced row leaves.
        assert cost_usd({"input_tokens": 1000}, "gpt-4o") is None

    def test_an_unnamed_model_uses_the_adapter_default(self) -> None:
        assert cost_usd({"input_tokens": 1000}, "") == pytest.approx(1000 * 5.00 / 1e6)

    def test_no_usage_is_unknown_not_zero(self) -> None:
        assert cost_usd(None, "gpt-5.6-sol") is None

    def test_no_table_is_unknown_not_zero(self) -> None:
        assert price_tokens({"input": 1_000_000}, None) is None
        assert price_tokens({"input": 1_000_000}, {"unit": "credits", "rates": {}}) is None

    def test_a_bucket_the_table_does_not_price_is_skipped_silently(self) -> None:
        pricing = {"unit": "usd_per_mtok", "rates": {"short": {"input": 5.0, "output": 30.0}}}
        assert price_tokens({"input": 1_000_000, "cache_write": 9_999}, pricing) == 5.0
