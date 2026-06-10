# Transparency Banner (Always Active)

> **Rule:** Every agent reply MUST begin with the `USER_BANNER` line emitted by `session-context.sh` (UserPromptSubmit `additionalContext`). One line, first thing the user sees, every turn.

The pulse block is agent-only (inside a `<system-reminder>` the chat UI hides), so the banner is the user's only view of the four cognitive signals — active task, Cynefin gate, loaded skill, in-progress audit — that decide what the agent will and won't do this turn. Hiding them breaks the trust contract: the user can't redirect what they can't see.

## The contract

`session-context.sh` emits one of three shapes, driven by `.task-mode` (`classify-task-mode.sh` sets it per prompt):

**Casual chat** (`mode ∈ {query, adhoc, chore}`):

```
🔔 ses=<8-char-tail> · mode=<mode>
```

**Formal work** (`mode ∈ {formal, gov-required, propose-formal}` or unset):

```
🔔 ses=<tail> · mode=<mode> · task=<T> · gate=<G> · skill=<S> · roles=<R> · audit=<A>
```

`roles=<R>` shows the active role + its position in the composed chain (e.g. `reviewer 2/3`) when `auto-compose-roles.sh` stamped `.roles` for a COMPLICATED/COMPLEX gate; `-` when no chain is active. The active role advances by work phase via `advance-role.sh` (PostToolUse), but only ever to a role already in the chain. See [auto-compose-roles.sh](../hooks/auto-compose-roles.sh) · [advance-role.sh](../hooks/advance-role.sh).

**Hook-internal Bash** (`mode = system`) — banner suppressed entirely.

Inconsistency markers (`⚠️ wip=N but task=none — cos task-start <ID>`) are appended when the DB shows in-progress work the agent has not bound to.

The agent's response MUST start with the rendered banner line exactly as emitted — no reformatting, translation, or abbreviation. Then a blank line. Then the normal reply.

Examples:

```
🔔 ses=648-639f · mode=query

[answering a how-does-X-work question — no banner clutter]
```

```
🔔 ses=648-639f · mode=formal · task=TASK-033 · gate=COMPLICATED 4 · skill=hook-authoring clean-code · roles=analyst+2 · audit=1(graph-os-deep-2026-05-25)·3-unchecked

[doing real work on a tracked task]
```

```
🔔 ses=648-639f · mode=formal · task=none · gate=unset · skill=- · roles=- · audit=- ⚠️ wip=1 but task=none — cos task-start <ID>

[banner forces the agent to surface the drift before continuing]
```

## Reply body — lean by default (the line after the banner)

The banner is line 1; the body follows the blank line. Default to the **minimum that fully answers** — result first, then only the reasoning the user needs to act on (measured: median visible reply ~36 tokens, p90 ~128).

- **Casual modes** (`query`/`adhoc`/`chore`): a sentence or two; no preamble/postamble, no "here's what I did" recap.
- **Formal work**: decision/result first, then the why; push verbose tables, file lists, and verification logs to the artifact that outlives the turn (task work-log, audit doc, PR body).
- **Deliberate reports** (the user asked for the full analysis / design proposal): be as thorough as the request demands. This exemption is the point — never trade a wanted report for brevity.

This is a **convention, not a hook**: a Stop hook fires *after* the reply is generated and billed, so it cannot save the turn.

## When the banner is missing

If `USER_BANNER` is not in the latest `additionalContext` (SessionStart with no UserPromptSubmit yet, or hook failure), the agent MAY skip the banner for that single turn. It must NOT fabricate a banner from memory — stale values mislead worse than no banner.

## What's NOT in the banner (by design)

Per-tool counts live in the agent-only pulse `ACTIVITY` field; block/warn events already surface as stderr; conversation summaries are the agent's normal reply. The banner is limited to **cognitive state** (what the agent thinks it's doing), not **action history** — the user picks the wrong state ten seconds earlier than they'd notice the wrong action.

## Anti-patterns

- Skipping the banner because "nothing changed since last turn" — the user still benefits from continuous confirmation.
- Translating the banner field names to another language — keep the literal field names so they match the underlying state files.
- Adding the banner to TOOL CALL descriptions or to the end of the reply — must be FIRST line, plain text.
- Synthesizing a banner when `USER_BANNER` is absent — accuracy beats coverage.
- Bundling the banner with code blocks, headers, or tool-call commentary — keep it standalone on line 1.

## Concurrency + per-field accuracy

The banner is accurate per panel: each panel writes its own `$COS_PANEL_DIR = $COS_AGENT_DIR/panels/<panel-id>/`, and the reader is STRICTLY panel-scoped (no `$COS_AGENT_DIR` fallback) so two concurrent Claude tabs never leak task/gate/skill into each other's banner. The `ses=<last-8>` field is the per-panel id tail — a different value per tab confirms isolation. One lag: skills loaded mid-turn show in the NEXT banner. Full personas × scenarios matrix, per-field source/ownership table, panel-id resolution, and the orphan-GC contract: [docs/engineering/state-files.md](../../docs/engineering/state-files.md).

## See also

- [src/core/hooks/session-context.sh](../hooks/session-context.sh) — emits `USER_BANNER` inside `additionalContext`.
- [src/core/hooks/write-state.sh](../hooks/write-state.sh) — atomic state-file writer.
- [src/core/hooks/inject-resume-prompt.sh](../hooks/inject-resume-prompt.sh) — SessionStart audit-resume block.
- [src/core/rules/thinking_os.md](thinking_os.md) — gate semantics.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — full state-file ownership + concurrency matrix.
