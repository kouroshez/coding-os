from __future__ import annotations

import asyncio
import sqlite3
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
