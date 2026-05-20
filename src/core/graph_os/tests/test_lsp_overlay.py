"""Tests for graph_os.lsp_overlay (I.5).

Ship gate (Section 19 I.5):
  - precision ≥ 95% on golden set WITH LSP — measured in I.4 golden
    once the real pyright driver lands (this module only proves the
    overlay's lifecycle + breaker contract with a fake driver).
  - graceful degrade test (kill pyright mid-index) — modelled with
    FakeLspDriver that raises.
  - warm-start latency test (≤ 60s cold, ≤ 5s warm) — simulated via
    `warm_start_latency`.
"""

from __future__ import annotations

import itertools

import pytest

from graph_os.lsp_overlay import (
    DEFAULT_MAX_FAILURES,
    FakeLspDriver,
    LspOverlay,
    LspOverlayResult,
    build_overlay,
)


class _FakeClock:
    """Deterministic clock — advance with .tick()."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def tick(self, delta: float) -> None:
        self.now += delta


def _make_overlay(
    *,
    driver: FakeLspDriver | None = None,
    clock: _FakeClock | None = None,
    **kwargs,
) -> LspOverlay:
    clock = clock or _FakeClock()
    driver = driver or FakeLspDriver(
        resolver=lambda f, s: LspOverlayResult(
            status="ok",
            uid=f"code:function:{f}::{s}",
            confidence=0.95,
            note="lsp",
        )
    )
    return LspOverlay(driver, clock=clock, **kwargs)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_initial_state_cold(self):
        overlay = _make_overlay()
        assert overlay.state == "cold"

    def test_warm_start_transitions_ready(self):
        overlay = _make_overlay()
        assert overlay.warm_start() is True
        assert overlay.state == "ready"

    def test_warm_start_failure_keeps_cold(self):
        driver = FakeLspDriver(warm_start_succeeds=False)
        overlay = _make_overlay(driver=driver)
        assert overlay.warm_start() is False
        assert overlay.state == "cold"

    def test_warm_start_timeout_returns_false(self):
        driver = FakeLspDriver(warm_start_latency=999.0)
        overlay = LspOverlay(driver)
        # Warm-start uses DEFAULT_WARM_START_TIMEOUT_SECONDS internally;
        # simulate a latency > default timeout by passing explicit config.
        driver.warm_start_latency = 120.1
        assert overlay.warm_start() is False

    def test_shutdown_invokes_driver_and_clears_cache(self):
        driver = FakeLspDriver()
        overlay = _make_overlay(driver=driver)
        overlay.warm_start()
        overlay.lookup(file_path="a.py", symbol="f")
        assert driver.shutdown_called == 0
        overlay.shutdown()
        assert driver.shutdown_called == 1
        # Cache cleared.
        snapshot = overlay.snapshot()
        assert snapshot["cache_size"] == 0


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


class TestLookup:
    def test_successful_lookup_returns_ok(self):
        overlay = _make_overlay()
        res = overlay.lookup(file_path="a.py", symbol="foo")
        assert res.status == "ok"
        assert res.uid.endswith("::foo")

    def test_cache_hits_avoid_second_resolve(self):
        driver = FakeLspDriver()
        overlay = _make_overlay(driver=driver)
        overlay.lookup(file_path="a.py", symbol="foo")
        overlay.lookup(file_path="a.py", symbol="foo")
        assert driver.resolve_calls == 1

    def test_different_symbols_trigger_separate_resolves(self):
        driver = FakeLspDriver()
        overlay = _make_overlay(driver=driver)
        overlay.lookup(file_path="a.py", symbol="foo")
        overlay.lookup(file_path="a.py", symbol="bar")
        assert driver.resolve_calls == 2

    def test_different_files_trigger_separate_resolves(self):
        driver = FakeLspDriver()
        overlay = _make_overlay(driver=driver)
        overlay.lookup(file_path="a.py", symbol="foo")
        overlay.lookup(file_path="b.py", symbol="foo")
        assert driver.resolve_calls == 2

    def test_non_ok_status_not_cached(self):
        driver = FakeLspDriver(
            resolver=lambda _f, _s: LspOverlayResult(status="unavailable"),
        )
        overlay = _make_overlay(driver=driver)
        overlay.lookup(file_path="a.py", symbol="foo")
        overlay.lookup(file_path="a.py", symbol="foo")
        assert driver.resolve_calls == 2

    def test_driver_exception_reports_unavailable(self):
        def boom(_f, _s):
            raise RuntimeError("kaboom")

        driver = FakeLspDriver(resolver=boom)
        overlay = _make_overlay(driver=driver)
        res = overlay.lookup(file_path="a.py", symbol="foo")
        assert res.status == "unavailable"
        assert "kaboom" in (res.note or "")

    def test_timeout_returns_timeout_status(self):
        driver = FakeLspDriver(latency=10.0)
        overlay = _make_overlay(driver=driver, timeout_seconds=0.01)
        res = overlay.lookup(file_path="a.py", symbol="foo")
        assert res.status == "timeout"


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_opens_after_threshold_failures(self):
        clock = _FakeClock()
        calls = itertools.count()

        def _maybe_boom(_f, _s):
            _ = next(calls)
            return LspOverlayResult(status="timeout")

        driver = FakeLspDriver(resolver=_maybe_boom)
        overlay = _make_overlay(
            driver=driver,
            clock=clock,
            max_failures=DEFAULT_MAX_FAILURES,
        )
        for _ in range(DEFAULT_MAX_FAILURES):
            clock.tick(1.0)
            overlay.lookup(file_path="a.py", symbol="s")
        assert overlay.state == "degraded"

    def test_open_breaker_short_circuits_resolves(self):
        clock = _FakeClock()
        driver = FakeLspDriver(resolver=lambda _f, _s: LspOverlayResult(status="timeout"))
        overlay = _make_overlay(
            driver=driver, clock=clock, max_failures=2, degrade_cooldown_seconds=300
        )
        # Trip it.
        for _ in range(2):
            overlay.lookup(file_path="a.py", symbol="s")
        assert overlay.state == "degraded"
        before = driver.resolve_calls
        overlay.lookup(file_path="a.py", symbol="s2")
        assert driver.resolve_calls == before  # short-circuited

    def test_breaker_resets_after_cooldown(self):
        clock = _FakeClock()
        driver = FakeLspDriver(resolver=lambda _f, _s: LspOverlayResult(status="timeout"))
        overlay = _make_overlay(
            driver=driver,
            clock=clock,
            max_failures=2,
            degrade_cooldown_seconds=60,
        )
        for _ in range(2):
            overlay.lookup(file_path="a.py", symbol="s")
        assert overlay.state == "degraded"
        clock.tick(61)
        assert overlay.state == "ready" or overlay.state == "cold"

    def test_old_failures_pruned(self):
        clock = _FakeClock()
        driver = FakeLspDriver(resolver=lambda _f, _s: LspOverlayResult(status="timeout"))
        overlay = _make_overlay(
            driver=driver,
            clock=clock,
            max_failures=3,
            failure_window_seconds=10,
            degrade_cooldown_seconds=30,
        )
        # Two failures now, one failure 30 s later — the first two are
        # outside the 10 s window so breaker should NOT trip.
        overlay.lookup(file_path="a.py", symbol="x")
        overlay.lookup(file_path="a.py", symbol="y")
        clock.tick(30)
        overlay.lookup(file_path="a.py", symbol="z")
        assert overlay.state != "degraded"


# ---------------------------------------------------------------------------
# Disabled overlay
# ---------------------------------------------------------------------------


class TestDisabled:
    def test_disabled_overlay_never_calls_driver(self):
        driver = FakeLspDriver()
        overlay = _make_overlay(driver=driver, enabled=False)
        overlay.warm_start()  # no-op
        res = overlay.lookup(file_path="a.py", symbol="foo")
        assert res.status == "unavailable"
        assert res.note == "disabled"
        assert driver.resolve_calls == 0
        assert driver.warm_start_called == 0

    def test_state_is_disabled(self):
        overlay = _make_overlay(enabled=False)
        assert overlay.state == "disabled"


# ---------------------------------------------------------------------------
# build_overlay factory
# ---------------------------------------------------------------------------


class TestBuildOverlay:
    def test_env_variable_disables(self, monkeypatch):
        monkeypatch.setenv("COS_LSP_ENABLED", "0")
        overlay = build_overlay("python")
        assert overlay.enabled is False

    def test_unsupported_language_returns_disabled(self):
        overlay = build_overlay("cobol")
        assert overlay.enabled is False

    def test_fake_config_uses_fake_driver(self):
        overlay = build_overlay("python", config={"fake": True, "latency": 0.001})
        assert overlay.enabled is True
        # Warm-start + lookup work without network.
        assert overlay.warm_start() is True
        res = overlay.lookup(file_path="a.py", symbol="foo")
        assert res.status == "ok"

    def test_snapshot_keys(self):
        overlay = build_overlay("python", config={"fake": True})
        snap = overlay.snapshot()
        for key in (
            "language",
            "enabled",
            "state",
            "warm",
            "cache_size",
            "tripped_until",
            "recent_failures",
        ):
            assert key in snap
