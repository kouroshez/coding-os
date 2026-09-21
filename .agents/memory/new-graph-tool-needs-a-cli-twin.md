---
name: new-graph-tool-needs-a-cli-twin
description: "Every cos_graph_* MCP tool must have a cos graph-* CLI mirror; the graph_os matrix row does not check it, CI does."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-21T01:27:50.456Z
---

Adding a `cos_graph_*` MCP tool requires **four** registrations, not two:

1. the function, in a private `_graph_*.py` sibling
2. the re-export in `src/core/graph_os/tools/graph.py`
3. the `@mcp.tool` wrapper in `src/core/thinking_os/_tools_graph_insights.py` — without it the tool is invisible to every agent
4. **a `cos graph-<name>` command in `src/cli/_graph_cli_query.py`**

**Why:** `tests/test_graph_cli_parity.py::test_every_mcp_graph_tool_has_cli_command` enumerates `dir(graph_os.tools.graph)` and fails on any tool without a CLI twin. It lives in `tests/`, so the `src/core/graph_os/**` matrix row never runs it — 1,285 green graph_os tests and a red CI. I shipped `cos_graph_stale_files` with steps 1–3 and only caught step 4 because an adversarial reviewer named the test.

**How to apply:** after adding any graph tool, run `uv run pytest tests/test_graph_cli_parity.py -q` before committing — it takes 0.5s. The same shape as [[verification-matrix-must-match-ci]]: the row you match is not the row CI runs. Related: [[rules-edits-need-golden-capture]].
