from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path

from thinking_os import dispatcher, supervision
from thinking_os.adapter_registry import AdapterRecord, _resolve_adapters_dir, load_adapter_records


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


def test_future_adapter_is_discovered_without_core_literal(tmp_path: Path) -> None:
    adapter = tmp_path / "future"
    adapter.mkdir()
    (adapter / "adapter.yaml").write_text(
        "id: future\nruntime_entrypoints:\n  dispatch: runtime.py\n  capabilities: [dispatch]\n",
        encoding="utf-8",
    )
    (adapter / "runtime.py").write_text(
        "def build_dispatcher():\n    return None\n", encoding="utf-8"
    )

    records = load_adapter_records(tmp_path)

    assert records["future"].capabilities == {"dispatch"}
    assert records["future"].entrypoints["dispatch"] == "runtime.py"


def test_installed_package_layout_resolves_sibling_adapters(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    module_path = site_packages / "thinking_os" / "adapter_registry.py"
    module_path.parent.mkdir(parents=True)
    module_path.touch()
    adapters = site_packages / "adapters"
    adapters.mkdir()

    assert _resolve_adapters_dir(module_path) == adapters


def test_capacity_cooldown_persists_and_recovers_with_one_probe(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    policy = {
        **supervision.DEFAULT_MODEL_ROUTING,
        "cooldown": {"default_seconds": 10, "maximum_seconds": 40},
    }
    supervision.record_result(
        db_path,
        "future",
        success=False,
        error_category="capacity",
        retryable=True,
        reason="usage limit",
        policy=policy,
        now=100,
    )

    blocked = supervision.check_capacity(db_path, "future", now=105)
    probe = supervision.check_capacity(db_path, "future", now=111)
    concurrent = supervision.check_capacity(db_path, "future", now=112)

    assert blocked.allowed is False and blocked.retry_after_s == 5
    assert probe.allowed is True and probe.probe is True
    assert concurrent.allowed is False and concurrent.state == "half_open"

    supervision.record_result(db_path, "future", success=True, now=113)
    assert supervision.check_capacity(db_path, "future", now=114).state == "healthy"


def test_provider_retry_after_wins_over_default_cooldown(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "future",
        success=False,
        error_category="capacity",
        retryable=True,
        retry_after_s=90,
        now=100,
    )

    assert supervision.check_capacity(db_path, "future", now=101).retry_after_s == 89


def test_capacity_reason_is_redacted_before_persistence(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    supervision.record_result(
        db_path,
        "future",
        success=False,
        error_category="capacity",
        retryable=True,
        reason="rate limit api_key=sk-1234567890abcdefghijkl",
        now=100,
    )

    reason = supervision.health_snapshot(db_path, now=101)["future"]["reason"]
    assert "sk-1234567890abcdefghijkl" not in reason


def test_known_capacity_failure_falls_back_to_next_adapter(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path)
    records = [_record(tmp_path, "first"), _record(tmp_path, "second")]
    calls: list[str] = []

    class Runtime:
        def __init__(self, adapter_id: str):
            self.adapter_id = adapter_id
            self.name = f"{adapter_id}-sdk"

        async def dispatch(self, request):
            calls.append(self.adapter_id)
            if self.adapter_id == "first":
                return dispatcher.DispatchResult(
                    formula_id=request.formula_id,
                    status="error",
                    error="usage limit",
                    error_category="capacity",
                    retryable=True,
                    outcome="known_failed",
                    dispatcher_name=self.name,
                )
            return dispatcher.DispatchResult(
                formula_id=request.formula_id,
                status="ok",
                output_json={"evidence": True},
                dispatcher_name=self.name,
            )

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(
        dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime(agent)
    )
    request = dispatcher.DispatchRequest(
        formula_id="analyst",
        agent_file="agent.md",
        prompt="analyze",
        adapter="first",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, db_path))

    assert result.status == "ok"
    assert result.output_json["_meta"]["adapter"] == "second"
    assert calls == ["first", "second"]

    calls.clear()
    result = asyncio.run(dispatcher.dispatch_request(request, db_path))
    assert result.status == "ok"
    assert result.output_json["_meta"]["adapter"] == "second"
    assert calls == ["second"]


def test_unknown_failure_is_never_replayed(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path)
    records = [_record(tmp_path, "first"), _record(tmp_path, "second")]
    calls: list[str] = []

    class Runtime:
        name = "test-sdk"

        async def dispatch(self, request):
            calls.append(request.adapter)
            return dispatcher.DispatchResult(
                formula_id=request.formula_id,
                status="error",
                error="connection dropped",
                error_category="provider",
                outcome="unknown",
                dispatcher_name=self.name,
            )

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="implementer",
        agent_file="agent.md",
        prompt="write",
        adapter="first",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, db_path))

    assert result.status == "error"
    assert calls == ["first"]


def test_single_configured_adapter_is_the_implicit_default(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path, fallback="fail_closed")
    records = [_record(tmp_path, "only")]

    class Runtime:
        name = "only-sdk"

        async def dispatch(self, request):
            return dispatcher.DispatchResult(
                formula_id=request.formula_id,
                status="ok",
                output_json={},
                dispatcher_name=self.name,
            )

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(dispatcher, "_detect_agent", lambda: "unconfigured-host")
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="reviewer",
        agent_file="agent.md",
        prompt="review",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, db_path))

    assert result.status == "ok"
    assert result.output_json["_meta"]["adapter"] == "only"


def test_disabled_policy_uses_existing_dispatch_path_without_health_state(
    tmp_path: Path, monkeypatch
) -> None:
    class Runtime:
        async def dispatch(self, request):
            return dispatcher.DispatchResult(
                formula_id=request.formula_id,
                status="skipped",
                dispatcher_name="existing",
            )

    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="analyst",
        agent_file="agent.md",
        prompt="analyze",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, tmp_path / "missing.db"))

    assert result.dispatcher_name == "existing"
    assert not (tmp_path / "missing.db").exists()


def test_orchestrator_target_is_the_default_for_unconfigured_roles(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"orchestrator":{"adapter":"first",'
        '"model":"large","effort":"high"},"roles":{"reviewer":{"model":"small"}}}}',
        encoding="utf-8",
    )

    assert supervision.role_policy("architect", tmp_path) == {
        "adapter": "first",
        "model": "large",
        "effort": "high",
    }
    # A role entry overrides field by field — pinning one model must not drop
    # the orchestrator's adapter and effort.
    assert supervision.role_policy("reviewer", tmp_path) == {
        "adapter": "first",
        "model": "small",
        "effort": "high",
    }


def test_adaptive_mode_skips_policy_below_the_complexity_gate(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"mode":"adaptive",'
        '"complexity_threshold":"COMPLEX","orchestrator":{"model":"large"}}}',
        encoding="utf-8",
    )

    assert supervision.role_policy("architect", tmp_path, complexity="COMPLICATED")["model"] == ""
    assert supervision.role_policy("architect", tmp_path, complexity="COMPLEX")["model"] == "large"
    assert supervision.role_policy("architect", tmp_path, complexity="CHAOTIC")["model"] == "large"
    # An unclassified request is below every gate rather than escalated.
    assert supervision.role_policy("architect", tmp_path, complexity="")["model"] == ""


def test_explicit_mode_applies_policy_without_a_complexity(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"orchestrator":{"model":"large"}}}',
        encoding="utf-8",
    )

    assert supervision.role_policy("architect", tmp_path, complexity="")["model"] == "large"


def test_adaptive_gate_below_threshold_bypasses_the_supervisor(tmp_path: Path, monkeypatch) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"mode":"adaptive","complexity_threshold":"COMPLEX"}}',
        encoding="utf-8",
    )

    class Runtime:
        name = "session"

        async def dispatch(self, request):
            return dispatcher.DispatchResult(
                formula_id=request.formula_id,
                status="ok",
                dispatcher_name="existing",
            )

    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="analyst",
        agent_file="agent.md",
        prompt="analyze",
        complexity="CLEAR",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, tmp_path / "missing.db"))

    assert result.dispatcher_name == "existing"
    assert not (tmp_path / "missing.db").exists()


def test_suggest_mode_returns_the_route_without_executing(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"mode":"suggest"}}', encoding="utf-8"
    )
    records = [_record(tmp_path, "only")]
    calls: list[str] = []

    class Runtime:
        name = "only-sdk"

        async def dispatch(self, request):
            calls.append(request.formula_id)
            return dispatcher.DispatchResult(formula_id=request.formula_id, status="ok")

    monkeypatch.setattr(supervision, "eligible_records", lambda _root: records)
    monkeypatch.setattr(dispatcher, "get_dispatcher", lambda agent=None, request=None: Runtime())
    request = dispatcher.DispatchRequest(
        formula_id="reviewer",
        agent_file="agent.md",
        prompt="review",
        adapter="only",
        cwd=str(tmp_path),
    )

    result = asyncio.run(dispatcher.dispatch_request(request, db_path))

    assert result.status == "skipped"
    assert result.output_json["proposed_route"]["adapter"] == "only"
    assert calls == []
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM adapter_health").fetchone()[0] == 0


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
    monkeypatch.setattr(supervision, "eligible_records", lambda _root: _catalog_records(tmp_path))

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
    monkeypatch.setattr(supervision, "eligible_records", lambda _root: _catalog_records(tmp_path))

    policy = supervision.update_policy(
        tmp_path, {"roles": {"reviewer": {"adapter": "freeform", "model": "anything-goes"}}}
    )

    assert policy["roles"]["reviewer"]["model"] == "anything-goes"


def test_write_time_validation_only_covers_the_patched_targets(
    tmp_path: Path, monkeypatch
) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    # A role pinned to an adapter that was later uninstalled must not lock the
    # operator out of every other edit.
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"roles":{"reviewer":{"adapter":"gone"}}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(supervision, "eligible_records", lambda _root: _catalog_records(tmp_path))

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
        db_path, "claude", success=False, error_category="capacity", retryable=True, retry_after_s=60
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
        db_path, "claude", success=False, error_category="capacity", retryable=True, retry_after_s=60
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
        db_path, "slow", success=False, error_category="capacity", retryable=True, retry_after_s=3000
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
        db_path, "claude:opus-4x", success=False, error_category="capacity",
        retryable=True, retry_after_s=900,
    )
    supervision.record_result(
        db_path, "claude:haiku", success=False, error_category="capacity",
        retryable=True, retry_after_s=60,
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
        db_path, "claude", success=False, error_category="capacity",
        retryable=True, retry_after_s=30,
    )

    assert supervision.health_snapshot(db_path)["claude"]["state"] == "cooling_down"

    later = supervision.health_snapshot(db_path, now=time.time() + 60)

    assert later["claude"]["state"] == "healthy"
    assert later["claude"]["retry_after_s"] == 0


def test_clear_health_removes_every_pool_of_one_adapter(tmp_path: Path) -> None:
    db_path = _health_db(tmp_path / "health.db")
    for scope in ("claude", "claude:opus-4x", "claude:haiku", "codex"):
        supervision.record_result(
            db_path, scope, success=False, error_category="capacity",
            retryable=True, retry_after_s=300,
        )

    assert supervision.clear_health(db_path, "claude") is True

    assert set(supervision.health_snapshot(db_path)) == {"codex"}


def test_a_raising_adapter_does_not_strand_the_recovery_probe(tmp_path: Path, monkeypatch) -> None:
    db_path = _health_db(tmp_path / "health.db")
    _settings(tmp_path, fallback="fail_closed")
    records = [_record(tmp_path, "claude")]
    supervision.record_result(
        db_path, "claude", success=False, error_category="capacity",
        retryable=True, retry_after_s=1,
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


def test_complexity_rank_orders_the_cynefin_levels() -> None:
    ranks = [supervision.complexity_rank(level) for level in supervision.COMPLEXITY_ORDER]

    assert ranks == sorted(ranks) and len(set(ranks)) == len(ranks)
    assert supervision.complexity_rank("complicated") == supervision.complexity_rank("COMPLICATED")
    assert supervision.complexity_rank("nonsense") == -1


def test_partial_policy_is_deep_normalized(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(
        '{"model_routing":{"enabled":true,"cooldown":{"default_seconds":90}}}',
        encoding="utf-8",
    )

    policy = supervision.load_policy(tmp_path)

    assert policy["cooldown"] == {"default_seconds": 90, "maximum_seconds": 3600}
    assert policy["orchestrator"] == {"adapter": "", "model": "", "effort": ""}


def test_policy_update_preserves_foreign_sections_and_permissions(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    path = state / "hub-settings.json"
    path.write_text(
        json.dumps({"foreign": {"keep": True}, "model_routing": {"enabled": False}}),
        encoding="utf-8",
    )

    policy = supervision.update_policy(
        tmp_path,
        {
            "enabled": True,
            "mode": "adaptive",
            "roles": {"reviewer": {"adapter": "claude", "effort": "high"}},
        },
    )

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert policy["roles"]["reviewer"] == {
        "adapter": "claude",
        "model": "",
        "effort": "high",
    }
    assert stored["foreign"] == {"keep": True}
    assert path.stat().st_mode & 0o777 == 0o600


def test_policy_update_rejects_corrupt_file_without_overwrite(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    path = state / "hub-settings.json"
    path.write_text("not-json", encoding="utf-8")

    try:
        supervision.update_policy(tmp_path, {"enabled": True})
    except ValueError as exc:
        assert "refusing to overwrite" in str(exc)
    else:
        raise AssertionError("corrupt settings should fail closed")

    assert path.read_text(encoding="utf-8") == "not-json"
