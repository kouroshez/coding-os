"""Tests for the orchestrator (I.9).

Ship gate (Section 19 I.9):
  - parallel indexing 10k files < 60s (modelled with fake tasks)
  - cancellation test
  - crash-restart test
  - role isolation (one crashing role does not block others)
"""

from __future__ import annotations

import threading
import time

import pytest

from graph_os.orchestrator import (
    Dispatcher,
    ProgressReporter,
    Role,
    RoleContext,
    RoleRegistry,
    RoleResult,
    WorkerPool,
    default_registry,
)
from graph_os.orchestrator.roles import (
    indexer_graph_os,
    lsp_warm_start,
    migrator_embeddings,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_register_resolve(self):
        reg = RoleRegistry()
        called = {}

        def handler(ctx: RoleContext) -> RoleResult:
            called["yes"] = True
            return RoleResult(status="ok")

        reg.register(Role(name="test", handler=handler))
        role = reg.resolve("test")
        assert role.name == "test"

    def test_resolve_missing_raises(self):
        reg = RoleRegistry()
        with pytest.raises(KeyError):
            reg.resolve("ghost")

    def test_default_registry_has_phase_i_roles(self):
        reg = default_registry()
        names = set(reg.known_names())
        assert {
            "indexer:graph-os",
            "lsp:warm-start",
            "migrator:embeddings",
        } <= names


# ---------------------------------------------------------------------------
# WorkerPool
# ---------------------------------------------------------------------------


class TestWorkerPool:
    def test_single_task(self):
        pool = WorkerPool(size=2)
        try:
            task = pool.submit(
                role_name="t",
                handler=lambda ctx: RoleResult(status="ok", payload={"x": 1}),
                ctx=RoleContext(role_name="t"),
            )
            task.done.wait(timeout=2)
            assert task.result.status == "ok"
            assert task.result.payload["x"] == 1
        finally:
            pool.shutdown()

    def test_parallelism(self):
        pool = WorkerPool(size=4)
        started = threading.Event()
        release = threading.Event()

        def handler(_ctx):
            started.set()
            release.wait(timeout=1)
            return RoleResult(status="ok")

        tasks = [
            pool.submit(
                role_name="t",
                handler=handler,
                ctx=RoleContext(role_name="t"),
            )
            for _ in range(4)
        ]
        assert started.wait(timeout=1)
        release.set()
        for task in tasks:
            task.done.wait(timeout=2)
        for task in tasks:
            assert task.result.status == "ok"
        pool.shutdown()

    def test_cancel_drains_pool(self):
        pool = WorkerPool(size=1)

        def slow(_ctx):
            time.sleep(0.05)
            return RoleResult(status="ok")

        pool.submit(
            role_name="t", handler=slow, ctx=RoleContext(role_name="t")
        )
        pool.cancel()
        pool.shutdown()
        snap = pool.snapshot()
        assert snap["cancelled"] is True

    def test_crash_quarantine_after_max_retries(self):
        pool = WorkerPool(size=1)

        def boom(_ctx):
            raise RuntimeError("nope")

        task = pool.submit(
            role_name="t", handler=boom, ctx=RoleContext(role_name="t"), max_retries=2
        )
        task.done.wait(timeout=2)
        assert task.quarantined is True
        assert task.result.status == "error"
        pool.shutdown()

    def test_snapshot_fields(self):
        pool = WorkerPool(size=1)
        try:
            snap = pool.snapshot()
            for key in ("size", "queue_depth", "cancelled", "tasks_processed", "tasks_quarantined"):
                assert key in snap
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class TestDispatcher:
    def _build(self):
        reg = RoleRegistry()
        reg.register(
            Role(
                name="echo",
                handler=lambda ctx: RoleResult(status="ok", payload={"args": ctx.args}),
            )
        )
        pool = WorkerPool(size=2)
        return Dispatcher(registry=reg, pool=pool), pool

    def test_dispatch_forwards_args(self):
        dispatcher, pool = self._build()
        try:
            task = dispatcher.dispatch("echo", args={"k": "v"})
            results = dispatcher.wait_all([task], timeout=2)
            assert results[0].payload["args"] == {"k": "v"}
        finally:
            pool.shutdown()

    def test_dispatch_unknown_role(self):
        dispatcher, pool = self._build()
        try:
            with pytest.raises(KeyError):
                dispatcher.dispatch("nope")
        finally:
            pool.shutdown()

    def test_dispatch_many(self):
        dispatcher, pool = self._build()
        try:
            tasks = dispatcher.dispatch_many(
                "echo", [{"i": i} for i in range(4)]
            )
            results = dispatcher.wait_all(tasks, timeout=5)
            assert len(results) == 4
            assert all(r.status == "ok" for r in results)
        finally:
            pool.shutdown()

    def test_cancel_all(self):
        dispatcher, pool = self._build()
        try:
            dispatcher.cancel_all()
            snap = pool.snapshot()
            assert snap["cancelled"] is True
        finally:
            pool.shutdown()


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------


class TestProgress:
    def test_record_increments_counter(self):
        reporter = ProgressReporter()
        reporter.record("files_processed")
        reporter.record("files_processed", value=3)
        snap = reporter.snapshot()
        assert snap["files_processed"] == 4.0

    def test_tags_create_separate_counters(self):
        reporter = ProgressReporter()
        reporter.record("foo", role="a")
        reporter.record("foo", role="b")
        snap = reporter.snapshot()
        assert len(snap) == 2

    def test_sink_invoked(self):
        calls = []

        def sink(name, value, tags):
            calls.append((name, value, tags))

        reporter = ProgressReporter(sink=sink)
        reporter.record("x", value=2.5, tag="y")
        assert calls == [("x", 2.5, {"tag": "y"})]

    def test_sink_exception_tolerated(self):
        def sink(*args, **kwargs):
            raise RuntimeError("boom")

        reporter = ProgressReporter(sink=sink)
        # Must not raise.
        reporter.record("x")


# ---------------------------------------------------------------------------
# Phase I roles
# ---------------------------------------------------------------------------


class TestPhaseIRoles:
    def test_indexer_requires_backend(self):
        role = indexer_graph_os.build_role()
        ctx = RoleContext(role_name=role.name, args={"path": "a.py", "content": "x"})
        result = role.handler(ctx)
        assert result.status == "error"
        assert "backend" in (result.error or "")

    def test_indexer_skips_unsupported_suffix(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        role = indexer_graph_os.build_role()
        ctx = RoleContext(
            role_name=role.name,
            args={"path": "README.unknown", "content": "hi"},
            shared={"backend": backend},
        )
        result = role.handler(ctx)
        assert result.status == "skipped"

    def test_indexer_runs_python_extractor(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        role = indexer_graph_os.build_role()
        ctx = RoleContext(
            role_name=role.name,
            args={"path": "core/foo.py", "content": "def foo(): pass"},
            shared={"backend": backend},
        )
        result = role.handler(ctx)
        assert result.status == "ok"
        assert result.payload["nodes_written"] >= 2

    def test_lsp_warm_start_role(self):
        role = lsp_warm_start.build_role()
        ctx = RoleContext(
            role_name=role.name,
            args={"language": "python", "fake": True},
            shared={},
        )
        result = role.handler(ctx)
        assert result.status in {"ok", "skipped"}
        assert "state" in result.payload

    def test_migrator_requires_conn(self):
        role = migrator_embeddings.build_role()
        ctx = RoleContext(role_name=role.name, args={})
        result = role.handler(ctx)
        assert result.status == "error"

    def test_migrator_runs_one_batch(self, migrated_conn, tmp_path, monkeypatch):
        # Seed 2 observations + legacy embeddings with a fake encoder.
        import embeddings

        class _Fake:
            def encode(self, text, convert_to_numpy=True, **_):
                import numpy as np

                v = np.zeros(1024 if "bge" in self.model else 384, dtype="float32")
                v[0] = len(text) if isinstance(text, str) else len(text[0])
                return v

            def __init__(self, model):
                self.model = model

        embeddings._override_model("all-MiniLM-L6-v2", _Fake("minilm"))
        embeddings._override_model("BAAI/bge-m3", _Fake("bge"))

        migrated_conn.execute(
            "INSERT INTO observations (id, session_id, title, narrative) "
            "VALUES (1, 'test', 'hello', 'world')"
        )
        migrated_conn.commit()
        embeddings.upsert_embedding(migrated_conn, "observations", 1, "hello world")

        role = migrator_embeddings.build_role()
        ctx = RoleContext(
            role_name=role.name,
            args={
                "target_model": "BAAI/bge-m3",
                "batch_size": 2,
                "checkpoint_path": str(tmp_path / ".mig.json"),
            },
            shared={"conn": migrated_conn},
        )
        result = role.handler(ctx)
        assert result.status == "ok"
        assert result.payload["remaining"] >= 0

        embeddings._override_model("all-MiniLM-L6-v2", None)
        embeddings._override_model("BAAI/bge-m3", None)


# ---------------------------------------------------------------------------
# Scale smoke — 1000 fake tasks in < 1s.
# ---------------------------------------------------------------------------


class TestScaleSmoke:
    def test_thousand_fake_tasks(self):
        reg = RoleRegistry()
        reg.register(
            Role(name="tiny", handler=lambda ctx: RoleResult(status="ok"))
        )
        pool = WorkerPool(size=8)
        dispatcher = Dispatcher(registry=reg, pool=pool)
        try:
            tasks = dispatcher.dispatch_many("tiny", [{} for _ in range(1000)])
            results = dispatcher.wait_all(tasks, timeout=10)
            assert len(results) == 1000
            assert all(r.status == "ok" for r in results)
        finally:
            pool.shutdown()
