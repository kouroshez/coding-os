# Audit — Roles Dispatch Dead Path (2026-05-23)

Forensic root-cause for the 11-semantic-role chain never firing in real sessions: `formula_dispatches=2` lifetime, `persona_selections=1`. User has never observed a role execute.

## Evidence

| Layer | Status | File:line |
|---|---|---|
| `cos_compose_chain` MCP registration | ✓ | [src/core/thinking_os/tools/cognition.py](../../../src/core/thinking_os/tools/cognition.py):1660 |
| `ClaudeSDKDispatcher` import path | ✓ | [src/adapters/claude/sdk_dispatcher.py](../../../src/adapters/claude/sdk_dispatcher.py):154 |
| 11 role YAMLs + agent.md catalog | ✓ | [src/core/thinking_os/roles/](../../../src/core/thinking_os/roles/) + [agents/](../../../src/core/thinking_os/agents/) |
| Formula composer logic | ✓ | [src/core/thinking_os/formula_composer.py](../../../src/core/thinking_os/formula_composer.py):183-246 |
| **Hook → agent action bridge** | ✗ | [src/core/hooks/nudge-thinking-os.sh](../../../src/core/hooks/nudge-thinking-os.sh):105 — emits "MANDATORY: cos_compose_chain" as plain text |
| Agent reads + executes the nudge | ✗ | DEAD — agents (verifiably including this one) read "MANDATORY" as advisory text and skip the tool call |

DB state confirms: `formula_dispatches=2` lifetime, both probably from manual tool-call experiments; `persona_selections=1`.

## Root cause

The system is **opt-in by design** per [src/core/thinking_os/server.py](../../../src/core/thinking_os/server.py) comments. `nudge-thinking-os.sh` writes the recommendation as an `additionalContext` string — Claude Code surfaces this as system text, agents read it, but there is **no mechanical hook that fires `cos_compose_chain`** when a `COMPLICATED+` gate is recorded.

Per the [Anthropic Certified Architect exam guide](../../code-os-core-docs/instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md) (Domain 1.4): *"prompt-based approaches have a non-zero failure rate; for deterministic compliance use programmatic enforcement (hooks, prerequisite gates)."* The current path is exactly the anti-pattern the guide warns against.

## Fix path (sequenced)

| # | Fix | Diff | Status |
|---|---|---|---|
| 1 | `/compose` slash command + nudge text update — gives agents a one-keystroke surface, doesn't change the opt-in posture but raises saliency | ~50 lines | **DONE — TASK-021** |
| 2 | Auto-trigger hook: when `.thinking_os-gate` records COMPLICATED+, spawn background python that calls `formula_composer` directly and writes the chain to `$COS_AGENT_DIR/.formula-chain.json` | ~80 lines (hook + helper) | **Phase 9** (deferred — needs `formula_composer` non-MCP entrypoint + session-context.sh integration) |
| 3 | Move chain composition into `cos_supervise` so the supervise tool's response always carries the chain (zero-opt-in for agents that already call supervise) | ~30 lines core | **Phase 9** |
| 4 | UI surface: roles tab on the Hub already renders `/api/roles/chain`; populate when fix 2/3 land | n/a | Free once 2/3 land |

## Why /compose first

- **No core change** — uses existing `cos_compose_chain` MCP tool.
- **Improves the prompt-side path** without committing to a deeper architectural rewrite while the project still has higher-leverage fixes pending (PRAGMA, graph viz, doctor panel).
- **Measurable**: every `/compose` invocation grows `formula_dispatches` and `persona_selections` by ≥1. Baseline before this task: 2 + 1 lifetime. Target after: every `COMPLICATED+` task adds rows.
- **Reversible**: removing `compose.md` from `src/core/commands/` rolls back without affecting any other system.

## Open questions

- **`/compose` adoption rate** — without telemetry on slash-command invocations, we can't directly measure. Proxy metric: `formula_dispatches` row growth over `task_outcomes` rows of kind `bug|feature|refactor`. Target ratio: ≥0.5 (half of non-trivial tasks compose a chain).
- **Phase 9 auto-trigger contract** — what task signals does `formula_composer` need that aren't already in the task's frontmatter? May require adding a `signals:` block to task templates.

## References

- [src/core/commands/compose.md](../../../src/core/commands/compose.md) — new slash command (TASK-021)
- [src/core/hooks/nudge-thinking-os.sh](../../../src/core/hooks/nudge-thinking-os.sh):105 — upgraded nudge text
- [docs/tasks/TASK-021-add-compose-slash-command-nudge-upgrade-for-role-chain-dispa.md](../../tasks/TASK-021-add-compose-slash-command-nudge-upgrade-for-role-chain-dispa.md)
