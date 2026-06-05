"""Drift-guard: the agent-memory + thinking_os skills must document MCP tools that exist.

agent-memory rotted to 100% fiction (TASK-116) because nothing tied the skill prose
to the live server. This asserts every (tool, kwarg) pair those skills teach is present
in the registered MCP input schema, and that the former fictional tool names stay gone.
Fails loudly on any future skill<->code drift.
"""

from __future__ import annotations

import asyncio

import pytest

import server

# Tool name as the agent calls it -> kwargs the agent-memory / thinking_os skills document.
DOCUMENTED = {
    "cos_observation_record": {"file_path", "tool_name"},
    "cos_search": {"query", "limit", "memory_type", "min_confidence", "since_days"},
    "cos_details": {"pattern_id", "source"},
    "cos_timeline": {"days", "domain", "limit"},
    "cos_learn_suggest": {"domain", "complexity", "task_type", "limit"},
    "cos_learn_extract": {"min_occurrences"},
    "cos_learn_validate": {"pattern_id", "was_helpful"},
    "cos_learn_feedback": {"min_rework"},
}

FICTIONAL = {"thinking_os_search", "thinking_os_details"}


@pytest.fixture(scope="module")
def registered_props() -> dict[str, set[str]]:
    tools = asyncio.run(server.mcp.list_tools())
    return {t.name: set((t.inputSchema or {}).get("properties", {})) for t in tools}


@pytest.mark.parametrize("tool, kwargs", sorted(DOCUMENTED.items()))
def test_documented_kwargs_exist(registered_props, tool, kwargs):
    assert tool in registered_props, f"skills document {tool} but it is not a registered MCP tool"
    missing = kwargs - registered_props[tool]
    assert not missing, f"{tool} missing documented kwargs {missing}; real {sorted(registered_props[tool])}"


def test_no_fictional_tool_names(registered_props):
    leaked = FICTIONAL & registered_props.keys()
    assert not leaked, f"fictional tool names registered again: {leaked}"
