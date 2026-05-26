# Transparency Banner (Always Active)

> **Rule:** Every agent reply MUST begin with the `USER_BANNER` line emitted by `session-context.sh` (UserPromptSubmit `additionalContext`). One line, first thing the user sees, every turn.

## Why

The pulse block (`[coding-os pulse] ...`) is agent-only — it ships inside a `<system-reminder>` tag that the chat UI does NOT show to the user. Without an echo, the user has zero visibility into:

- which task is active (`.task-current`)
- which Cynefin gate is set (`.thinking_os-gate`)
- which skill is loaded (`.active-skill`)
- which audit is still in_progress (`docs/tasks/audits/audit-*.md`)

These four cognitive signals decide what the agent will and will not do this turn. Hiding them from the user breaks the trust contract — the user is supposed to be able to redirect when the agent is in the wrong state. They can't redirect what they can't see.

This rule closes that gap with the cheapest possible mechanism: agent literally copies one pre-rendered line into the visible reply.

## The contract

`session-context.sh` constructs and emits a line of one of three shapes, driven by `.task-mode` (`classify-task-mode.sh` sets this on every prompt):

**Casual chat** (`mode ∈ {query, adhoc, chore}`) — minimal banner:

```
🔔 ses=<8-char-tail> · mode=<mode>
```

**Formal work** (`mode ∈ {formal, gov-required, propose-formal}` or unset) — full cognitive state:

```
🔔 ses=<tail> · mode=<mode> · task=<T> · gate=<G> · skill=<S> · audit=<A>
```

**Hook-internal Bash** (`mode = system`) — banner suppressed entirely.

Inconsistency markers (`⚠️ wip=N but task=none — cos task-start <ID>`) are appended when the DB shows in-progress work the agent has not bound to.

The agent's response MUST start with the rendered banner line exactly as emitted. No reformatting, no translation, no abbreviation. Then a blank line. Then the normal reply.

Examples:

```
🔔 ses=648-639f · mode=query

[answering a how-does-X-work question — no banner clutter]
```

```
🔔 ses=648-639f · mode=formal · task=TASK-033 · gate=COMPLICATED 4 · skill=hook-authoring clean-code · audit=1(graph-os-deep-2026-05-25)·3-unchecked

[doing real work on a tracked task]
```

```
🔔 ses=648-639f · mode=formal · task=none · gate=unset · skill=- · audit=- ⚠️ wip=1 but task=none — cos task-start <ID>

[banner forces the agent to surface the drift before continuing]
```

## When the banner is missing

If `USER_BANNER` is not in the latest `additionalContext` (e.g. SessionStart with no UserPromptSubmit yet, or hook failure), the agent MAY skip the banner for that single turn. It must NOT fabricate a banner from memory — stale values mislead worse than no banner.

## What's NOT in the banner (by design)

- Per-tool counts (memory hits, graph queries, edits) — those live in the agent-only pulse `ACTIVITY` field and would be too noisy as a top-line every turn.
- Block/warn events — those already surface as stderr messages the user sees.
- Conversation summaries — that's the agent's normal reply.

Signals deliberately limited to **cognitive state** (what the agent thinks it's doing) rather than **action history** (what it just did). The user picks the wrong state ten seconds earlier than they'd notice the wrong action.

## Anti-patterns

- Skipping the banner because "nothing changed since last turn" — the user still benefits from continuous confirmation.
- Translating the banner ("🔔 =… · =…") — keep the literal field names so they match the underlying state files.
- Adding the banner to TOOL CALL descriptions or to the end of the reply — must be FIRST line, plain text.
- Synthesizing a banner when `USER_BANNER` is absent — accuracy beats coverage.
- Bundling the banner with code blocks, headers, or tool-call commentary — keep it standalone on line 1.

## Concurrency model — what the banner isolates

Cross-agent, cross-panel, and cross-project are all isolated by directory split:

| Setup | Banner accuracy | Why |
|---|---|---|
| Solo Claude / Codex / Cursor | ✅ accurate | own `$COS_AGENT_DIR` |
| Claude + Codex concurrent (same project) | ✅ each its own banner | different `$COS_AGENT_DIR` |
| Same agent in two projects | ✅ accurate | different `.coding-os/` |
| Same agent in two worktrees (`git worktree add`) | ✅ accurate | different filesystem |
| **Two panels of the SAME agent on SAME project** | ✅ **accurate per panel** | each panel writes to its own `$COS_PANEL_DIR = $COS_AGENT_DIR/panels/<panel-id>/`; `cos_panel_upgrade_from_payload` derives `<panel-id>` from the agent runtime's stdin `session_id` |

`session-context.sh` upgrades the panel id from stdin **before** materialising state, so two concurrent SessionStarts from sibling Claude tabs land in different `panels/<panel-id>/` subdirs and never overwrite each other's `session-id`, `.task-current`, `.thinking_os-gate`, `.active-skill`, `.doc-anchor`, etc. The `ses=<last-8>` field in the banner is the per-panel id tail — different value per tab confirms isolation.

Full personas × scenarios matrix (P1-P6 × S1-S7), per-file routing rationale, and the per-panel orphan-GC contract: [docs/engineering/state-files.md](../../docs/engineering/state-files.md).

## Accuracy guarantees (per-field)

| Field | Source | Ownership check | Edge cases handled |
|---|---|---|---|
| `ses` | `session-id` file → last 8 chars (panel-first, then agent-level fallback) | n/a (identity) | both files missing → seeded from `COS_PANEL_ID` |
| `mode` | `.task-mode` (`classify-task-mode.sh`) | n/a (per-turn write) | unset → `formal` default |
| `task` | `.task-current` via `_read_state` | accepts panel-id OR agent-id (transition window) | missing / stale → `none` |
| `gate` | `.thinking_os-gate` via `_read_state` | accepts panel-id OR agent-id | missing / stale → `unset` |
| `skill` | `.active-skill` via `_read_state` | accepts panel-id OR agent-id | missing / stale → `-` · **lag 1 turn**: skills loaded mid-turn show in NEXT banner |
| `audit` | grep `^status:` (YAML) OR `**Status:**` (markdown) | filesystem-current | no audits → `-` · `count(id)·N-unchecked` when verified=no rows exist |
| `⚠️` | DB `wip` vs `.task-current` | n/a | suppressed when consistent |

**Panel-level session-id initialization.** `cos_panel_upgrade_from_payload` writes `$COS_PANEL_DIR/session-id` when missing — seeding from the agent-level legacy `$COS_AGENT_DIR/session-id` if present, else from `$COS_PANEL_ID` itself. Without this, hooks that read `$COS_SESSION_FILE` (panel SSOT) on a resumed panel — where SessionStart:startup never fires — see an empty file, the ownership check rejects every state file, and the banner collapses to `ses=? · task=none · gate=unset` even though valid legacy state exists. The reader pairs this with a dual-id accept (panel-id OR agent-id) so legacy `.task-current` / `.thinking_os-gate` / `.active-skill` written before panel-aware writers shipped stay readable until the next session cycle re-stamps them.

Hardening invariants enforced by `_read_state`:
- If `_CURRENT_SESSION` cannot be determined (missing `session-id` file), ALL state files are rejected as untrusted.
- Multi-byte utf-8 (Persian skill names, etc.) is truncated by char count, not byte count.
- Special chars (`|`, `"`, newlines) are JSON-escaped before injection into `additionalContext`.

## See also

- [src/core/hooks/session-context.sh](../hooks/session-context.sh) — emits `USER_BANNER` inside `additionalContext`.
- [src/core/hooks/write-state.sh](../hooks/write-state.sh) — atomic (tmp + mv) writer of state files with session-id prefix.
- [src/core/hooks/inject-resume-prompt.sh](../hooks/inject-resume-prompt.sh) — SessionStart audit-resume block (one-shot per session).
- [src/core/rules/thinking_os.md](thinking_os.md) — gate semantics.
- [docs/engineering/state-files.md](../../docs/engineering/state-files.md) — full state-file ownership model + concurrency matrix.
