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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools._shared import (
    VALID_LAYERS,
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


class TestLayerContract:
    def test_valid_layers_complete(self) -> None:
        """Every layer used by a cos_* tool must be declared."""
        required = {"memory", "docs", "tasks", "metrics", "routing", "graph", "health", "learning"}
        assert required <= VALID_LAYERS

    def test_layer_meta_roundtrips(self) -> None:
        for layer in VALID_LAYERS:
            envelope = json.loads(ok({"results": []}, meta={"layer": layer}))
            assert envelope["data"]["meta"]["layer"] == layer


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

    def test_failure_log_carries_pid_thread_and_db_identity(self, caplog) -> None:
        # Forensics contract (mcp-error-envelope.md § Internal-error
        # forensics): multi-process .mcp.log attribution needs pid + thread,
        # and sqlite errors must name the DB the connection was attached to.
        import os
        import sqlite3
        import threading

        conn = sqlite3.connect(":memory:")

        @safe_tool
        def hits_missing_table(db: sqlite3.Connection) -> str:
            db.execute("INSERT INTO tasks (task_id) VALUES ('x')")
            return ok({})

        with caplog.at_level("ERROR", logger="coding_os.tools._shared"):
            envelope = json.loads(hits_missing_table(conn))

        assert envelope["error"]["category"] == "internal"
        record = next(r for r in caplog.records if "hits_missing_table" in r.getMessage())
        assert f"pid={os.getpid()}" in record.getMessage()
        assert f"thread={threading.current_thread().name}" in record.getMessage()
        assert "db=" in record.getMessage()

    def test_failure_log_skips_db_identity_for_non_sqlite_errors(self, caplog) -> None:
        @safe_tool
        def plain_boom() -> str:
            raise RuntimeError("kaboom")

        with caplog.at_level("ERROR", logger="coding_os.tools._shared"):
            json.loads(plain_boom())

        record = next(r for r in caplog.records if "plain_boom" in r.getMessage())
        assert "db=" not in record.getMessage()
        assert "pid=" in record.getMessage()


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
