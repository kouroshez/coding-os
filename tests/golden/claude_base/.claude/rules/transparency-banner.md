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

Inconsistency markers (`⚠️ wip=N but task=none — cos task-start <ID>`) are appended when the DB shows in-progress work the agent has not bound to. A context-budget marker (`⚠️ ctx=412k>150k — /clear after this task`) is appended when the transcript's last usage record exceeds `COS_CONTEXT_BUDGET` (default 150K tokens) — past that point every turn re-reads the whole prefix, so finish the bound task and recommend a fresh session instead of pulling the next task. Audit the burn rate with `cos doctor --tokens`.

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
