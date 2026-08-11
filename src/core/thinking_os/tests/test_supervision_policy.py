from __future__ import annotations

import asyncio
import json
import sqlite3
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
