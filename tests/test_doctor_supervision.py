"""supervision.policy_reachable doctor check (TASK-1001).

Fast + hermetic: a settings file plus a throwaway project tree, calling the check
directly. Exists because the only way to discover that `model_routing.enabled`
was inert used to be a hand-written SQL query against formula_dispatches.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from cli._doctor_supervision import _check_supervision_policy
from cli.doctor import SEV_PASS, SEV_WARN


def _state(tmp_path: Path, routing: dict | None) -> Path:
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    if routing is not None:
        (state / "hub-settings.json").write_text(
            json.dumps({"model_routing": routing}), encoding="utf-8"
        )
    return state


def _project(tmp_path: Path, *, trigger: bool, adapters: tuple[str, ...]) -> Path:
    project = tmp_path / "proj"
    hooks = project / "src" / "core" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    if trigger:
        (hooks / "resolve-supervise-route.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    for adapter in adapters:
        target = project / "src" / "adapters" / adapter
        target.mkdir(parents=True, exist_ok=True)
        (target / "adapter.yaml").write_text(f"id: {adapter}\n", encoding="utf-8")
    return project


def _run(project: Path, state: Path):
    report = SimpleNamespace(checks=[])
    _check_supervision_policy(project, state, report)
    return report.checks[-1]


def test_disabled_policy_is_a_pass_not_a_nag(tmp_path: Path) -> None:
    result = _run(
        _project(tmp_path, trigger=True, adapters=("claude",)),
        _state(tmp_path, {"enabled": False}),
    )
    assert result.severity == SEV_PASS
    assert "disabled" in result.message


def test_absent_settings_is_a_pass(tmp_path: Path) -> None:
    result = _run(_project(tmp_path, trigger=True, adapters=("claude",)), _state(tmp_path, None))
    assert result.severity == SEV_PASS


def test_enabled_and_wired_reports_the_policy(tmp_path: Path) -> None:
    result = _run(
        _project(tmp_path, trigger=True, adapters=("claude", "codex")),
        _state(
            tmp_path,
            {
                "enabled": True,
                "mode": "adaptive",
                "complexity_threshold": "COMPLEX",
                "roles": {"reviewer": {"adapter": "codex"}},
            },
        ),
    )
    assert result.severity == SEV_PASS
    assert "mode=adaptive" in result.message
    assert "threshold=COMPLEX" in result.message
    assert "pinned roles=1" in result.message


def test_enabled_without_the_trigger_warns(tmp_path: Path) -> None:
    # The exact defect: the policy is announced but nothing applies it.
    result = _run(
        _project(tmp_path, trigger=False, adapters=("claude",)),
        _state(tmp_path, {"enabled": True}),
    )
    assert result.severity == SEV_WARN
    assert "never applied" in result.message


def test_role_pinned_to_a_missing_adapter_warns(tmp_path: Path) -> None:
    # A policy the dispatcher can never satisfy is a silent outage.
    result = _run(
        _project(tmp_path, trigger=True, adapters=("claude",)),
        _state(tmp_path, {"enabled": True, "roles": {"reviewer": {"adapter": "gemini"}}}),
    )
    assert result.severity == SEV_WARN
    assert "reviewer→gemini" in result.message


def test_role_without_an_adapter_is_not_counted_as_pinned(tmp_path: Path) -> None:
    result = _run(
        _project(tmp_path, trigger=True, adapters=("claude",)),
        _state(tmp_path, {"enabled": True, "roles": {"reviewer": {"model": "x"}}}),
    )
    assert result.severity == SEV_PASS
    assert "pinned roles=0" in result.message
