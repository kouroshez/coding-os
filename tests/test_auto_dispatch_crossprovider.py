"""Cross-provider auto-dispatch — the trigger that was missing (TASK-1015).

Supervision sat enabled for six days with zero dispatches because nothing called
cos_dispatch_formula_run. These tests pin the selection rule and its guards; the
economics are the reason for the rule: a child rebuilds context (~$0.56, ~50s
measured), so a same-provider spawn costs more for identical capability.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src" / "core" / "hooks" / "_helpers"))

from auto_dispatch import adapter_timeout, cross_provider_roles
from dispatch_summary import summarise

HOOK = _ROOT / "src" / "core" / "hooks" / "auto-dispatch-crossprovider.sh"

_POLICY = {
    "enabled": True,
    "roles": {
        "reviewer": {"adapter": "codex", "model": "gpt-5.6-sol", "effort": ""},
        "security_auditor": {"adapter": "codex", "model": "gpt-5.6-sol", "effort": ""},
        "implementer": {"adapter": "claude", "model": "claude-sonnet-5", "effort": "high"},
        "documenter": {"adapter": "claude", "model": "claude-haiku-4-5", "effort": "low"},
    },
}


class TestSelection:
    def test_only_other_providers_are_dispatched(self) -> None:
        roles = [t["role"] for t in cross_provider_roles(_POLICY, "claude")]
        assert roles == ["reviewer", "security_auditor"]

    def test_same_provider_roles_run_inline(self) -> None:
        # Spawning a sibling of yourself costs more for identical capability.
        roles = [t["role"] for t in cross_provider_roles(_POLICY, "claude")]
        assert "implementer" not in roles and "documenter" not in roles

    def test_the_mirror_case_from_a_codex_session(self) -> None:
        roles = [t["role"] for t in cross_provider_roles(_POLICY, "codex")]
        assert roles == ["documenter", "implementer"]

    def test_carries_model_and_effort_through(self) -> None:
        target = cross_provider_roles(_POLICY, "claude")[0]
        assert target["model"] == "gpt-5.6-sol"
        # codex declares no effort_selection; a pinned effort is a hard error there.
        assert target["effort"] == ""


class TestGuards:
    @pytest.mark.parametrize("session", ["fable", "claude-fable-5", "", "gpt-5.6-sol"])
    def test_a_model_id_in_the_adapter_slot_dispatches_nothing(self, session: str) -> None:
        # `fable` is a MODEL inside the claude adapter. If a model ever reaches
        # this argument every role looks cross-provider and one transition spawns
        # the whole chain — ~$6 instead of ~$0.6. Fail toward spending nothing.
        assert cross_provider_roles(_POLICY, session) == []

    def test_unpinned_roles_are_skipped(self) -> None:
        policy = {"enabled": True, "roles": {"analyst": {"adapter": "", "model": ""}}}
        assert cross_provider_roles(policy, "claude") == []

    def test_malformed_policy_is_inert(self) -> None:
        assert cross_provider_roles({}, "claude") == []
        assert cross_provider_roles({"roles": "nope"}, "claude") == []


class TestAdapterBudget:
    def test_codex_declares_a_longer_budget_than_the_agent_default(self) -> None:
        # A successful codex review measured 123s against a 120s agent default.
        assert (adapter_timeout("codex") or 0) > 123

    def test_claude_defers_to_the_agent_default(self) -> None:
        assert adapter_timeout("claude") is None

    def test_unknown_adapter_defers(self) -> None:
        assert adapter_timeout("nope") is None


class TestSummaryLine:
    def test_names_role_adapter_model_status_and_cost(self) -> None:
        line = summarise(
            [
                json.dumps(
                    {
                        "role": "reviewer",
                        "adapter": "codex",
                        "model": "gpt-5.6-sol",
                        "status": "ok",
                        "cost_usd": 0.31,
                    }
                )
            ]
        )
        assert line == "reviewer@codex/gpt-5.6-sol=ok$0.3100"

    def test_a_failed_run_is_still_reported(self) -> None:
        # A silent failure is what made a broken route look like an idle one.
        line = summarise(
            [json.dumps({"role": "reviewer", "adapter": "codex", "status": "timeout"})]
        )
        assert "timeout" in line

    def test_garbage_lines_are_skipped_not_fatal(self) -> None:
        assert summarise(["", "not json", json.dumps({"role": "x"})]) == "x@?/-=?"


class TestHookGating:
    def _run(self, to: str) -> int:
        payload = {
            "tool_name": "mcp__coding-os__cos_task_move",
            "tool_input": {"task_id": "TASK-TEST", "to": to},
        }
        proc = subprocess.run(
            ["bash", str(HOOK)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=30,
            env={**__import__("os").environ, "COS_AGENT": ""},
        )
        return proc.returncode

    @pytest.mark.parametrize("to", ["testing", "in_progress", "complete", "blocked"])
    def test_never_blocks_the_task_move(self, to: str) -> None:
        # A dispatch that cannot start must never break the transition that
        # triggered it.
        assert self._run(to) == 0


class TestCodexUsageIsCaptured:
    """Codex spend was invisible: the CLI reports usage and the parser dropped it."""

    def _parse(self, events: list[dict]):
        sys.path.insert(0, str(_ROOT / "src"))
        from adapters.codex.sdk_dispatcher import _parse_cli_output

        return _parse_cli_output("\n".join(json.dumps(e) for e in events))

    def test_turn_completed_usage_is_kept(self) -> None:
        _r, _f, usage = self._parse(
            [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
                {"type": "turn.completed", "usage": {"input_tokens": 20690, "output_tokens": 5}},
            ]
        )
        assert usage == {"input_tokens": 20690, "output_tokens": 5}

    def test_absent_usage_is_none_not_a_fabricated_zero(self) -> None:
        # A fabricated 0 would read as "this run was free" in the rollup.
        _r, _f, usage = self._parse([{"type": "turn.completed"}])
        assert usage is None

    def test_the_message_and_failure_channels_still_work(self) -> None:
        response, failure, _u = self._parse(
            [{"type": "item.completed", "item": {"type": "agent_message", "text": "done"}}]
        )
        assert response == "done" and failure is None
