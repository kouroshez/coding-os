<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-19 -->
# Hooks Reference — Every Hook, Every Category

Purpose: Canonical catalog of every hook coding-os ships. Lists what it fires on, what it blocks vs warns, and where its source lives. This is the file to read when `cos hooks-log` shows a hook you don't recognize, or when deciding whether to add a new hook vs extend an existing one.

Read when: onboarding to hook authoring · deciding which hook governs a specific behavior · debugging why a hook fired or didn't.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

**SSOT for registration:** [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml). Adapter template files are GENERATED from it by `make regen-adapter-templates`. Never hand-edit `src/adapters/*/settings.template.json` or `src/adapters/*/hooks.template.json` — the `warn-template-drift.sh` hook catches drift.

## Effect classes — what the agent sees

Every hook falls into one of three classes by effect:

| Class | Exit | Agent visibility | Example use |
|---|---|---|---|
| **BLOCK** | exit 2 + stderr | appears in agent context; tool call is refused | enforce pre-conditions, reject anti-patterns |
| **WARN** | exit 0 + stderr | advisory stderr in agent context; action proceeds | nudge toward best practice |
| **SILENT** | exit 0 (log-only) | invisible to agent; only `.coding-os/.hooks.log` records | passive observation |

## Per-line log format

Every hook calls `cos_log_hook` from [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh) which writes lines of the form:

```
[ISO-8601] [hook-name] [action] agent=X session=Y task=Z detail...
```

The `agent=X session=Y task=Z` triplet (added 2026-04-18) lets downstream tools separate activity across concurrent chats or runtimes:

```bash
cos hooks-log --agent claude                 # only claude
cos hooks-log --session ses-20260418-...     # one specific chat
cos hooks-log --task governance-xyz          # one specific task across sessions
cos hooks-log --hook enforce- --follow       # live stream of enforcement hooks
```

## Catalog

### Safety (7 hooks) — PreToolUse BLOCK

| Hook | Fires on | What it blocks |
|---|---|---|
| `block-secrets` | Bash, Write/Edit | AWS keys, tokens, `.env` leaks in commands or file content |
| `block-dangerous-commands` | Bash | `rm -rf`, `git push --force` to main, `git reset --hard` without flag |
| `block-uv-heredoc` | Bash | `uv run ... <<EOF` pattern (Rule 9 — silently hangs) |
| `block-bad-patterns` | Write/Edit | bare `except: pass`, mock-where-real-needed, known anti-patterns |
| `block-protected-files` | Write/Edit | edits to `CLAUDE.md`, `AGENTS.md`, `.coding-os/`, `src/core/rules/`, `src/core/hooks/` unless active task name contains `governance` / `docs-update` (Rule 8) |
| `block-migration-conflict` | Write/Edit | duplicate migration version numbers in `src/core/thinking_os/database.py` (Rule 10 — append-only) |
| `block-hardcoded-literals` | Write/Edit | `"django"` / `"claude"` / `"python-django"` as quoted literals in `src/cli/*.py` (Rule 12 — data-driven only) |

### Enforcement (8 hooks) — PreToolUse BLOCK

| Hook | Fires on | Blocks until |
|---|---|---|
| `enforce-skill` | Write/Edit on `.py`/`.ts`/`.tsx` | domain skill invoked (`clean-code`, `python-django`, `nextjs-react`, …) |
| `enforce-zoom` | Write/Edit after Complexity Gate = COMPLICATED/COMPLEX | `.coding-os/.zoom-checkpoint` records `PROBLEM_FRAMED` |
| `thinking_os-gate` | Write/Edit | `.coding-os/.thinking_os-gate` records `<CYNEFIN> <DIM>` classification |
| `enforce-task-start` | Write/Edit | `.coding-os/.task-current` points at an active task (or CLEAR-1 fast-path) |
| `enforce-doc-anchor` | Write/Edit on code | `.coding-os/.doc-anchor` points at a real doc (Rule 0 — docs-first) |
| `enforce-memory-check` | Write/Edit | `.coding-os/.memory-check` records a recent `cos_search` for past patterns |
| `enforce-template` | Write on specific markdown paths | proper template bootstrap ran (see [template-enforcement.md](template-enforcement.md)) |
| `enforce-verify` | `make task-done` | Verification Matrix commands passed for the changed domain |

### Observability (6 hooks) — SILENT log-only

| Hook | Event | What it records |
|---|---|---|
| `capture-observation` | PostToolUse Write/Edit | one row in `observations` (async; errors → `.coding-os/.capture-errors.log`) |
| `verify-changed-file` | PostToolUse | quick sanity (syntax, refs) on just-edited file |
| `track-skill` | PostToolUse | which skill was active when a tool fired |
| `session-context` | SessionStart + UserPromptSubmit | on `startup`: orphan-recover previous session, clear stale state, new session-id. On `compact`/`resume`: re-inject workflow rules. On `UserPromptSubmit` (Codex): lightweight context refresh only — no new session-id, no state reset |
| `session-end` | Stop | builds `session_summaries` row + runs `session_enrich` |
| `check-capture-worked` | Stop | reads `.capture-errors.log`; surfaces silent capture failures |

### Reminder (5 hooks) — PostToolUse WARN

| Hook | Fires on | Reminds about |
|---|---|---|
| `regen-reminder` | Edit on `src/templates/*/stack.yaml`, `src/adapters/*/adapter.yaml`, `src/core/hooks/registry.yaml`, or any `scaffold/**` | run `make regen-rules` / `make manifest-regen` / `make regen-adapter-templates` |
| `test-first-reminder` | Write/Edit on code without paired test | suggest writing test alongside code |
| `doc-sync-reminder` | Edit on `src/core/hooks/*.sh` or `src/core/thinking_os/tools/*.py` | docs in `docs/engineering/` / `src/core/docs/` may need sync |
| `remind-learn-validate` | PostToolUse at end-of-session | call `cos_learn_validate` on suggested patterns that were used |
| `remind-dogfood` | Edit on `src/core/**` | remember this repo dogfoods itself; run `make dogfood` after core edits |

### Cognition (3 hooks) — UserPromptSubmit nudges

Surface the right tool / discipline at prompt time so the agent never reaches a downstream BLOCK uninformed. Each is per-session debounced via a marker file under `$COS_AGENT_DIR/`.

| Hook | Fires on | Surfaces |
|---|---|---|
| `nudge-thinking-os` | UserPromptSubmit (heuristic) | Complexity Gate + Rule 18 task reconciliation for COMPLICATED+ prompts. Debounce: `.zoom-prompt-suggested` |
| `nudge-graph-os` | UserPromptSubmit (13 structural patterns, bilingual EN+FA) | Recommends specific `cos_graph_*` tool BEFORE Read/grep. Debounce: per-pattern marker under `.graph-nudge/` |
| `nudge-docs-first` | UserPromptSubmit (code-edit intent, bilingual EN+FA) — silent when `.doc-anchor` already populated or task-mode in `query/chore/adhoc` | Recommends `cos_doc_search` / `cos_doc_header` + points at [docs-first-protocol.md](../governance/docs-first-protocol.md) before any code Write/Edit (Rule 0 + 19). Debounce: `.docs-first-nudged` |

Codex receives the same hooks via the `codex-userpromptsubmit-dispatch.sh` dispatcher (concurrent UserPromptSubmit triggers coalesced through `src/adapters/codex/adapter.yaml::hook_dispatchers`). Cursor: rendered same as Claude.

### Meta (4 hooks) — BLOCK or WARN on governance docs

| Hook | Event | Purpose |
|---|---|---|
| `check-agents-md-size` | PostToolUse after AGENTS.md edit | warn if size > 30 KB (context budget) |
| `check-agents-md-refs` | PostToolUse after AGENTS.md edit | warn if referenced files/paths are missing |
| `warn-template-drift` | PreToolUse on generated files | WARN if hand-editing `src/core/rules/dimension-registry.md`, `src/core/rules/skill-enforcement.md`, `src/core/scaffold_manifest.json`, or `tests/golden/**` (generated — regenerate instead) |
| `warn-mcp-down` | SessionStart | WARN if thinking_os MCP can't be reached (session is cognitively blind) |

## Adding a new hook

1. Write the script: `src/core/hooks/<new-name>.sh`. Source [cos-env.sh](../../src/core/hooks/cos-env.sh) and call `cos_log_hook <new-name> <action> <detail>`.
2. Register in [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) with fields: `id`, `script`, `description`, `category`, `phase`, `events[]`.
3. `make regen-adapter-templates` — regenerates both adapter JSON files.
4. `make dogfood` — re-installs adapters in this repo (symlinks are already live, but settings JSON needs refresh).
5. `make verify-hooks` — syntax-check all hooks.
6. Write a test for expected BLOCK/WARN/SILENT behavior in `src/core/thinking_os/tests/` or `tests/`.

## Debugging — "why didn't my hook fire?"

Zero entries in `.coding-os/.hooks.log` for a hook you expected means the agent runtime isn't delivering the event. Checklist:

1. `cos hooks-list --agent claude` (or codex) — is the hook registered for that runtime?
2. Open `.claude/settings.json` (or `.codex/hooks.json`) — does the hook appear under the right matcher?
3. If you edited `registry.yaml` mid-session and forgot `make regen-adapter-templates`, templates drift — `warn-template-drift` catches that on next PreToolUse.
4. Runtime reload — Claude Code/Codex may need a restart to pick up new settings.

## Why log-only observability hooks don't surface in agent context

By design. Silent hooks are for *telemetry*, not *control*. Surfacing every `capture-observation` fire to the agent would flood context and crowd out the actual work. Use `cos hooks-log --follow` in a second terminal when you need to watch live.

## References

- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — SSOT registration
- [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh) — logging helper + agent detection
- [src/core/docs/agent-workflow.md](../../src/core/docs/agent-workflow.md) — when hooks fire in the Core Loop
- [docs/engineering/template-enforcement.md](template-enforcement.md) — enforce-template.sh detail
- [docs/engineering/skill-architecture.md](skill-architecture.md) — enforce-skill.sh detail
