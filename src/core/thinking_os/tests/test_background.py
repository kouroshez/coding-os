"""
Tests for background.py — continuous indexer.

Focus:
  - is_enabled() and interval parsing env-var handling
  - BackgroundIndexer.run_once() success / failure / disabled-after-3-fails
  - start/stop lifecycle idempotency
  - status() snapshot shape
  - maybe_start_indexer() gating on COS_BACKGROUND_INDEX

Threading is tested with injected fake runners so tests don't touch the
real doc_indexer or task_sync pipelines (speed + isolation).
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import pytest

# Wall-clock heavyweight: real tick/poll loops dominate the whole thinking_os
# suite (237 s of 322 s measured 2026-06-09 — docs/engineering/test-governance.md).
# Runs via `make test-slow` / pre-merge, excluded from the mid-task matrix command.
pytestmark = pytest.mark.slow

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import background
from background import (
    _MAX_CONSECUTIVE_FAILURES,
    ENV_ENABLED,
    ENV_INTERVAL,
    BackgroundIndexer,
    is_enabled,
    maybe_start_indexer,
    reset_singleton_for_tests,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_singleton() -> None:
    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


def _ok_runner(tag: str, counter: list[int] | None = None) -> Callable[[], dict]:
    def _run() -> dict:
        if counter is not None:
            counter.append(1)
        return {"status": "ok", "tag": tag}

    return _run


def _fail_runner(msg: str) -> Callable[[], dict]:
    def _run() -> dict:
        raise RuntimeError(msg)

    return _run


# ---------------------------------------------------------------------------
# Env parsing
# ---------------------------------------------------------------------------


class TestEnvParsing:
    def test_is_enabled_false_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_ENABLED, raising=False)
        assert is_enabled() is False

    @pytest.mark.parametrize("v", ["1", "true", "YES", "On"])
    def test_is_enabled_truthy_values(
        self,
        v: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(ENV_ENABLED, v)
        assert is_enabled() is True

    @pytest.mark.parametrize("v", ["0", "false", "no", "off", ""])
    def test_is_enabled_falsy_values(
        self,
        v: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(ENV_ENABLED, v)
        assert is_enabled() is False

    def test_interval_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_INTERVAL, raising=False)
        assert background._parse_interval() == background.DEFAULT_INTERVAL_SECONDS

    def test_interval_clamped_low(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_INTERVAL, "1")
        assert background._parse_interval() == background._MIN_INTERVAL_SECONDS

    def test_interval_clamped_high(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_INTERVAL, "999999")
        assert background._parse_interval() == background._MAX_INTERVAL_SECONDS

    def test_interval_non_numeric_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ENV_INTERVAL, "abc")
        assert background._parse_interval() == background.DEFAULT_INTERVAL_SECONDS


# ---------------------------------------------------------------------------
# run_once — success path
# ---------------------------------------------------------------------------


class TestRunOnceSuccess:
    def test_single_tick_records_stats(self) -> None:
        docs_calls: list[int] = []
        task_calls: list[int] = []
        idx = BackgroundIndexer(
            interval_seconds=60,
            run_docs_index=_ok_runner("docs", docs_calls),
            run_task_sync=_ok_runner("tasks", task_calls),
        )
        stats = idx.run_once()
        assert len(docs_calls) == 1
        assert len(task_calls) == 1
        assert stats["docs"]["status"] == "ok"
        assert stats["tasks"]["status"] == "ok"

        s = idx.status()
        assert s["iterations"] == 1
        assert s["last_error"] is None
        assert s["consecutive_failures"] == 0
        assert s["last_duration_ms"] is not None
        assert s["last_run_at"] is not None

    def test_multiple_ticks_accumulate(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=60,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        for _ in range(5):
            idx.run_once()
        assert idx.status()["iterations"] == 5
        assert idx.status()["consecutive_failures"] == 0


# ---------------------------------------------------------------------------
# run_once — failure path
# ---------------------------------------------------------------------------


class TestRunOnceFailure:
    def test_single_failure_recorded(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=60,
            run_docs_index=_fail_runner("docs boom"),
            run_task_sync=_ok_runner("tasks"),
        )
        idx.run_once()
        s = idx.status()
        assert s["consecutive_failures"] == 1
        assert s["last_error"] is not None
        assert "docs boom" in s["last_error"]
        assert s["disabled_reason"] is None

    def test_three_failures_disable_loop(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=60,
            run_docs_index=_fail_runner("boom"),
            run_task_sync=_fail_runner("boom2"),
        )
        for _ in range(_MAX_CONSECUTIVE_FAILURES):
            idx.run_once()
        s = idx.status()
        assert s["consecutive_failures"] >= _MAX_CONSECUTIVE_FAILURES
        assert s["disabled_reason"] is not None
        assert "disabled" in s["disabled_reason"].lower()

    def test_success_after_failure_resets_counter(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=60,
            run_docs_index=_fail_runner("first fail"),
            run_task_sync=_ok_runner("tasks"),
        )
        idx.run_once()
        assert idx.status()["consecutive_failures"] == 1

        # Replace the failing runner
        idx._run_docs_index = _ok_runner("recovered")
        idx.run_once()
        s = idx.status()
        assert s["consecutive_failures"] == 0
        assert s["last_error"] is None


# ---------------------------------------------------------------------------
# Thread lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_start_returns_true_first_call(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        try:
            assert idx.start() is True
            assert idx.status()["running"] is True
        finally:
            idx.stop(timeout=2.0)

    def test_start_idempotent(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        try:
            assert idx.start() is True
            assert idx.start() is False  # already running
        finally:
            idx.stop(timeout=2.0)

    def test_stop_blocks_until_thread_exits(self) -> None:
        counter: list[int] = []
        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs", counter),
            run_task_sync=_ok_runner("tasks"),
            run_graph_index=_ok_runner("graph"),
        )
        idx.start()
        # Give thread a moment to run once
        for _ in range(20):
            if counter:
                break
            time.sleep(0.05)
        ok = idx.stop(timeout=3.0)
        assert ok is True
        assert idx.status()["running"] is False

    def test_stop_idempotent_when_never_started(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        assert idx.stop(timeout=0.5) is True


# ---------------------------------------------------------------------------
# maybe_start_indexer (opt-in gate)
# ---------------------------------------------------------------------------


class TestMaybeStartIndexer:
    def test_disabled_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_ENABLED, raising=False)
        result = maybe_start_indexer()
        assert result["started"] is False
        assert "opt-in" in result["reason"].lower()

    def test_enabled_starts_singleton(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """With the env var set, maybe_start_indexer should start the singleton
        indexer exactly once. A second call returns started=False."""
        monkeypatch.setenv(ENV_ENABLED, "1")
        # Replace default runners by pre-seeding the singleton so it doesn't
        # touch the real filesystem pipeline.
        indexer = background.BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        background._singleton = indexer
        try:
            first = maybe_start_indexer()
            second = maybe_start_indexer()
            assert first["started"] is True
            assert second["started"] is False
            assert "already running" in second["reason"]
        finally:
            indexer.stop(timeout=2.0)


# ---------------------------------------------------------------------------
# Status snapshot shape
# ---------------------------------------------------------------------------


class TestStatusShape:
    def test_required_keys_present(self) -> None:
        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        s = idx.status()
        for key in (
            "enabled",
            "running",
            "iterations",
            "last_run_at",
            "last_duration_ms",
            "last_error",
            "consecutive_failures",
            "disabled_reason",
            "next_run_in_seconds",
            "last_stats",
            "interval_seconds",
        ):
            assert key in s, f"status missing key: {key}"

    def test_status_is_json_safe(self) -> None:
        import json

        idx = BackgroundIndexer(
            interval_seconds=30,
            run_docs_index=_ok_runner("docs"),
            run_task_sync=_ok_runner("tasks"),
        )
        idx.run_once()
        s = idx.status()
        # Should serialize without default=str tricks
        serialized = json.dumps(s)
        assert len(serialized) > 0
