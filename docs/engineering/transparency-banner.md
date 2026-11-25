<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-11-25 -->
# Transparency Banner — How the Banner and Board Lines Are Produced

Purpose: The implementation behind the `transparency-banner` rule: which hook computes each banner field, why the shapes are what they are, how board transitions reach the user, and the panel-scoping contract that keeps two tabs from leaking into each other.

Read when: Changing `session-context.sh`, `show-board-transition.sh`, `warn-abandoned-task.sh` or a banner field · debugging a missing, wrong or stale banner · adding a field to the banner.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

The rule an agent follows (echo the line, never fabricate one, echo board lines verbatim) is `src/core/rules/transparency-banner.md`. This page is the machinery; the agent does not need it to comply.

## Shapes

`classify-task-mode.sh` sets `.task-mode` per prompt and `session-context.sh` renders one of three shapes:

- **Casual** (`query`/`adhoc`/`chore`): `🔔 ses=<8-char-tail> · mode=<mode>`
- **Formal** (`formal`/`gov-required`/`propose-formal`/unset): `🔔 ses=<tail> · mode=<mode> · task=<T>·<status> · gate=<G> · skill=<S>`. `<status>` is the task's live board status, so a task left in `testing` never reads as active work.
- **Hook-internal** (`system`): suppressed. `classify-task-mode.sh` never writes `system` for a user prompt; it is reserved for hook-internal Bash, where there is no reply to prefix.

A panel whose session id is not seeded yet (turn 1, or a runtime that supplies the id late) still emits a banner, with `ses=new` and honest `-`/`none` fields. The earlier behaviour — suppress, on the theory that `ses=? · gate=unset` reads like a hung agent — traded a legible first turn for an invisible one, and the first turn is when an operator most needs to see the machinery running.

### `sup=` — the routing field

When `model_routing.enabled` is true, every shape gains `sup=<adapter>[/<model>][/<effort>]`, naming where the active role would dispatch, resolved by `resolve-supervise-route.sh` into the panel's `.supervise-route`. Under `suggest` mode the value is suffixed `?`. With supervision off the field is absent entirely. It is on the casual shapes too: which model is answering is a cost-and-capability fact the operator is entitled to on a one-line question, and the omission once made an enabled feature look switched off for days.

### `🚨 emergency=N`

When the board holds open `emergency` tasks, every shape gains `🚨 emergency=N` — the one board-wide field, because whichever session is open must see a fire, not only the session that filed it.

## Board transitions

The banner is computed when the prompt arrives, so it cannot show what the turn does. Every create or move is shown as it lands, one plain sentence per event, by `show-board-transition.sh` (PostToolUse on the `cos_task_*` tools and `cos task-*` commands). The review gate adds the ⏳ and 🔍 lines in its refusal under the same `BOARD_EVENTS` header ([agent-supervision.md § The review gate](agent-supervision.md)). The `Stop` hook `warn-abandoned-task.sh` repeats only what no tool call showed.

A `systemMessage` lands inside the tool-call row, which the desktop app folds, so the same hook hands the lines to the agent as `additionalContext` under `BOARD_EVENTS` and the agent echoes them. The title after `—` is data any session can write: the helper folds it to one line of plain text, so no newline or control character can start a forged event. Both emitters read `task_status_history` past a shared per-panel cursor (`.board-cursor`, the last shown history id), so no event is shown twice.

## SessionStart emission

Recovery rules, `[Session State]`, `[MCP Prime]` and enrichment blocks go into one hidden `additionalContext` envelope; `[Uncommitted Work]` and the active-task list go to stderr, the operator-visible channel. One envelope per invocation (under Codex, plain text only — its dispatcher re-wraps it); the enrichment runs on `startup`/`resume` and is suppressed on `compact`. Full contract: [state-files.md §S5](state-files.md).

## Panel scope

Each panel writes its own `$COS_PANEL_DIR` and the banner reader is strictly panel-scoped (no `$COS_AGENT_DIR` fallback), so two tabs never leak task, gate or skill into each other's banner. Skills loaded mid-turn show in the next banner. `.supervise-route` obeys the same scope with no exception: an agent-level fallback once rendered a six-day-old marker from another tab, and a neighbour's marker is a false statement the operator cannot spot, where `-` is a true one. Emitter: `src/core/hooks/session-context.sh`; atomic writer: `write-state.sh`; ownership table: [state-files.md](state-files.md).
