# Transparency Banner (Always Active)

> **Rule:** Every agent reply MUST begin with the `USER_BANNER` line emitted by `session-context.sh` (UserPromptSubmit `additionalContext`). One line, first thing the user sees, every turn.

The pulse block is agent-only (the chat UI hides `<system-reminder>` tags), so the banner is the user's only view of the cognitive signals — task, gate, skill, roles — that decide what the agent does this turn. The user can't redirect what they can't see.

## The contract

`session-context.sh` emits one of three shapes, driven by `.task-mode` (`classify-task-mode.sh` sets it per prompt):

**Casual chat** (`mode ∈ {query, adhoc, chore}`):

```
🔔 ses=<8-char-tail> · mode=<mode>
```

**Formal work** (`mode ∈ {formal, gov-required, propose-formal}` or unset):

```
🔔 ses=<tail> · mode=<mode> · task=<T> · gate=<G> · skill=<S> · roles=<R>
```

`roles=<R>` shows the active role + its chain position (e.g. `reviewer 2/3`) when a chain is composed for a COMPLICATED/COMPLEX gate; `-` otherwise. It advances by work phase via `advance-role.sh`, only to a role already in the chain.

**Hook-internal Bash** (`mode = system`) — banner suppressed entirely.

Inconsistency markers (`⚠️ wip=N but task=none — cos task-start <ID>`) are appended when the DB shows in-progress work the agent has not bound to. A context-budget marker (`ℹ️ ctx=412k>200k — optional /compact; /clear only between unrelated tasks`) is appended when the transcript's last usage record exceeds `COS_CONTEXT_BUDGET` (default 200K tokens). It is an **informational cost/reliability signal for the user, not a stop directive** — the `ℹ️` (informational) prefix is deliberately distinct from the `⚠️` (act-now) one: the agent MUST NOT halt, refuse, or defer pulling the next task because of it. Keep working autonomously through related and queued tasks. To free context mid-run, prefer `/compact` (it summarizes — the working thread survives) and rely on the persistent memory layer (Agent Digest, agent memory, board, work-logs) that a fresh SessionStart re-inherits, so a `/clear` here does not reset accumulated knowledge to zero; `/clear` itself is the user's choice when switching to unrelated work. Audit the burn rate with `cos doctor --tokens`. A self-bypass marker (`ℹ️ bypasses=N self-issued CLEAR-1`) counts how many times this session manually set the `CLEAR 1` gate to skip the enforcement hooks (doc-anchor / skill / task-start / memory-check / zoom / anti-ambiguity); each is recorded with its justification in `$COS_PANEL_DIR/.clear1-bypass-log` for retro review. It is informational (`ℹ️`), not a stop directive — but a rising count means the discipline is being routed around rather than internalized, which is exactly what `/retro` should surface.

The agent's response MUST start with the rendered banner line exactly as emitted — no reformatting, translation, or abbreviation. Then a blank line. Then the normal reply. Example formal-work banner (the `⚠️` form forces the agent to surface unbound WIP before continuing):

```
🔔 ses=648-639f · mode=formal · task=TASK-033 · gate=COMPLICATED 4 · skill=hook-authoring clean-code · roles=analyst+2
🔔 ses=648-639f · mode=formal · task=none · gate=unset · skill=- · roles=- ⚠️ wip=1 but task=none — cos task-start <ID>
```

## Reply body — lean by default (the line after the banner)

After the banner + blank line, default to the **minimum that fully answers** — result first, then only the reasoning the user needs to act on (measured: median ~36 tokens, p90 ~128). Casual modes (`query`/`adhoc`/`chore`): a sentence or two, no preamble or "here's what I did" recap. Formal work: decision first, then the why; push verbose tables / file lists / verification logs to the task work-log or PR body. Deliberate reports (the user asked for the full analysis): be as thorough as the request demands — never trade a wanted report for brevity. Convention, not a hook (a Stop hook fires after the reply is billed).

## When the banner is missing

If `USER_BANNER` is not in the latest `additionalContext` (SessionStart with no UserPromptSubmit yet, or hook failure), the agent MAY skip the banner for that single turn. It must NOT fabricate a banner from memory — stale values mislead worse than no banner.

## What's NOT in the banner (by design)

The banner is limited to **cognitive state** (what the agent thinks it's doing), not **action history**. Per-tool counts live in the pulse `ACTIVITY` field, block/warn events already surface as stderr, and conversation summaries are the normal reply.

## SessionStart emission — hidden agent context vs visible operator alerts

The same hidden-vs-visible contract governs `SessionStart`, not only the per-prompt banner. `session-context.sh` routes its SessionStart output to two channels:

- **Hidden (agent context).** The recovery rules, `[Session State]`, `[MCP Prime]`, `[Agent Digest]`, and the startup/resume-only enrichment blocks (Project Trajectory, Autonomous Routing Evolution, token-economics) go into a single `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":…}}` envelope on stdout. Claude injects it but the chat UI hides it (the `<system-reminder>` treatment the banner relies on). This is the agent's memory inheritance — noise to the operator.
- **Visible (operator alerts).** `[Uncommitted Work]` (a prior session's dirty tree) and `[Session Start]` active-tasks go to **stderr** — the deliberate operator-only channel, same as `warn-mcp-down`'s liveness banner. These are signals a human must act on, so they stay in the chat.

Two invariants keep this cross-runtime safe:

1. **One envelope per invocation.** The Codex SessionStart dispatcher captures each delegate with `2>&1` and runs one `json.loads`, so a stray plain line merged with a JSON envelope would surface literal JSON to the agent. Under Codex, `session-context.sh` emits **plain text only** (the dispatcher re-wraps the whole card); the envelope split is Claude-only, and Codex has no operator-visible SessionStart chat so nothing is lost.
2. **Suppress the digest on `compact`.** A same-session auto-compact (Claude-only source) still holds the digest in working memory, so re-emitting it is the wasted re-dump that put a multi-thousand-token wall mid-chat. On `compact` only the minimal recovery (rules + `[Session State]`) is emitted; the digest/trajectory/routing block runs on `startup`/`resume` only. See [state-files.md §S5](../../docs/engineering/state-files.md).

## Anti-patterns

- Skipping the banner because "nothing changed since last turn" — the user still benefits from continuous confirmation.
- Translating the banner field names to another language — keep the literal field names so they match the underlying state files.
- Adding the banner to TOOL CALL descriptions or to the end of the reply — must be FIRST line, plain text.
- Synthesizing a banner when `USER_BANNER` is absent — accuracy beats coverage.
- Bundling the banner with code blocks, headers, or tool-call commentary — keep it standalone on line 1.

## Concurrency + per-field accuracy

Accurate per panel: each panel writes its own `$COS_PANEL_DIR`, and the reader is STRICTLY panel-scoped (no `$COS_AGENT_DIR` fallback), so two concurrent tabs never leak task/gate/skill into each other's banner — the `ses=<last-8>` tail differs per tab. One lag: skills loaded mid-turn show in the NEXT banner. Full per-field ownership table, panel-id resolution, and orphan-GC contract: [state-files.md](../../docs/engineering/state-files.md).

## See also

[session-context.sh](../hooks/session-context.sh) (emits `USER_BANNER`) · [write-state.sh](../hooks/write-state.sh) (atomic writer) · [thinking_os.md](thinking_os.md) (gate semantics) · [state-files.md](../../docs/engineering/state-files.md) (ownership + concurrency matrix).
