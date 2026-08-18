"""Tier aliases resolve against the descriptor before validation (TASK-1012).

Roles declare `model_pref: {complicated: sonnet}` while adapter descriptors
declare concrete ids. The supervisor validated the routed value against the id
list first, so every alias was rejected as undeclared — a live dispatch failed
with `model 'sonnet' is not declared by adapter 'claude'` and NO supervised
dispatch could ever run. Validation now resolves first.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from thinking_os.dispatcher_helpers import resolve_model_alias

_ADAPTERS = Path(__file__).resolve().parents[1] / "src" / "adapters"


def _descriptor(agent: str) -> tuple[list[str], str | None]:
    data = yaml.safe_load((_ADAPTERS / agent / "adapter.yaml").read_text(encoding="utf-8")) or {}
    models = [m for m in (data.get("models") or []) if isinstance(m, dict) and m.get("id")]
    return [str(m["id"]) for m in models], next(
        (str(m["id"]) for m in models if m.get("default")), None
    )


class TestAgainstTheRealClaudeDescriptor:
    @pytest.mark.parametrize("alias", ["sonnet", "opus", "haiku", "fable"])
    def test_every_tier_alias_resolves_to_a_declared_id(self, alias: str) -> None:
        ids, default = _descriptor("claude")
        assert resolve_model_alias(alias, ids, default) in ids

    def test_the_regression_case(self) -> None:
        ids, default = _descriptor("claude")
        assert resolve_model_alias("sonnet", ids, default) == "claude-sonnet-5"

    def test_a_concrete_id_passes_through_untouched(self) -> None:
        ids, default = _descriptor("claude")
        assert resolve_model_alias("claude-opus-4-8", ids, default) == "claude-opus-4-8"

    def test_role_model_prefs_are_all_resolvable(self) -> None:
        # The prefs and the descriptor are edited independently; this is what
        # catches a role pinned to a tier the adapter stopped declaring.
        ids, default = _descriptor("claude")
        agents = Path(__file__).resolve().parents[1] / "src/core/thinking_os/agents"
        seen = 0
        for agent_file in agents.glob("*.md"):
            text = agent_file.read_text(encoding="utf-8")
            if "model_pref:" not in text:
                continue
            front = yaml.safe_load(text.split("---")[1]) or {}
            for tier in (front.get("model_pref") or {}).values():
                seen += 1
                assert resolve_model_alias(str(tier), ids, default) in ids, (
                    f"{agent_file.name}: {tier}"
                )
        assert seen > 0, "no model_pref found — the guard would be vacuous"


class TestEdges:
    def test_unknown_alias_falls_back_to_the_default(self) -> None:
        assert resolve_model_alias("nope", ["a-1", "b-2"], "a-1") == "a-1"

    def test_empty_and_none_pass_through(self) -> None:
        assert resolve_model_alias(None, ["a-1"], "a-1") is None
        assert resolve_model_alias("", ["a-1"], "a-1") == ""

    def test_no_default_returns_the_input(self) -> None:
        assert resolve_model_alias("nope", ["a-1"], None) == "nope"
