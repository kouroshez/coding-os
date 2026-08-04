<!-- domain:ADAPTERS | layer:architecture | ssot:true | updated:2026-08-03 -->
# Multi-Adapter Supervisor

Purpose: Evidence-backed architecture decision for coordinating Claude Code,
Codex, and future agent runtimes without importing provider SDKs into core.
Read when: extracting writable Hub chat behind a shared runtime port, adding a
new interactive adapter, or implementing mixed-adapter supervision.

> Nav: [docs/](../) · [architecture/](.) · related:
> [Agent Hub](../engineering/agent-hub-orchestration.md) ·
> [Codex adapter](../adapters/codex.md) ·
> [Claude SDK](../adapters/claude-sdk.md)

## Decision

Build a thin, deterministic supervisor inside Coding OS and expose an optional
ACP-compatible boundary for external agents. Do not embed OpenHands, LangGraph,
CrewAI, AutoGen, or another general orchestration framework as the kernel.

The supervisor has three separate layers:

1. **Runtime port** — provider-neutral start, load, prompt, steer, cancel,
   events, transcript, and close operations implemented by each adapter.
2. **Workflow supervisor** — typed state, checkpoints, policy routing,
   fan-out/fan-in, budgets, leases, approvals, and cancellation propagation.
3. **Execution isolation** — explicit workspace, sandbox, permissions, and one
   writer lease per change scope.

ACP is the right compatibility protocol at the edge, not the complete internal
contract. Its standard session lifecycle and JSON-RPC transport are valuable,
but provider-native SDKs expose capabilities Coding OS must not flatten away.

## Research method

Sources were reviewed on 2026-08-03. GitHub stars are a point-in-time popularity
signal, rounded below; they are not a quality or architectural fitness score.
The review used official repositories, project documentation, the ACP protocol
specification, and OpenAI's Codex documentation.

### Popular projects reviewed

| Project | Stars | Relevant architecture | Use in Coding OS |
|---|---:|---|---|
| [OpenCode](https://github.com/anomalyco/opencode) | 193.0k | Headless HTTP server, async sessions, child sessions, SSE events, provider/model abstraction, per-agent permissions | Borrow the normalized session/event surface; do not replace native Claude/Codex runtimes with a lowest-common-denominator model client. |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | 83.0k | Agent Server plus workspace backend; Canvas connects to several backends and launches ACP agents including Claude Code and Codex | Closest product precedent for Hub: adapter-labelled sessions over multiple local/remote runtimes. |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 69.7k | Role-based software company where SOPs coordinate product, architecture, project, and engineering agents | Keep Coding OS roles, presets, and formula chains declarative; do not couple roles to runtime adapters. |
| [AutoGen](https://github.com/microsoft/autogen) | 60.2k | Event-driven runtime, teams, model-client extensions, and agent-as-tool composition | Borrow event-driven composition concepts only. AutoGen is in maintenance mode and points new users to Agent Framework. |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 56.6k | Crews plus event-driven Flows, hierarchical managers, persisted state, replay/resume, and usage aggregation | Borrow checkpoint and accounting requirements; avoid duplicating Coding OS board and cognition layers. |
| [goose](https://github.com/aaif-goose/goose) | 52.2k | Provider abstraction, MCP extensions, and ACP providers for Claude Code and Codex | Strong proof that subscription-backed native agents can sit behind one interface. Its ACP adapter currently lacks session resume/fork. |
| [Agno](https://github.com/agno-agi/agno) | 41.6k | Multi-agent teams with provider-independent models, tools, memory, and workflows | Benchmark only; its broad agent platform overlaps the existing kernel. |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 38.8k | Stateful graphs, durable execution, streaming, human approval, subagents, handoffs, routers, and custom workflows | Borrow the deterministic graph/checkpoint model and explicit routing patterns, not the dependency. |
| [smolagents](https://github.com/huggingface/smolagents) | 28.7k | Small model/tool-agnostic core and hierarchical multi-agent delegation | Use as an anti-overengineering reference for a narrow port and small supervisor. |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | 12.6k | Successor to AutoGen/Semantic Kernel agent work; graph workflows, concurrent/handoff/group patterns, checkpoints, OpenTelemetry, governance | Confirms production requirements: durability, observability, middleware, and human-in-loop. |
| [Claude Squad](https://github.com/smtg-ai/claude-squad) | 8.2k | Profiles launch Claude, Codex, OpenCode, or other CLIs in isolated tmux sessions and git worktrees | Borrow explicit process/workspace ownership; it is a launcher, not a semantic supervisor. |
| [Agent Client Protocol](https://github.com/agentclientprotocol/agent-client-protocol) | 3.9k | Versioned JSON-RPC schemas and SDKs for clients to control coding agents | Implement as an optional compatibility adapter/gateway after the internal runtime port is stable. |

Other high-star systems checked for category coverage include
[ChatDev](https://github.com/OpenBMB/ChatDev),
[Semantic Kernel](https://github.com/microsoft/semantic-kernel), and
[CAMEL](https://github.com/camel-ai/camel). They reinforce role-play and
multi-agent workflow patterns but do not provide a better native Claude/Codex
runtime boundary than ACP plus provider adapters.

## What the strongest precedents actually do

### OpenHands: backend-scoped native agents

[Agent Canvas](https://docs.openhands.dev/openhands/usage/agent-canvas/backends)
defines a backend as an Agent Server plus workspace and lets one frontend
connect to multiple backends. Settings, LLM configuration, MCP servers, and
automations are scoped to the active backend. Its
[ACP integration](https://docs.openhands.dev/openhands/usage/agent-canvas/acp-agents)
spawns the provider CLI, lets that external agent own its LLM/tools/execution,
and relays UI events. The chosen agent is stored per backend, while an existing
conversation keeps the agent selected when it was created.

This maps directly to Coding OS: a Hub project supplies workspace scope; a run
records its adapter immutably; the adapter owns its SDK and native thread id.

### ACP and goose: useful portability with explicit gaps

The [ACP lifecycle](https://agentclientprotocol.com/protocol/v1/overview) uses
capability negotiation followed by `session/new` or `session/load`,
`session/prompt`, streamed `session/update`, and `session/cancel`. The client
also mediates permissions, filesystem, and terminal requests. Extensions are
capability-advertised instead of assumed.

[goose's ACP provider documentation](https://goose-docs.ai/docs/guides/acp-providers)
shows Claude Code and Codex running through the same provider interface while
preserving their own subscriptions and accepting MCP extensions. It also
documents two warnings Coding OS must design around: ACP resume/fork is not yet
available there, and the ACP session id differs from the goose session id.

Therefore the supervisor must persist both its own run id and the provider's
native thread id. An external ACP adapter may honestly advertise missing
resume/fork rather than simulating parity.

### LangGraph and Agent Framework: deterministic workflow above agents

[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview) separates
stateful orchestration from agent implementations and emphasizes durable
execution, persistence, streaming, and human control. Its
[multi-agent patterns](https://docs.langchain.com/oss/python/langchain/multi-agent)
distinguish centralized subagents, handoffs, routers, and custom workflows;
those are policy choices, not provider features.

[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)
likewise treats sequential, concurrent, handoff, and group collaboration as
graph workflow patterns with checkpointing and OpenTelemetry. This supports a
deterministic supervisor above adapter-owned runtimes instead of agent-to-agent
free chat as the primary control plane.

### Official Codex: native subagents and an MCP server

Codex already has native parent-controlled
[subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents) with
per-agent models, reasoning effort, and sandbox overrides. It can also run as
an [MCP server](https://learn.chatgpt.com/docs/mcp-server), exposing a start
operation and a reply operation. OpenAI's
[Agents SDK integration guide](https://developers.openai.com/api/docs/guides/agents/integrations-observability#mcp)
demonstrates a manager coordinating specialist agents, handoffs, guardrails,
and tracing while Codex remains the coding runtime.

The Codex adapter should use those official surfaces directly. Wrapping Codex
through ACP is an interoperability option, not a reason to discard native
thread, steer, sandbox, or tracing capabilities.

## Internal contracts

### Runtime identity

Every supervised run persists:

```text
run_id                 Coding OS stable id
adapter_id             claude | codex | future manifest id
native_thread_id       provider SDK/CLI thread id
parent_run_id          nullable supervisor parent
task_id                board task pointer
role                   provider-neutral role/formula
status                 queued | running | waiting | completed | failed | cancelled
capability_snapshot    immutable negotiated features for this run
workspace              resolved project/workspace identity
```

The Hub and traces use `run_id`; the adapter translates to
`native_thread_id`. This prevents the same id-space split already found in the
Hub transcript bridge.

### Runtime port

Each interactive adapter implements the same semantic operations:

```text
discover() -> RuntimeDescriptor
capabilities() -> CapabilitySet
start(request) -> RunHandle
load(native_thread_id) -> RunHandle
prompt(run, message) -> TurnHandle
steer(run, message) -> TurnHandle
cancel(run) -> Ack
events(run, cursor) -> AsyncIterator[RuntimeEvent]
transcript(run, page) -> TranscriptPage
close(run) -> Ack
```

Capabilities include start, load, resume, steer, cancel, fork, structured
output, permissions, sandbox modes, tool policy, MCP, usage, and context-window
signals. The supervisor routes by capability and policy, never by hardcoded
provider names.

### Normalized event envelope

Adapter events normalize only the cross-runtime control plane:

```text
message | reasoning | plan | tool_start | tool_update | tool_end |
permission | usage | warning | error | completed
```

Each event retains the native payload under an adapter-owned extension field.
The normalized envelope powers Hub status, traces, cancellation, and budgets;
it must not erase provider-specific details.

### Supervisor output

Children return typed `EvidenceBundle` or artifact references to their parent,
not an unbounded transcript dump. The parent receives the smallest upstream
slice required by the formula chain. This preserves Coding OS's minimal-context
and evidence-first contracts.

## Scheduling and safety invariants

- One mutable scope has one writer lease; concurrent researchers are read-only.
- A run's adapter and capability snapshot never change after creation.
- Cancellation propagates parent to children and is idempotent.
- Budgets cover turns, wall time, tokens/cost when exposed, and child count.
- Checkpoints precede external side effects and fan-in transitions.
- Retry reuses an idempotency key and never silently replays an uncertain write.
- Permission requests route through one supervisor policy and remain visible in
  Hub; an adapter may enforce stricter limits.
- A child may fail independently; the workflow declares fail-fast, quorum, or
  best-effort behavior before dispatch.
- Core imports no provider SDK. Adapter manifests advertise runtime entrypoints
  and capabilities.

For this meta-project, the existing prohibition on agent worktree isolation
still applies. Consumer projects may opt into their existing PR/worktree mode,
but the supervisor must select isolation from project policy rather than assume
worktrees are universally safe.

## Delivery phases

### Phase 1 — Shared runtime port

Extract Hub start/load/prompt/steer/cancel from the Claude-only route into the
runtime port. Migrate Claude first with behavior parity, then add Codex through
its official SDK/app-server. Keep transcript providers as the read side of the
same adapter boundary.

Acceptance: Claude and Codex can each start, continue, stream, cancel, and load
through identical core calls; unsupported capabilities are visible, not faked.

### Phase 2 — Durable supervisor

Add supervisor runs, parent-child edges, capability snapshots, checkpoints,
budgets, and task/scope leases. Reuse board tasks, formula dispatch, cognition
traces, and EvidenceBundle validation instead of creating parallel state
systems.

Acceptance: a deterministic two-child fan-out/fan-in survives process restart,
cancels cleanly, and cannot create two writers for one scope.

### Phase 3 — Mixed-adapter policies

Add role-to-capability routing and adapter preferences. Start with parallel
read-only research/review children; enable writer children only after leases,
idempotency, and approval flows are verified.

Acceptance: one parent can route research to Claude, implementation to Codex,
and review to either adapter while every decision and artifact remains traced.

### Phase 4 — ACP compatibility

Add an ACP runtime adapter or expose the Coding OS runtime port as an ACP client
boundary for external agents. Keep native Claude and Codex adapters available
when ACP lacks a required capability.

Acceptance: an ACP-compatible third-party coding agent can join without a core
code change; capability negotiation prevents unsupported resume/fork paths.

### Phase 5 — Hub control plane

Render adapter/model badges, parent-child DAG, live state, permissions, budget,
artifacts, and trace links. The run id is the UI identity; native thread ids are
diagnostic metadata.

Acceptance: operators can identify which adapter owns every run, inspect the
workflow tree, approve/deny blocked work, cancel a subtree, and open the correct
native transcript.

## Rejected alternatives

| Alternative | Reason |
|---|---|
| Import a full multi-agent framework | Duplicates board, roles, formula chains, persistence, and tracing; raises migration and dependency cost without solving native CLI identity. |
| Use only ACP internally | Current implementations have capability gaps, while Coding OS needs native steer/resume/hooks/evidence semantics. |
| Use only a model-provider gateway | Provider switching is not native-agent switching; it loses Claude Code/Codex tools, sandbox, sessions, subscriptions, and hooks. |
| Let agents freely message one another | Hard to checkpoint, budget, cancel, reproduce, or prove; typed supervisor transitions provide a stable control plane. |
| Hardcode Claude/Codex routing in core | Violates adapter autonomy and makes the next adapter a kernel change. |

## Implementation gate

This research authorizes design decomposition, not immediate broad
implementation. Before Phase 1 code changes, create a dedicated task with the
runtime-port schema, migration path for the current Claude route, Codex SDK
compatibility checks, failure semantics, and a final adapter-parity matrix.
