<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-05-07 -->
# MCP Schema Traps — Exact Types for Agent Callers

> P: Canonical reference for the non-obvious input shapes of `cos_*` MCP tools and the deferred-tool loading rule.
> R: Authoring an agent flow that calls a `cos_*` tool, or debugging an `InputValidationError`.
> S: The tool's signature is already loaded into context this session.
> N: [mcp-error-envelope.md](mcp-error-envelope.md), [mcp-fast-path-entry.md](mcp-fast-path-entry.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

> The 79 `cos_*` tools are deferred — their schemas are not loaded at session start. Agents must call `ToolSearch` before the first use of any tool. Several tools also have Pydantic-validated inputs whose field types are non-obvious and produce opaque validation errors when wrong. This file is the canonical reference for those traps.

## Deferred Tool Loading (mandatory, session-scoped)

All `mcp__coding-os__cos_*` tools appear only as **names** in context at session start.
Calling one without first loading its schema produces:

```
InputValidationError: tool not found or schema not loaded
```

**Protocol:** call `ToolSearch(query="select:<tool1>,<tool2>")` before the first invocation
of any new tool. Batch multiple tools in one call.

```
ToolSearch("select:mcp__coding-os__cos_compose_chain,mcp__coding-os__cos_task_board")
```

This is a **session-scoped** requirement — it resets on every new Claude Code session. There
is no hook that reminds you; missing it produces a silent `InputValidationError`.

---

## TaskSignals — `cos_compose_chain` / `cos_analyze_task`

`signals_json` must be valid JSON that deserializes into `TaskSignals` (Pydantic v2).
The non-obvious fields:

| Field | Type | Legal values | Common wrong form |
|---|---|---|---|
| `dimensions` | `int` | any int ≥ 1 | `["mcp-tooling", "workflow"]` ← list, WRONG |
| `domain` | `list[str]` | `["meta"]`, `["django", "meta"]` | `"meta"` ← string, WRONG |
| `complexity` | `Literal` | `"CLEAR"`, `"COMPLICATED"`, `"COMPLEX"`, `"CHAOTIC"`, `"CONFUSION"` | `"complex"` ← lowercase, WRONG |
| `scope_size` | `Literal` | `"trivial"`, `"small"`, `"medium"`, `"large"`, `"recursive"` | `"big"` ← not a valid value |
| `action` | `Literal` | `"create"`, `"modify"`, `"debug"`, `"research"`, `"review"`, `"deploy"`, `"refactor"`, `"document"`, `"audit"`, `"unknown"` | `"analyze"` ← not valid |
| `urgency` | `Literal` | `"normal"`, `"elevated"`, `"incident"` | `"high"` ← not valid |
| `novelty` | `float` | `0.0`–`1.0` | `"high"` ← string, WRONG |

**Minimal valid call:**

```json
{
  "task_title": "Fix auth bug",
  "dimensions": 2,
  "complexity": "COMPLICATED",
  "domain": ["meta"]
}
```

**What Pydantic says on error** (not helpful):

```
2 validation errors for TaskSignals
domain
  Input should be a valid array [type=list_type, input_value='meta', input_type=str]
dimensions
  Input should be a valid integer [type=int_type, input_value=['mcp-tooling'], input_type=list]
```

---

## `ok` / `fail` Envelope — `@safe_tool` contract

Every `cos_*` tool wraps its return in:

```json
{"ok": true,  "data": { ... }}
{"ok": false, "error": {"category": "...", "message": "...", "retryable": false}}
```

The `result` key you get from calling an MCP tool wraps this again:

```python
# What you receive:
tool_result = {"result": "{\"ok\": true, \"data\": {...}}"}

# Correct unwrap:
import json
envelope = json.loads(tool_result["result"])
if envelope["ok"]:
    data = envelope["data"]
else:
    raise ValueError(envelope["error"]["message"])
```

**Anti-pattern:** reading `tool_result["data"]` directly → `KeyError`. The outer key is always
`"result"` and its value is a JSON **string** (double-encoded), not a dict.

---

## Graph UID Scheme

See [graph-hallucination-cures.md](graph-hallucination-cures.md) Rule #0 for full reference.
Short form:

```
code:file:<repo-relative-path>            core/thinking_os/server.py
code:function:<path>::<name>              core/thinking_os/server.py::cos_metric_record
code:class:<path>::<name>                 core/thinking_os/cognition.py::SupervisorState
code:module:<dotted>                      core.thinking_os.server
doc:file:<repo-relative-path>             docs/engineering/mcp-schema-traps.md
doc:heading:<path>#<slug>:<level>         docs/engineering/mcp-schema-traps.md#uid-scheme:2
folder:<repo-relative-path>               core/thinking_os/tools
config:json:<path>#<json-pointer>         core/web/ui/tsconfig.json#/compilerOptions/paths/@app/*
config:toml:<path>#<dotted-key>           pyproject.toml#/project/scripts/cos
npm:package:<name>                        npm:package:react
pypi:package:<name>                       pypi:package:click
crates:package:<name>                     crates:package:tokio
mcp:server:<name>                         mcp:server:coding-os
cos:hook:<name>                           cos:hook:nudge-thinking-os
```

The `config:*`, `npm:*`, `pypi:*`, `crates:*`, `mcp:*` kinds landed with the
polyglot extractor upgrade (commit 9bee865) — agents querying for package
dependencies or MCP server registrations can now hit those nodes directly
rather than reading the source JSON/TOML.

**Which tools auto-resolve raw paths:**
- `cos_graph_context` (`uid_or_name`) — YES, full fuzzy fallback
- `cos_graph_impact` (`uid`) — documented as YES, but active agent belief says NO (score 0.93)
- `cos_graph_references`, `cos_graph_rename_plan`, `cos_graph_path` — NO

**Safe pattern: always resolve first.**

```
cos_graph_resolve("core/thinking_os/server.py")
→ returns: [{"uid": "code:file:core/thinking_os/server.py", ...}]
→ pass uid to cos_graph_impact / cos_graph_references
```

---

## Deprecated Tools

| Tool | Status | Use instead |
|---|---|---|
| `cos_graph` | DEPRECATED | `cos_graph_context` / `cos_graph_impact` |

Calling `cos_graph` returns `{"ok": false, "error": {...}}` with a migration message.
Do not call it; callers that do will receive an empty result set.

---

## See also

- [graph-hallucination-cures.md](graph-hallucination-cures.md)
- [mcp-error-envelope.md](mcp-error-envelope.md)
- [mcp-fast-path-entry.md](mcp-fast-path-entry.md)
