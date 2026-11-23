"""The task family loads upfront instead of behind ToolSearch.

Claude Code honours `_meta["anthropic/alwaysLoad"]` on a tools/list entry, so an
agent can start, move and log a task without first searching for the tools.
"""

from __future__ import annotations

import asyncio

import server

HOT_TASK_TOOLS = {
    "cos_task_create",
    "cos_task_move",
    "cos_task_show",
    "cos_task_search",
    "cos_work_log_append",
    "cos_classify_prompt",
}


def test_only_the_task_family_is_marked_always_load():
    tools = asyncio.run(server.mcp.list_tools())
    marked = {tool.name for tool in tools if (tool.meta or {}).get("anthropic/alwaysLoad")}
    assert marked == HOT_TASK_TOOLS


def test_the_flag_is_serialised_as_tools_list_meta():
    tools = asyncio.run(server.mcp.list_tools())
    create = next(tool for tool in tools if tool.name == "cos_task_create")
    assert create.model_dump(by_alias=True, exclude_none=True)["_meta"] == {
        "anthropic/alwaysLoad": True
    }
