---
id: TASK-031
title: "Codex adapter parity: enforce-commit-message hook + golden snapshot refresh + role-* dual-mode validation"
swimlane: infra
kind: chore
epic: null
labels: [codex, adapter, deferred, parity, golden]
status: icebox
priority: P3
appetite: "2h"
created: 2026-05-25
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-031: Codex adapter parity: enforce-commit-message hook + golden snapshot refresh + role-* dual-mode validation

**Outcome (one sentence):** When the project starts implementing the Codex adapter, fold in these deferred items: add enforce-commit-message.sh to src/adapters/codex/hooks.template.json, refresh tests/golden/codex_* snapshots, verify role-*.md dual-mode renders correctly under Codex CLI matcher rules. Do NOT pick up now — only when adapter work resumes.

## When to pick up

**NOT NOW.** Pick up only when the next session begins active work on the
Codex adapter (`src/adapters/codex/**`). At that point the agent will see
the open icebox task and reconcile against the audit findings below.

## Deferred items

1. **Codex hook-template gap** — `tests/test_adapter_parity.py::test_codex_covers_all_claude_bash_hooks` fails because `enforce-commit-message.sh` is missing from `src/adapters/codex/hooks.template.json`. Add it (or whitelist with reason in `CLAUDE_ONLY_WHITELIST`).
2. **Golden parity drift** — `tests/test_golden_parity.py` shows 6 failures: `compose.md` + `enforce-commit-message.sh` are not in any `tests/golden/<adapter>_<stack>/` snapshot. Refresh via `uv run python scripts/capture_golden.py --section <all>` after the Codex hook gap is closed.
3. **Role-* dual-mode validation under Codex CLI** — TASK-030 landed the dual-mode template at `src/core/thinking_os/agents/*.md`. Claude adapter consumes via symlink and works. Codex CLI has Bash-only matcher (no `Skill` matcher as of 2026-04). Verify the interactive-mode auto-detect table renders/behaves correctly when Codex invokes the equivalent slash command. If Codex doesn't surface the prompt at all, document under `src/adapters/codex/adapter.yaml::hook_capabilities` and adjust.

## Read First
- src/adapters/codex/adapter.yaml
- src/adapters/codex/hooks.template.json
- tests/test_adapter_parity.py
- docs/engineering/workflow-audit-2026-04-25.md

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** Codex adapter work has resumed,
- **When** the agent runs `uv run pytest tests/test_adapter_parity.py tests/test_golden_parity.py -q`,
- **Then** all tests pass (0 fail).

- **Given** `src/core/thinking_os/agents/*.md` dual-mode is live,
- **When** Codex CLI invokes `/role-reviewer`,
- **Then** the agent auto-detects task_id/scope/stack from repo state and returns Markdown + JSON envelope (same shape as Claude).

## Work Log
