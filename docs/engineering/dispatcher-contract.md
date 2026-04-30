# Dispatcher Contract

> **Source of truth.** When this doc and the code disagree, the code wins —
> open a PR to update this doc, then merge.

## Purpose

Formula agents (F1..F11) need to run **somewhere**. The runtime is different
per agent CLI:

| Agent  | Spawn channel                              | SDK kind             |
|--------|--------------------------------------------|----------------------|
| Claude | `claude-agent-sdk.query()` (in-process)    | Python library       |
| Codex  | `codex --no-interactive --json` subprocess | CLI binary           |
| Cursor | none (no headless API as of 2026-04)       | n/a — inline only    |
| any    | `DefaultDispatcher` (DB-only fallback)     | n/a — inline only    |

The contract here is the **agent-agnostic shape** every dispatcher must
satisfy so the supervisor (`cos_supervise`, `cos_dispatch_formula`) does not
need to know which runtime it is talking to.

## Contract Surface

Defined in [core/thinking_os/dispatcher.py](../../core/thinking_os/dispatcher.py).

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
│ core/thinking_os/dispatcher.py           │   agent-agnostic
│   • DispatchRequest / DispatchResult     │
│   • AgentDispatcher Protocol             │
│   • get_dispatcher() factory             │
│ core/thinking_os/dispatcher_helpers.py   │
│   • load_agent_prompt()                  │
│   • extract_json_block()                 │
└─────────────────┬────────────────────────┘
                  │ importlib (path-based; no static link)
   ┌──────────────┼──────────────┬────────────┐
   ▼              ▼              ▼            ▼
adapters/     adapters/      adapters/   core/thinking_os/
claude/       codex/         cursor/     dispatchers/
sdk_dispatcher.py                        default.py
   │              │              │            │
   ▼              ▼              ▼            ▼
claude-agent-sdk  codex CLI    stub     DB-only fallback
(in-proc)         (subprocess) (skipped)(skipped)
```

**Why three implementations and not one:** the SDKs are different runtimes,
not different views of the same runtime. A unified body would either have to
re-implement what each SDK does (more code, more surface to break) or
abstract over differences that do not exist as a real abstraction (in-proc
async generator vs. subprocess vs. nothing). Hexagonal here gives us:

- `core/` agent-agnostic (Rule 1)
- adapters self-contained (Principle P8)
- new agents add a folder, not a switch statement

## Factory rules (`get_dispatcher`)

1. If `COS_FORCE_DEFAULT_DISPATCHER=1` → `DefaultDispatcher`. Tests use this.
2. Detect agent from `COS_AGENT` env, then `COS_AGENT_DIR` folder name.
3. Try to load `adapters/<agent>/sdk_dispatcher.py::build_dispatcher()`.
4. Call `available()`; if `False`, fall through to `DefaultDispatcher`.
5. `DefaultDispatcher.available()` is always `True` — last-resort path.

The loader is `importlib.util.spec_from_file_location` so `core/` never has
a static import on `adapters/`.

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

## Adding a new adapter dispatcher

1. Create `adapters/<agent>/sdk_dispatcher.py`.
2. Import the contract + helpers from `thinking_os.*`.
3. Implement a class with `name`, `available()`, and `async dispatch()`.
4. Add `build_dispatcher() -> YourDispatcher`.
5. Add a parity test in `tests/test_adapter_parity.py`.
6. Update `adapters/<agent>/adapter.yaml` if presence/hook capabilities
   change. No edits to `core/` are needed.

## Tests

| File                                              | What it covers                          |
|---------------------------------------------------|-----------------------------------------|
| `core/thinking_os/tests/test_dispatcher.py`       | Protocol shape, factory, default path   |
| `tests/test_codex_dispatchers.py`                 | Codex subprocess path                   |
| `tests/test_adapter_parity.py`                    | Hook + dispatcher parity across agents  |
