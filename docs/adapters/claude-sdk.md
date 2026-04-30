<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-04-24 -->
# Claude-SDK Dispatcher — `adapters/claude/sdk_dispatcher.py`

Purpose: Explain how the Claude adapter spawns formula-agent sub-sessions via `claude-agent-sdk`.
Read when: touching `adapters/claude/sdk_dispatcher.py`, debugging formula dispatch, enabling the claude-sdk extra.
Skip when: other adapters, retrieval, board_os.

> Nav: [AGENTS.md](../../AGENTS.md) › [adapters](../adapters/) › **claude-sdk**
> Introduced: 2026-04-20 (Phase N.SDK slice)
> Status: live · optional extra · Claude-adapter-only

## 1. What it is

The claude-sdk dispatcher turns Phase M **formula-agents** (F1..F11) into
**real sub-sessions** spawned via [`claude-agent-sdk`](https://github.com/anthropics/claude-agent-sdk-python).
Before this slice, `cos_supervise` returned `NextAction(action="dispatch", …)`
and the main agent had to execute the formula inline. Now, when the adapter
is Claude *and* the `claude-sdk` extra is installed, the supervisor can ask
the dispatcher to **actually run** the agent and return a structured
EvidenceBundle slice — including in parallel.

## 2. Why it is Claude-only

`claude-agent-sdk` wraps the **Claude Code CLI** (Go binary) and targets
Anthropic models exclusively. Codex, Cursor, and future agents have their
own SDKs (OpenAI Agents SDK, etc.) or no SDK at all — they use the
**default dispatcher** in [core/thinking_os/dispatchers/default.py](../../core/thinking_os/dispatchers/default.py),
which records the dispatch intent and returns `status="skipped"`, letting
the main agent execute the formula inline (the Phase M behaviour).

This keeps `core/` agent-agnostic (Rule 1): the Protocol lives in core,
the Claude-specific implementation lives under `adapters/claude/`.

## 3. Architecture

```
core/thinking_os/cognition.py          pure state machine (unchanged)
        │                               returns NextAction(dispatch, …)
        ▼
core/thinking_os/dispatcher.py         AgentDispatcher Protocol + factory
        │
        ├── get_dispatcher() ──────┐
        │                          │
        ▼                          ▼
core/thinking_os/dispatchers/      adapters/claude/sdk_dispatcher.py
  default.py  (fallback)             ClaudeSDKDispatcher
  status="skipped"                    wraps claude-agent-sdk.query()
```

### Factory resolution order

1. If `COS_FORCE_DEFAULT_DISPATCHER=1` → default.
2. Detect agent: `COS_AGENT` env → `COS_AGENT_DIR` folder name → "default".
3. If agent is `claude`, import `adapters/claude/sdk_dispatcher.py` by path.
4. If the import succeeds AND `claude_agent_sdk` is installed → use it.
5. Otherwise → default dispatcher.

## 4. Install

```bash
uv sync --extra claude-sdk
```

This adds `claude-agent-sdk>=0.1.0` and `anyio>=4.0.0` to the project.
The dispatcher probe (`available()`) returns True only after this.

## 5. Contract

**Input** — `DispatchRequest`:

| field | type | description |
|---|---|---|
| `formula_id` | str | e.g. `"implementer"` |
| `agent_file` | str | absolute path to `F<N>_<name>.md` |
| `prompt` | str | composed system+user prompt |
| `input_slice` | dict | upstream-only bundle view from `build_input_slice()` |
| `persona_id` | str\|None | dispatch persona (Phase N) |
| `intensity` | `"light"\|"standard"\|"full"` | filters agent step list |
| `allowed_tools` | list[str] | SDK `allowed_tools` passthrough |
| `timeout_s` | float | hard timeout, default 300s |

**Output** — `DispatchResult`:

| field | type | description |
|---|---|---|
| `status` | `"ok"\|"timeout"\|"error"\|"skipped"` | outcome |
| `output_json` | dict | parsed from ```json``` fenced block in transcript |
| `latency_ms` | int | wall-clock dispatch time |
| `dispatcher_name` | str | `"claude-sdk"` or `"default"` |
| `error` | str\|None | failure reason if not ok |
| `raw_transcript` | str\|None | full assistant text, for debugging |

## 6. Real benchmarks (2026-04-20)

Run: `uv run --extra claude-sdk python scripts/bench_sdk_dispatcher.py`

### Sequential (3 formulas, real Claude Code spawning)

| Scenario | Formula | Latency | Output size | Fields populated |
|---|---|---|---|---|
| decompose a /healthz endpoint | F2 | 30.0s | 3549 B | actors, decision_table, data_model, events, dependencies |
| debug `sorted(...)` TypeError | F7 | 15.9s | 1582 B | root_cause, fault_chain, fix_applied, regression_tests_added, prevention |
| implement `slugify()` helper | F5 | 14.7s | 1080 B | files_created, files_modified, implementation_notes, open_items |
| **Total** | | **60.6s** | | **3/3 ok** |

### Parallel (F7 + F5 via `asyncio.gather`)

| Metric | Value |
|---|---|
| Parallel wall time | 15.8s |
| Sequential equivalent | 30.6s |
| **Speedup** | **1.93x** (near-perfect) |

### Interpretation

- F2 is the slowest because decompose-intensity produces the largest JSON (~3.5 KB, 6+ entity fields).
- F5/F7 are ~14s — typical for light-intensity formulas emitting <2 KB JSON.
- Parallel dispatch is bandwidth-bound, not CPU-bound — `asyncio.gather` gives near-linear speedup. The F8 security-layers parallel path (Phase M feature) will benefit similarly.

## 7. How the supervisor wires in

The main agent doesn't call the dispatcher directly — it goes through
two MCP tools registered in [core/thinking_os/tools/cognition.py](../../core/thinking_os/tools/cognition.py):

### 7.1 — `cos_dispatch_formula_run` (single)

```
Input:  formula_id, session_id, task_marker, persona_id, intensity, timeout_s?
Output: {status, formula_id, dispatcher_name, latency_ms,
         output_json, error, bundle_fields_filled}
```

Under the hood:

1. Build `DispatchRequest` from session state (agent file, input slice, intensity).
2. `get_dispatcher()` picks `claude-sdk` or `default` automatically.
3. `asyncio.run(d.dispatch(req))` — nested-loop fallback spins a dedicated thread.
4. On `ok`, output is validated against the formula's `F<N>Output` Pydantic
   schema, merged into the EvidenceBundle, and the dispatch row is written
   to `formula_dispatches`.
5. On `default` dispatcher (Codex/Cursor/no-SDK): status is `"skipped"` with
   `error="inline-dispatch-required"`, and the main agent falls back to
   Phase M inline-execution.

### 7.2 — `cos_dispatch_parallel_run` (concurrent)

```
Input:  formula_ids: list[str], session_id, …
Output: {results: [...], parallel_wall_ms, ok_count, total}
```

Uses `asyncio.gather(*(d.dispatch(req) for req in requests))` under the
same nested-loop fallback. Each output is independently validated and
persisted. Call when `cos_supervise` returns
`action="dispatch_parallel"` (e.g. F8 security layers).

### 7.3 — Typical call sequence

```
main agent:
  cos_route_persona    → { persona_id: "senior-backend", … }
  cos_supervise        → NextAction(action="dispatch",   formula="implementer", …)
  cos_dispatch_formula_run(formula_id="implementer", …)
                       → { status:"ok", output_json:{…}, bundle_fields_filled:1 }
  cos_supervise        → NextAction(action="dispatch_parallel", formulas=["reviewer","security_auditor"], …)
  cos_dispatch_parallel_run(formula_ids=["reviewer","security_auditor"], …)
                       → { ok_count:2/2, parallel_wall_ms:13839 }
  cos_supervise        → NextAction(action="done")
```

`cos_supervise_record_output` is still useful when the **default** dispatcher
is in use (main agent runs the formula inline), but you don't need to call
it manually after `cos_dispatch_formula_run` — that tool persists the bundle
itself.

## 8. End-to-end validation (2026-04-20)

`scripts/e2e_dispatch_tool.py` exercises the full MCP-tool path:

```
→ registered tools: ['cos_dispatch_formula_run', 'cos_dispatch_parallel_run']

=== Single-formula dispatch (F7) ===
  dispatcher: claude-sdk  latency: 10.4s
  output keys: [_meta, fault_chain, fix_applied, prevention, regression_tests, root_cause]
  bundle_fields_filled: 1

=== Parallel (F5+F7) ===
  ok_count: 2/2   parallel_wall_ms: 13.8s
  F5: latency=13.8s   F7: latency=10.7s (ran concurrently)

=== Bundle ===    populated: [implementer, debugger]
=== DB audit ===  3 rows in formula_dispatches

E2E: PASS
```

Compared to sequential (10.7 + 13.8 = 24.5s), parallel wall was **13.8s —
a 1.78x speedup** on a 2-formula dispatch.

## 9. Tests

| File | Tests | Covers |
|---|---|---|
| [core/thinking_os/tests/test_dispatcher.py](../../core/thinking_os/tests/test_dispatcher.py) | 11 | Protocol shape, factory env routing, default dispatcher, SDK dispatcher (mocked happy/timeout/missing-json) |
| [scripts/bench_sdk_dispatcher.py](../../scripts/bench_sdk_dispatcher.py) | — | Real sequential + parallel benchmark (spawns real Claude Code) |
| [scripts/e2e_dispatch_tool.py](../../scripts/e2e_dispatch_tool.py) | — | Real MCP tool → dispatcher → Claude → bundle → DB audit row |

Run:

```bash
uv run --extra claude-sdk --extra rag pytest core/thinking_os/tests/test_dispatcher.py -v
# 11 passed in 0.34s

uv run --extra claude-sdk python scripts/bench_sdk_dispatcher.py
# sequential: 3/3 ok in 54–60s; parallel speedup: 1.93x

uv run --extra claude-sdk python scripts/e2e_dispatch_tool.py
# E2E: PASS (single + parallel + bundle + DB)
```

## 9. What other adapters do

| Adapter | Dispatcher | Behaviour |
|---|---|---|
| `claude` + `claude-sdk` extra | `ClaudeSDKDispatcher` | Real sub-agent spawning via CLI |
| `claude` without extra | `DefaultDispatcher` | Inline dispatch (Phase M fallback) |
| `codex` | `DefaultDispatcher` | Inline dispatch (OpenAI Agents SDK integration pending) |
| `cursor` | `DefaultDispatcher` | Inline dispatch (no SDK planned) |
| any other | `DefaultDispatcher` | Inline dispatch |

New adapter with its own SDK? Drop `sdk_dispatcher.py` under
`adapters/<your-agent>/` exposing a `build_dispatcher()` factory, teach
`_detect_agent()` the name, and add a `_try_load_<agent>_sdk_dispatcher()`
branch to the factory. Core never learns your SDK's shape.

## 10. Related

- [core/thinking_os/dispatcher.py](../../core/thinking_os/dispatcher.py) — Protocol + factory
- [core/thinking_os/dispatchers/default.py](../../core/thinking_os/dispatchers/default.py) — fallback
- [adapters/claude/sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py) — Claude-specific
- [scripts/bench_sdk_dispatcher.py](../../scripts/bench_sdk_dispatcher.py) — real benchmark
- [docs/phase-n-role-based-routing-plan.md](../phase-n-role-based-routing-plan.md) — routing layer (what formula to pick)
- [docs/phase-m-thinking_os-new-formula.md](../phase-m-thinking_os-new-formula.md) — formula-agents (what this dispatcher spawns)
