<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-07-10 -->
# Dispatcher Contract

Purpose: Define the provider-neutral request/result protocol and the adapter-owned execution responsibilities for formula agents.
Read when: changing `DispatchRequest`, `DispatchResult`, an adapter dispatcher, or cross-adapter routing.
Skip when: changing an interactive provider UI that never invokes formula dispatch.
Read next: [Codex adapter](../adapters/codex.md), [Claude SDK](../adapters/claude-sdk.md), [adapter parity](adapter-parity.md).

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

> **Source of truth.** Update this contract before extending dispatcher behavior. A disagreement is drift to repair, not permission for the code to redefine the contract silently.

## Purpose

Formula agents (F1..F11) need to run **somewhere**. The runtime is different
per agent CLI:

| Agent  | Spawn channel | SDK kind |
|--------|---------------|----------|
| Claude | `claude-agent-sdk.query()` | required Python library |
| Codex  | default `codex exec --json`; optional `openai-codex` app-server | stable CLI plus opt-in beta Python SDK |
| any    | `DefaultDispatcher` (DB-only fallback) | n/a - inline only |

The contract here is the **agent-agnostic shape** every dispatcher must
satisfy so the supervisor (`cos_supervise`, `cos_dispatch_formula`) does not
need to know which runtime it is talking to.

## Contract Surface

Defined in [src/core/thinking_os/dispatcher.py](../../src/core/thinking_os/dispatcher.py).

### IO models

```python
class DispatchRequest(BaseModel):
    formula_id: str            # safe slug — embeddable in filenames
    agent_file: str            # absolute or thinking_os-relative path
    prompt: str                # composed system+user prompt
    input_slice: dict          # upstream-only EvidenceBundle view
    persona_id: str | None
    intensity: Literal["light", "standard", "full"]
    allowed_tools: list[str]
    timeout_s: float
    session_id: str | None
    cwd: str | None
    model: str | None          # forwarded to the adapter; None = adapter default
    max_budget_usd: float | None
    long_context: bool
    adapter: str | None        # target-runtime HINT (e.g. "codex"); see below
    max_turns: int | None      # adapter-owned cap when the runtime supports it

class DispatchResult(BaseModel):
    formula_id: str
    status: Literal["ok", "timeout", "error", "skipped"]
    output_json: dict          # validated against formula's output_schema
    latency_ms: int
    error: str | None
    dispatcher_name: str       # "claude-sdk" | "codex-sdk" | "default" | ...
    raw_transcript: str | None
```

### Protocol

```python
@runtime_checkable
class AgentDispatcher(Protocol):
    name: str
    async def dispatch(self, request: DispatchRequest) -> DispatchResult: ...
    def available(self) -> bool: ...
```

### Status semantics

| `status`  | Meaning                                                         | Caller action                                          |
|-----------|-----------------------------------------------------------------|--------------------------------------------------------|
| `ok`      | Sub-agent ran, returned valid `output_json`                     | Validate against formula schema, persist               |
| `timeout` | Sub-agent exceeded `timeout_s`                                  | Surface as transient; main agent may retry             |
| `error`   | SDK failure, parse failure, missing agent file, subprocess rc≠0 | Surface as internal; do **not** silently downgrade     |
| `skipped` | Dispatcher cannot spawn (no SDK, no binary, stub adapter)       | Main agent inlines the formula and records output |

## Architecture

```
┌──────────────────────────────────────────┐
│ src/core/thinking_os/dispatcher.py       │   agent-agnostic
│   • DispatchRequest / DispatchResult     │
│   • AgentDispatcher Protocol             │
│   • get_dispatcher() factory             │
│ src/core/thinking_os/dispatcher_helpers.py   │
│   • load_agent_prompt()                  │
│   • extract_json_block()                 │
└─────────────────┬────────────────────────┘
                  │ importlib (path-based; no static link)
   ┌──────────────┼───────────────────────────┐
   ▼              ▼                            ▼
src/adapters/claude/  src/adapters/codex/  src/core/thinking_os/dispatchers/
sdk_dispatcher.py     sdk_dispatcher.py    default.py
   │                     │                   │
   ▼                     ▼                   ▼
claude-agent-sdk     codex CLI default     DB-only fallback
                     Python SDK opt-in     (skipped)
```

**Why three implementations and not one:** the SDKs are different runtimes,
not different views of the same runtime. A unified body would either have to
re-implement what each SDK does (more code, more surface to break) or
abstract over differences that do not exist as a real abstraction (in-proc
async generator vs. subprocess vs. nothing). Hexagonal here gives us:

- `src/core/` agent-agnostic (Rule 1)
- adapters self-contained (Principle P8)
- new agents add a folder, not a switch statement

## Factory rules (`get_dispatcher`)

1. If `COS_FORCE_DEFAULT_DISPATCHER=1` → `DefaultDispatcher`. Tests use this.
2. Detect agent from `COS_AGENT` env, then `COS_AGENT_DIR` folder name.
3. Try to load `src/adapters/<agent>/sdk_dispatcher.py::build_dispatcher()`.
4. Call `available()`; if `False`, fall through to `DefaultDispatcher`.
5. `DefaultDispatcher.available()` is always `True` — last-resort path.

The loader is `importlib.util.spec_from_file_location` so `src/core/` never has
a static import on `src/adapters/`.

6. **Adapter hint, not adapter switch.** `DispatchRequest.adapter` is a HINT:
   when set and different from the session's resolved adapter,
   `get_dispatcher(request=…)` logs a warning naming both and proceeds on the
   session adapter — one adapter per session remains the invariant. The field
   exists so supervisor decisions (preset `roles_adapter_hints`, TASK-321) have
   a typed carrier today; honoring the hint with a real cross-adapter dispatch
   is the explicit follow-up seam, not implied behaviour. Per-call cost ceilings
   ride on `max_budget_usd`; a separate `adapter_budget_usd` carrier was removed
   (audit 2026-06 F-axis-5 — it was never read, only defaulted).

## Parity rules

Every adapter dispatcher MUST:

1. Import `DispatchRequest`/`DispatchResult` from `thinking_os.dispatcher`
   (not by relative path or `sys.path` injection).
2. Use `load_agent_prompt` and `extract_json_block` from
   `thinking_os.dispatcher_helpers` rather than re-implementing them.
3. Expose `build_dispatcher() -> AgentDispatcher` as the factory entry-point.
4. Return `status="error"` (not raise) on FileNotFoundError, SDK import
   failure, subprocess rc≠0, parse failure, etc.
5. Set `dispatcher_name` to the same string as `self.name`.
6. Forward `model`; surface unsupported budget, context, tool, or turn controls instead of silently dropping them.
7. Never retry on another backend after a provider turn may have started; duplicate execution is worse than a visible error.

The Codex CLI backend additionally MUST use the current non-interactive surface (`codex exec`), write the prompt to stdin, parse JSONL events, and run formula output in a read-only sandbox with approvals disabled. Formula dispatch ignores user configuration, disables hooks, and clears MCP servers so host customizations cannot recurse into or mutate a supervised sub-run. The optional Python SDK is beta and selected explicitly until its schema stays compatible with the stable CLI.

## Adding a new adapter dispatcher

1. Create `src/adapters/<agent>/sdk_dispatcher.py`.
2. Import the contract + helpers from `thinking_os.*`.
3. Implement a class with `name`, `available()`, and `async dispatch()`.
4. Add `build_dispatcher() -> YourDispatcher`.
5. Add a parity test in `tests/test_adapter_parity.py`.
6. Update `src/adapters/<agent>/adapter.yaml` if presence/hook capabilities
   change. No edits to `src/core/` are needed.

## Tests

| File                                              | What it covers                          |
|---------------------------------------------------|-----------------------------------------|
| `src/core/thinking_os/tests/test_dispatcher.py`       | Protocol shape, factory, default path   |
| `src/core/thinking_os/tests/test_dispatcher.py`   | Codex CLI/SDK paths and request parity  |
| `tests/test_adapter_parity.py`                    | Hook + dispatcher parity across agents  |
