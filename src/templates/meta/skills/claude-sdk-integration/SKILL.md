---
name: claude-sdk-integration
description: Use when authoring code that uses Anthropic's Claude SDK or the claude-agent-sdk inside the meta-repo — primarily src/adapters/claude/sdk_dispatcher.py and the formula composer pipeline that spawns Claude Code sub-sessions. Covers prompt caching, tool-use loop, model selection (Opus 4.7, Sonnet 4.6, Haiku 4.5), session lifecycle, error handling, and the dispatcher protocol contract every adapter must satisfy. Pairs with python-meta-server, meta-engineering, and the claude-api skill (when working on raw API).
last_reviewed: "2026-05-11"

---

# claude-sdk-integration

Purpose: Make every interaction with Anthropic's Python SDKs robust,
cache-friendly, and contract-compliant. The meta-repo dispatches Claude
sub-sessions via `claude-agent-sdk`; agents editing this surface must
preserve the protocol that `src/core/thinking_os/dispatcher.py` defines.

Read when: editing any of:
- `src/adapters/claude/sdk_dispatcher.py` — the SDK dispatcher.
- `src/adapters/claude/install.sh` — adapter scaffold (when changing SDK options).
- `src/core/thinking_os/dispatcher.py` — the protocol the dispatcher implements.
- `src/core/thinking_os/formula_composer.py` — when changing how chains spawn sub-sessions.
- `src/core/thinking_os/cognition.py` — when wiring `cos_dispatch_formula_run`.

Skip when: editing tests under `tests/test_*sdk*`, mock fixtures.

## Two libraries, two scopes

```
anthropic       — raw Claude API (Messages, tool use, streaming)
claude-agent-sdk — high-level: spawns a Claude Code sub-session as a
                   coroutine, handles tool-use loop, session lifecycle
```

`src/adapters/claude/sdk_dispatcher.py` uses **claude-agent-sdk** (high
level). For raw API work (cognition tools that build prompts), use
`anthropic`.

## Dispatcher protocol contract

`src/core/thinking_os/dispatcher.py` defines:

```python
class AgentDispatcher(Protocol):
    def available(self) -> bool: ...
    async def dispatch(self, request: DispatchRequest) -> DispatchResult: ...
```

Any adapter dispatcher (Claude, Codex, …) MUST implement this. Breaking
the signature breaks every cognition flow.

## Hard rules

### 1. Prompt caching (SDK + raw)

Cache markers on stable prefixes:

```python
messages = [
    {"role": "user", "content": [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic_question},
    ]}
]
```

Goal: ≥80% cache hit rate on repeated dispatches. The dispatcher should
keep the system prompt + tool list + role context BEFORE the
question — never interleave dynamic content into the cached prefix.

### 2. Model selection

Default: `claude-sonnet-4-6`. Promote to `claude-opus-4-7` only for:
- COMPLICATED+ tasks via `cos_compose_chain`.
- Architect / refactorer roles.
Never use older model IDs (3.x family) — retired.

Haiku (`claude-haiku-4-5-20251001`) for cheap heuristic dispatches
(formula composition, classification).

### 3. Tool-use loop

When using raw API with tools:

```python
while response.stop_reason == "tool_use":
    tool_calls = [b for b in response.content if b.type == "tool_use"]
    tool_results = [run_tool(tc) for tc in tool_calls]
    response = client.messages.create(
        model=...,
        messages=messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tc.id, "content": result}
                for tc, result in zip(tool_calls, tool_results)
            ]},
        ],
        tools=tools,
    )
```

Always check `stop_reason` — `end_turn`, `tool_use`, `max_tokens`,
`stop_sequence`. NEVER assume the model returned plain text.

### 4. Session lifecycle (claude-agent-sdk)

```python
from claude_agent_sdk import query

async with query(prompt=..., options=...) as session:
    async for message in session:
        if message.type == "assistant":
            ...
```

Always use `async with` so the session terminates cleanly. Leaking
sessions = stuck child processes.

### 5. EvidenceBundle — Rule 16

`cos_dispatch_formula_run` records output via `cos_supervise_record_output`
which produces a typed `EvidenceBundle`. Don't return plain strings —
the cognition layer expects the typed shape.

## Pre-edit moves

1. `cos_graph_context("src/adapters/claude/sdk_dispatcher.py", depth=1)` — neighbours.
2. `cos_graph_references("ClaudeSDKDispatcher.dispatch")` — who calls it.
3. `cos_graph_impact("ClaudeSDKDispatcher", direction="downstream")` — blast radius before signature change.
4. Read [docs/adapters/claude-sdk.md](../../../../docs/adapters/claude-sdk.md) for the full SDK contract.

## Anti-patterns

- **Hardcoded model ID strings scattered around** — define in one
  `MODELS` const, reference everywhere.
- **No `stop_reason` check** — silently truncated responses.
- **Calling `client.messages.create` synchronously inside async dispatch** — blocks event loop.
- **Cache marker on dynamic content** — destroys cache hit rate.
- **Importing `anthropic.*` in `src/core/**`** — P8 violation; SDK code lives in
  `src/adapters/claude/`.
- **Using `claude-agent-sdk` for raw prompts** — overkill; use `anthropic` directly.
- **Forgetting `--extra claude-sdk` when running tests that hit the dispatcher** — tests skip silently.

## Verification

- `uv run pytest tests/test_claude_dispatcher_options.py tests/test_sdk_presence.py -q`
- `uv run python src/scripts/smoke_sdk_dispatch.py` — end-to-end smoke (real API call, opt-in via env).
- After signature change to `dispatch()`: re-run cognition smoke — `cos_dispatch_formula_run` shouldn't break.

## Tooling

Flag stale/deprecated Claude model ids (update the map when the family rotates):
`python3 scripts/check_model_ids.py src/adapters/claude/*.py`

## See also

- [assets/sdk-checklist.md](assets/sdk-checklist.md) — the SDK integration gate (model/caching/tool-loop/session).
- [docs/adapters/claude-sdk.md](../../../../docs/adapters/claude-sdk.md)
- [docs/adapters/claude-deepening-checklist.md](../../../../docs/adapters/claude-deepening-checklist.md)
- [src/core/thinking_os/dispatcher.py](../../../../core/thinking_os/dispatcher.py)
- [src/adapters/claude/sdk_dispatcher.py](../../../../adapters/claude/sdk_dispatcher.py)
