# Transparency Banner (Always Active)

> **Rule:** Every agent reply MUST begin with the `USER_BANNER` line emitted by `session-context.sh` (UserPromptSubmit `additionalContext`) — exactly as emitted, standalone on line 1, then a blank line, then the reply. The pulse block is agent-only (the chat UI hides `<system-reminder>` tags), so the banner is the user's only view of the cognitive signals — task, gate, skill — driving the turn; the user can't redirect what they can't see.

## The contract

**Every turn that produces a visible reply carries a banner.** There is exactly
one suppression, and it is not a turn the user ever sees (below). "Nothing
interesting happened" is not a reason to omit it — an operator who sees a banner
only sometimes cannot tell a quiet turn from a broken hook.

Three shapes, driven by `.task-mode` (`classify-task-mode.sh` sets it per prompt):

- **Casual** (`query`/`adhoc`/`chore`): `🔔 ses=<8-char-tail> · mode=<mode>`
- **Formal** (`formal`/`gov-required`/`propose-formal`/unset): `🔔 ses=<tail> · mode=<mode> · task=<T>·<status> · gate=<G> · skill=<S>`. `<status>` is the task's live board status, so a task left in `testing` never reads as active work.
- **Hook-internal** (`system`): suppressed — and only this. `classify-task-mode.sh` never writes `system` for a user prompt; it is reserved for hook-internal Bash, where there is no reply to prefix. Suppressing a banner nobody could read is not an exception to the rule above.

A panel whose session id is not seeded yet (turn 1, or a runtime that supplies
the id late) still emits a banner, with `ses=new` and honest `-`/`none` fields.
The earlier behaviour — suppress, on the theory that `ses=? · gate=unset` reads
like a hung agent — traded a *legible* first turn for an *invisible* one, and the
first turn is exactly when an operator most needs to see that the machinery is
running at all.

### `sup=` — the routing field

When `model_routing.enabled` is true, **every** shape gains
`sup=<adapter>[/<model>][/<effort>]` naming where the active role would dispatch,
resolved by `resolve-supervise-route.sh` into the panel's `.supervise-route`.
Under `suggest` mode the value is suffixed `?` to mark it a proposal that will
not execute. With supervision off the field is absent entirely — zero injected
characters, matching the feature's opt-in contract.

The field is on the *casual* shapes too, deliberately. Which model is answering
is a cost-and-capability fact the operator is entitled to on a one-line question
just as much as on a formal task, and the omission is what made an enabled
feature look switched off for days.

### `🚨 emergency=N` — the incident lane

When the board holds open `emergency` tasks, every shape gains
`🚨 emergency=N`. It is the one board-wide field, on purpose: the emergency lane
is the fast path for a fire, so whichever session is open must see it, not only
the session that filed it. With no open emergency the field is absent.

### Board transitions, live

The banner is computed when the prompt arrives, so it cannot show what the turn
does, and an agent may start, test, close and pull several tasks inside one
turn. Every create or move is therefore shown to the user the moment it lands,
as a `systemMessage` (the channel Claude Code shows to the user), one plain
sentence per event with the task's short title:

```
🚨 TASK-1100 created as EMERGENCY — Fix login crash
▶️ TASK-1100 started (in progress) — Fix login crash
🧪 TASK-1100 moved to testing — Fix login crash
✅ TASK-1100 completed — Fix login crash
🆕 TASK-1101 created in icebox — Add CSV export
```

`show-board-transition.sh` (PostToolUse on the `cos_task_*` tools and `cos task-*`
commands) emits it; the `Stop` hook `warn-abandoned-task.sh` repeats only what no
tool call showed (a move made by another path).

**The agent echoes each line, like the banner.** A `systemMessage` lands inside
the tool-call row, and the desktop app folds those rows by default, so on its own
the line is recorded but unseen. The same hook therefore hands the lines to the
agent as `additionalContext` headed `BOARD_EVENTS`, and the agent writes each one
verbatim, on its own line, in its next visible text — before its next tool call
when it is mid-work, so the user sees the move as it happens. Same discipline as
the banner: never reformat, batch, or translate a line, and never write one that
did not arrive in `BOARD_EVENTS`. Both read `task_status_history`
past a shared per-panel cursor (`.board-cursor`, the last shown history id), so
no event is ever shown twice. The agent's own view stays the pulse, which states
`task=<T>·<status>` and the emergency count from the DB on every prompt and so
survives compaction where earlier tool results do not.

Appended markers:

- `⚠️ wip=N but task=none — cos task-start <ID>` — act-now: surface and bind the unbound WIP before continuing.
- `ℹ️ ctx=NNNk>200k — optional /compact; /clear only between unrelated tasks` — **informational cost signal for the user, not a stop directive**: the agent MUST NOT halt, refuse, or defer pulling the next task because of it. Prefer `/compact` mid-run (the working thread survives); persistent memory (Agent Digest, board, work-logs) survives a `/clear`, which is the user's choice between unrelated work. Audit burn with `cos doctor --tokens`.
- `ℹ️ bypasses=N self-issued CLEAR-1` — count of manual gate bypasses this session (justifications logged to `$COS_PANEL_DIR/.clear1-bypass-log` for retro). Informational — but a rising count means discipline is being routed around, which `/retro` should surface.

## Reply body — lean by default

After banner + blank line: the **minimum that fully answers** (measured median ~36 tokens, p90 ~128). Casual modes → a sentence or two, no preamble or "here's what I did" recap. Formal work → decision first, then the why; verbose tables / file lists / verification logs go to the work-log or PR body. Deliberate reports the user explicitly asked for → as thorough as the request demands. Convention, not a hook.

## When the banner is missing

No `USER_BANNER` in the latest `additionalContext` (SessionStart before any prompt, or hook failure) → skip the banner for that single turn. NEVER fabricate one from memory — stale values mislead worse than no banner.

## SessionStart emission — hidden agent context vs visible operator alerts

Same hidden-vs-visible split as the banner: recovery rules, `[Session State]`, `[MCP Prime]` and enrichment blocks go into ONE hidden `additionalContext` envelope; `[Uncommitted Work]` + `[Session Start]` active-tasks go to **stderr** — the operator-visible channel. Two invariants: **one envelope per invocation** (under Codex, plain text only — its dispatcher re-wraps the card), and **the enrichment is suppressed on `compact`** (same-session memory already holds it; only minimal recovery re-emits — the enrichment runs on `startup`/`resume` only). Full contract: [state-files.md §S5](../../docs/engineering/state-files.md).

## Anti-patterns

Skipping the banner because "nothing changed" · translating or reformatting the field names · placing it anywhere but plain-text line 1 · synthesizing one when `USER_BANNER` is absent · bundling it with code blocks, headers, or tool-call commentary.

## Concurrency + per-field accuracy

Each panel writes its own `$COS_PANEL_DIR` and the banner reader is STRICTLY panel-scoped (no `$COS_AGENT_DIR` fallback) — two concurrent tabs never leak task/gate/skill into each other's banner (the `ses=` tail differs per tab). One lag: skills loaded mid-turn show in the NEXT banner. Ownership table + panel-id resolution: [state-files.md](../../docs/engineering/state-files.md). Emitter: [session-context.sh](../hooks/session-context.sh); atomic writer: [write-state.sh](../hooks/write-state.sh).

**`.supervise-route` obeys that scope with no exception.** An agent-level
fallback once rendered a six-day-old marker from another tab inside a fresh
panel. A cross-panel read is worse than an empty field: `-` is a true statement
about this turn, a neighbour's marker is a false one the operator cannot spot.
Every banner-visible cognitive marker is therefore panel-only, and absence
renders as `-`/`none`.
