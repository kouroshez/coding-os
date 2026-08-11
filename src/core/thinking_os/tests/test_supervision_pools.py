from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

from thinking_os import dispatcher, supervision
from thinking_os.adapter_registry import AdapterRecord


def _health_db(path: Path) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE adapter_health (
                adapter_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                failure_count INTEGER NOT NULL DEFAULT 0,
                cooldown_until REAL,
                probe_lease_until REAL,
                reason TEXT,
                updated_at REAL NOT NULL
            );
            """
        )
    return path


def _record(tmp_path: Path, adapter_id: str) -> AdapterRecord:
    path = tmp_path / adapter_id
    path.mkdir(exist_ok=True)
    return AdapterRecord(
        adapter_id,
        path,
        {
            "id": adapter_id,
            "runtime_entrypoints": {"dispatch": "sdk_dispatcher.py", "capabilities": ["dispatch"]},
            "models": [],
        },
    )


def _settings(project: Path, fallback: str = "next_eligible") -> None:
    state = project / ".coding-os"
    state.mkdir(exist_ok=True)
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"fallback_policy":"' + fallback + '"}}',
        encoding="utf-8",
    )


def _pooled_record(tmp_path: Path) -> AdapterRecord:
    path = tmp_path / "claude"
    path.mkdir(exist_ok=True)
    return AdapterRecord(
        "claude",
        path,
        {
            "id": "claude",
            "runtime_entrypoints": {"dispatch": "sdk.py", "capabilities": ["dispatch"]},
            "models": [
                {"id": "big", "bucket": "opus-4x", "default": True},
                {"id": "small", "bucket": "haiku"},
                {"id": "unpooled"},
            ],
        },
    )


def test_capacity_is_keyed_per_declared_model_pool(tmp_path: Path) -> None:
    record = _pooled_record(tmp_path)

    assert supervision.capacity_key(record, "big") == "claude:opus-4x"
    assert supervision.capacity_key(record, "small") == "claude:haiku"
    # A model with no declared pool, and an unknown model, fall back to treating
    # the adapter as one pool — exactly the pre-existing behaviour.
    assert supervision.capacity_key(record, "unpooled") == "claude"
    assert supervision.capacity_key(record, None) == "claude"


def test_one_limited_pool_does_not_take_the_others_out_of_service(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path, fallback="fail_closed")
    record = _pooled_record(tmp_path)
    used: list[str] = []

    class Runtime:
        name = "claude-sdk"

        async def dispatch(self, request):
            used.append(request.model or "")
            if request.model == "big":
                return dispatcher.DispatchResult(
                    formula_id=request.formula_id,
                    status="error",
                    error="usage limit",
                    error_category="capacity",
                    retryable=True,
                    retry_after_s=600,
                    outcome="known_failed",
                    dispatcher_name=self.name,
                )
            return dispatcher.DispatchResult(
                formula_id=request.formula_id, status="ok", dispatcher_name=self.name
            )

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: [record])
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())

    def run(model: str):
        return asyncio.run(
            dispatcher.dispatch_request(
                dispatcher.DispatchRequest(
                    formula_id="architect",
                    agent_file="a.md",
                    prompt="p",
                    adapter="claude",
                    model=model,
                    cwd=str(tmp_path),
                ),
                db_path,
            )
        )

    assert run("big").error_category == "capacity"
    assert supervision.health_snapshot(db_path)["claude:opus-4x"]["state"] == "cooling_down"

    # The provider meters these pools separately, so the cheap model is still
    # fully available — blocking it would delete capacity that provably exists.
    assert run("small").status == "ok"
    assert used == ["big", "small"]

    # And the limited pool stays shut.
    assert run("big").error_category == "capacity"
    assert used == ["big", "small"]


def test_hub_summary_reports_the_worst_pool_and_the_soonest_recovery(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "claude:opus-4x",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=900,
    )
    supervision.record_result(
        db_path,
        "claude:haiku",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=60,
    )
    supervision.record_result(db_path, "codex", success=True)

    summary = supervision.adapter_health(supervision.health_snapshot(db_path), "claude")

    assert summary["state"] == "cooling_down"
    assert 0 < summary["retry_after_s"] <= 60
    assert summary["limited_buckets"] == ["claude:haiku", "claude:opus-4x"]
    assert supervision.adapter_health(supervision.health_snapshot(db_path), "codex")["state"] == (
        "healthy"
    )


def test_expired_cooldown_is_not_reported_as_still_cooling(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "claude",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=30,
    )

    assert supervision.health_snapshot(db_path)["claude"]["state"] == "cooling_down"

    later = supervision.health_snapshot(db_path, now=time.time() + 60)

    assert later["claude"]["state"] == "healthy"
    assert later["claude"]["retry_after_s"] == 0


def test_clear_health_removes_every_pool_of_one_adapter(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    for scope in ("claude", "claude:opus-4x", "claude:haiku", "codex"):
        supervision.record_result(
            db_path,
            scope,
            success=False,
            error_category="capacity",
            retryable=True,
            retry_after_s=300,
        )

    assert supervision.clear_health(db_path, "claude") is True

    assert set(supervision.health_snapshot(db_path)) == {"codex"}
