from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path

from thinking_os import _supervision_policy as policy_module, dispatcher, supervision
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


def _rich_record(tmp_path: Path, adapter_id: str, manifest: dict) -> AdapterRecord:
    path = tmp_path / adapter_id
    path.mkdir(exist_ok=True)
    return AdapterRecord(adapter_id, path, {"id": adapter_id, **manifest})


def _catalog_records(tmp_path: Path) -> list[AdapterRecord]:
    return [
        _rich_record(
            tmp_path,
            "rich",
            {
                "runtime_entrypoints": {
                    "capabilities": ["dispatch", "model_selection", "effort_selection"]
                },
                "models": [{"id": "big"}, {"id": "small"}],
                "efforts": ["low", "high"],
            },
        ),
        _rich_record(
            tmp_path,
            "freeform",
            {
                "runtime_entrypoints": {"capabilities": ["dispatch", "model_selection"]},
                "models": [],
            },
        ),
    ]


def test_write_time_validation_rejects_targets_dispatch_could_never_satisfy(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".coding-os").mkdir()
    monkeypatch.setattr(policy_module, "eligible_records", lambda _root: _catalog_records(tmp_path))

    for patch, expected in (
        ({"roles": {"reviewer": {"adapter": "ghost"}}}, "unknown adapter"),
        ({"roles": {"reviewer": {"adapter": "rich", "model": "huge"}}}, "is not declared"),
        ({"roles": {"reviewer": {"adapter": "freeform", "effort": "high"}}}, "is not supported"),
        ({"orchestrator": {"adapter": "rich", "effort": "extreme"}}, "is not supported"),
    ):
        try:
            supervision.update_policy(tmp_path, patch)
        except ValueError as exc:
            assert expected in str(exc)
        else:
            raise AssertionError(f"{patch} should have been rejected")


def test_write_time_validation_accepts_free_form_model_on_an_empty_catalog(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".coding-os").mkdir()
    monkeypatch.setattr(policy_module, "eligible_records", lambda _root: _catalog_records(tmp_path))

    policy = supervision.update_policy(
        tmp_path, {"roles": {"reviewer": {"adapter": "freeform", "model": "anything-goes"}}}
    )

    assert policy["roles"]["reviewer"]["model"] == "anything-goes"


def test_write_time_validation_only_covers_the_patched_targets(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    # A role pinned to an adapter that was later uninstalled must not lock the
    # operator out of every other edit.
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"roles":{"reviewer":{"adapter":"gone"}}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(policy_module, "eligible_records", lambda _root: _catalog_records(tmp_path))

    policy = supervision.update_policy(tmp_path, {"max_parallel": 5})

    assert policy["max_parallel"] == 5
    assert policy["roles"]["reviewer"]["adapter"] == "gone"


def test_entrypoint_module_is_cached_until_the_file_changes(tmp_path: Path) -> None:
    from thinking_os import adapter_registry

    adapter = tmp_path / "cached"
    adapter.mkdir()
    runtime = adapter / "runtime.py"
    runtime.write_text("VALUE = 1\n", encoding="utf-8")
    record = AdapterRecord(
        "cached",
        adapter,
        {"id": "cached", "runtime_entrypoints": {"dispatch": "runtime.py"}},
    )
    adapter_registry._MODULE_CACHE.pop(("cached", "dispatch"), None)

    first = adapter_registry.load_entrypoint_module(record, "dispatch")
    assert adapter_registry.load_entrypoint_module(record, "dispatch") is first

    import os

    runtime.write_text("VALUE = 2\n", encoding="utf-8")
    os.utime(runtime, (0, 0))
    reloaded = adapter_registry.load_entrypoint_module(record, "dispatch")

    assert reloaded is not first
    assert reloaded.VALUE == 2


def test_probe_lease_outlives_the_dispatch_it_guards(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "claude",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=60,
    )
    after_cooldown = time.time() + 120

    probe = supervision.check_capacity(db_path, "claude", now=after_cooldown, lease_seconds=300)
    assert probe.allowed and probe.probe

    # A formula dispatch routinely runs for minutes; a second caller must not be
    # let through while the first probe is still in flight.
    for elapsed in (45, 120, 299):
        concurrent = supervision.check_capacity(
            db_path, "claude", now=after_cooldown + elapsed, lease_seconds=300
        )
        assert not concurrent.allowed, f"second probe admitted {elapsed}s into the first"
        assert "probe already running" in concurrent.reason


def test_failed_probe_releases_its_lease_instead_of_stalling_recovery(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "claude",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=60,
    )
    after_cooldown = time.time() + 120
    supervision.check_capacity(db_path, "claude", now=after_cooldown, lease_seconds=300)

    # The probe died for an unrelated reason — that says nothing about capacity.
    supervision.record_result(
        db_path, "claude", success=False, error_category="provider", retryable=False
    )

    retry = supervision.check_capacity(db_path, "claude", now=after_cooldown + 1, lease_seconds=300)

    # Settled back to healthy rather than pinned to half_open: the cooldown had
    # already expired and a provider error is no evidence of a capacity problem.
    assert retry.allowed and not retry.probe and retry.state == "healthy"
    assert supervision.health_snapshot(db_path)["claude"]["state"] == "healthy"


def test_exhausted_fleet_reports_the_soonest_recovery(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path)
    records = [_record(tmp_path, "slow"), _record(tmp_path, "quick")]
    supervision.record_result(
        db_path,
        "slow",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=3000,
    )
    supervision.record_result(
        db_path, "quick", success=False, error_category="capacity", retryable=True, retry_after_s=30
    )

    class Runtime:
        name = "never-called"

        async def dispatch(self, request):
            raise AssertionError("a cooling adapter must not be dispatched to")

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="reviewer",
        agent_file="agent.md",
        prompt="review",
        adapter="slow",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, db_path))

    assert result.error_category == "capacity"
    # 'slow' was the requested target and 'quick' the fallback; the caller needs
    # the soonest wait across the fleet, not the last adapter checked.
    assert result.retry_after_s is not None and result.retry_after_s <= 31
    assert "every eligible model pool is at capacity" in (result.error or "")
    assert "quick" in (result.error or "") and "slow" in (result.error or "")


def test_a_raising_adapter_does_not_strand_the_recovery_probe(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path, fallback="fail_closed")
    records = [_record(tmp_path, "claude")]
    supervision.record_result(
        db_path,
        "claude",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=1,
    )

    class Runtime:
        name = "claude-sdk"

        async def dispatch(self, request):
            raise RuntimeError("adapter blew up mid-probe")

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="reviewer",
        agent_file="a.md",
        prompt="p",
        adapter="claude",
        timeout_s=3600,
        cwd=str(tmp_path),
    )
    time.sleep(1.1)

    try:
        asyncio.run(dispatcher.dispatch_request(request, db_path))
    except RuntimeError:
        pass
    else:
        raise AssertionError("the adapter's exception must propagate")

    # Without the release the lease would hold for the full timeout_s.
    assert supervision.check_capacity(db_path, "claude").allowed
