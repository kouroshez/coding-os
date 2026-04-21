# Codex Adapter

> Nav: [AGENTS.md](../../AGENTS.md) › [adapters](.) › **codex**
> Status: live · formula dispatch uses default (inline) path

## Dispatcher

Codex has no first-party Python agent SDK wired into `coding-os` yet.
Formula-agent dispatch (`cos_dispatch_formula_run`) falls back to the
**default dispatcher** in [core/thinking_os/dispatchers/default.py](../../core/thinking_os/dispatchers/default.py),
which returns `status="skipped"` with `error="inline-dispatch-required"`.
The main Codex agent runs the formula inline (Phase M behaviour).

## Future SDK integration

OpenAI ships [`openai-agents`](https://github.com/openai/openai-agents-python).
To light it up for Codex, mirror the Claude pattern:

1. `uv add openai-agents` under a new `codex-sdk` extra in [pyproject.toml](../../pyproject.toml).
2. Create `adapters/codex/sdk_dispatcher.py` exposing `build_dispatcher()` and an `AgentDispatcher`-shaped class.
3. Teach `_try_load_codex_sdk_dispatcher()` in [core/thinking_os/dispatcher.py](../../core/thinking_os/dispatcher.py) to import it by path.

Rule 1 stays intact: `core/` never imports the OpenAI SDK.

## See also

- [docs/adapters/claude-sdk.md](claude-sdk.md) — reference implementation
- [AGENTS.md §P8](../../AGENTS.md) — Adapter-SDK autonomy principle
