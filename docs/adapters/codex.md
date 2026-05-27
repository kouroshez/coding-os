<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-04-27 -->
# Codex Adapter

Purpose: Reference for the Codex (OpenAI) adapter — hook capabilities, dispatcher, gate behaviour, MCP responsibilities.
Read when: editing `src/adapters/codex/`, debugging a Codex session, adding a new hook that needs Codex parity.
Skip when: Claude/Cursor-specific issues.

> Nav: [AGENTS.md](../../AGENTS.md) › [adapters](.) › **codex**
> Status: live · subprocess SDK dispatcher active · limited hook surface

---

## Dispatcher

`src/adapters/codex/sdk_dispatcher.py` ships a **subprocess-based** dispatcher that wraps the
`codex` CLI binary:

```python
# src/adapters/codex/sdk_dispatcher.py
class CodexSDKDispatcher:
    name = "codex-sdk"

    def available(self) -> bool:
        return shutil.which("codex") is not None

    async def dispatch(self, request: DispatchRequest) -> DispatchResult:
        # Calls: codex --no-interactive --json <message>
        ...
```

`src/core/thinking_os/dispatcher.get_dispatcher("codex")` loads it via the generic
`_try_load_adapter_dispatcher("codex")` loader — no core code is coupled to the
Codex binary. If `codex` is absent from `PATH`, the loader returns `None` and
`get_dispatcher` falls back to the default inline dispatcher.

**Dispatch prompt structure (parity with Claude dispatcher):**

```
{formula_body}

## Dispatch Context
- Formula: {formula_id}
- Persona: {persona_id}
- Intensity: {intensity}

## Input Context (upstream formulas only)
```json
{input_slice}
```

## Task
{request.prompt}

Produce the EvidenceBundle slice for this formula as a single ```json ... ``` block.
```

The old implementation used `request.prompt or system_body` — either/or, which silently
dropped the formula body whenever a task prompt was provided. The current implementation
always includes system body + context + input slice + prompt.

**SDK choice:** The dispatcher uses subprocess (`codex --no-interactive --json`), not
the `openai-agents` Python SDK. This keeps the dependency surface minimal and stays
compatible with the `codex` CLI's stable CLI surface. If OpenAI releases a first-party
Python SDK with a stable async API, mirror the Claude pattern:
`src/adapters/codex/sdk_dispatcher.py` is the only file that needs updating.

---

## Hook Capability Gap

Codex exposes a **narrower hook surface** than Claude (as of 2026-04). The key gaps
affect which enforcement gates fire automatically:

| Event | Claude | Codex |
|-------|--------|-------|
| PreToolUse `Write\|Edit` | ✅ | ❌ |
| PreToolUse `Bash` | ✅ | ✅ |
| PostToolUse `Write\|Edit` | ✅ | ❌ |
| PostToolUse `Bash` | ✅ | ✅ |
| SessionStart `startup\|resume` | ✅ | ✅ |
| SessionStart `compact` | ✅ | ❌ |

**Consequence for gates:** All hooks that use `Write\|Edit` matchers (e.g.
`enforce-wip-limit.sh`, `auto-reindex-docs.sh`, `capture-work-log.sh`,
`enforce-doc-anchor.sh`) do **not** fire in Codex. Codex must call the MCP
equivalents explicitly.

---

## Explicit MCP Pattern for Codex

Because `PostToolUse Write|Edit` does not fire, Codex agents MUST call these MCP
tools manually at the points where the hook would otherwise run:

| Hook (Claude-only) | Codex must call instead |
|--------------------|------------------------|
| `enforce-wip-limit.sh` | `cos_task_wip_check` before moving task to in_progress |
| `capture-work-log.sh` | `cos_work_log_append` after each meaningful change |
| `auto-reindex-docs.sh` | `cos graph-reindex --prune-stale` (shell) — or accept stale graph until next hook-capable run |
| `enforce-doc-anchor.sh` | Manually verify doc anchor before each code write |

The `AGENTS.md` Tool Routing section flags Codex specifically:
> **Codex MUST call `cos_work_log_append`** — no PostToolUse hook.

---

## Thinking OS Gate in Codex

The `thinking_os-gate` hook fires on `PreToolUse Bash` in Codex (it's in the
`codex-pretool-dispatch.sh` chain via `enforce-verify.sh`). However:

- **Write/Edit code changes are NOT gated by the gate check** — only Bash commands are.
- Codex agents must manually record the gate before writing code:

```bash
bash .codex/hooks/write-state.sh .codex/.thinking_os-gate "COMPLICATED 3"
```

Or via the CLI:
```bash
cos gate-record "COMPLICATED 3"
```

The gate is stored at `$COS_STATE_DIR/.thinking_os-gate` (defaults to `.codex/`),
expires after 120 minutes or on new session start.

---

## WIP Enforcement

`enforce-wip-limit.sh` does not fire in Codex (requires `PreToolUse Write|Edit`).
Codex must use `cos_task_wip_check` before starting a task:

```python
result = await mcp.call_tool("cos_task_wip_check", {"status": "in_progress"})
if not result["data"]["allowed"]:
    raise RuntimeError(f"WIP cap reached: {result['data']['reason']}")
```

---

## Adding a New Codex Gate

When Codex expands its hook surface, update `src/adapters/codex/adapter.yaml::hook_capabilities`
and re-run `make regen-adapter-templates`. No other code changes are needed —
the template renderer automatically enables hooks whose `{event, matcher}` pair
appears in the capability list.

---

## See also

- [docs/adapters/claude-sdk.md](claude-sdk.md) — Claude SDK reference implementation
- [AGENTS.md §P8](../../AGENTS.md) — Adapter-SDK autonomy principle
- [src/core/thinking_os/dispatcher.py](../../src/core/thinking_os/dispatcher.py) — generic adapter dispatcher loader
- [src/adapters/codex/sdk_dispatcher.py](../../src/adapters/codex/sdk_dispatcher.py) — Codex subprocess dispatcher
- [docs/engineering/board-thinking-os-coupling.md](../engineering/board-thinking-os-coupling.md) — WIP + task coupling
