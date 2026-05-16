<!-- domain:CORE | layer:engineering | ssot:false | updated:2026-05-08 -->
# Task-Mode Matrix — Persona-Aware Enforcement

> P: Persona / mode classification produced by `classify-task-mode.sh` and how each enforcement hook gates itself against it.
> R: Authoring or modifying a hook that should behave differently for analytical, exploratory, or formal-implementation turns.
> S: Routine implementation work — every hook already reads the mode marker correctly.
> N: [hooks-reference.md](hooks-reference.md), [adapter-parity.md](adapter-parity.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why this exists

Rule 18 ("task reconciliation is mandatory") was uniformly applied to every
turn — a Q&A request like "explain how X works" got the same enforcement
chain as a multi-file refactor. That penalised exploration and forced the
agent to fabricate `exploratory-<slug>` markers that polluted the board.

The mode marker (`$COS_AGENT_DIR/.task-mode`) lets each enforcement hook
gate its own work without weakening Rule 18 — formal implementations
still go through the full chain; analytical turns no longer pretend to
be tasks.

The classifier is one hook (`classify-task-mode.sh`, UserPromptSubmit) so
adapter parity is automatic — every adapter that emits UserPromptSubmit
inherits the same persona model.

## The seven modes

| #  | Mode             | Trigger (priority order, first match wins)                                                       | What it represents                                              |
|----|------------------|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| 1  | `formal`         | `.task-current` already names a `TASK-NNN` for this session                                      | Picked-from-board work: full lifecycle                          |
| 2  | `gov-required`   | Prompt mentions `governance` / `critical-rules` / `src/core/rules/` / `registry.yaml` / `agents.md`  | Touching governance without an active gov task                  |
| 3  | `propose-formal` | Verbs: `implement\|build\|fix\|add\|ship\|refactor\|migrate\|optimi[sz]e\|deploy\|hotfix` (+FA)  | Implementation request: nudge user to create a task             |
| 4  | `query`          | Verbs: `what is\|why\|explain\|analy[sz]e\|look at\|review\|show\|list\|describe` (+FA)          | Read-only Q&A: enforcement skipped                              |
| 5  | `adhoc`          | Verbs: `explore\|investigate\|trace\|map\|audit\|deep dive` (+FA)                                | Exploratory dive: warn-only enforcement                         |
| 6  | `chore`          | Prompt < 80 chars, no implementation/Q&A signal                                                  | Quick fix / one-liner                                           |
| 7  | `system`         | Reserved for hook-internal Bash spawned by the kernel itself                                     | Background ops: full bypass (never set by classifier)           |

The classifier writes one of `formal | gov-required | propose-formal |
query | adhoc | chore`. `system` is opt-in — set by callers that need to
suppress all enforcement (background daemons, hook-spawned subshells).

`promote` is reserved for the runtime: `enforce-task-start.sh` flips
`adhoc` → `formal` when the user accepts a "ok " / "ok build it"
escalation cue.

## Hook gating contract

Every enforcement hook that wants to honour the mode reads
`$COS_AGENT_DIR/.task-mode` after its own file-path filter and exits 0
when the mode is `query | adhoc | chore | system`. Pseudo-code:

```bash
MODE_FILE="${COS_AGENT_DIR}/.task-mode"
if [[ -f "$MODE_FILE" ]]; then
  TASK_MODE=$(tr -d '\n\r' < "$MODE_FILE" 2>/dev/null | head -c 24)
  case "$TASK_MODE" in
    query|adhoc|chore|system) exit 0 ;;
  esac
fi
```

Hooks already wired:

| Hook                       | `query` | `adhoc` | `chore` | `system` | `formal` | `propose-formal` | `gov-required` |
|----------------------------|---------|---------|---------|----------|----------|------------------|----------------|
| `enforce-task-start.sh`    | skip    | skip    | skip    | skip     | enforce  | enforce          | enforce        |
| `enforce-skill.sh`         | skip    | skip    | skip    | skip     | enforce  | enforce          | enforce        |
| `enforce-zoom.sh`          | skip    | skip    | skip    | skip     | enforce  | enforce          | enforce        |
| `enforce-memory-check.sh`  | skip    | skip    | skip    | skip     | enforce  | enforce          | enforce        |

Safety hooks (`block-secrets`, `block-dangerous-commands`,
`block-protected-files`, `block-bad-patterns`, `block-uv-heredoc`,
`block-migration-conflict`, `block-hardcoded-literals`) ignore the mode
— they protect against irreversible damage regardless of intent.

## Acceptance (G/W/T)

- **Given** UserPromptSubmit fires with prompt `"explain the doctor flow"`
- **When** the agent attempts `Edit src/cli/doctor.py`
- **Then** `.task-mode` reads `query`; `enforce-task-start` / `enforce-skill`
  / `enforce-zoom` / `enforce-memory-check` exit 0; the safety hooks still
  fire.

- **Given** UserPromptSubmit fires with `"refactor src/cli/doctor.py to use
  pathlib"`
- **When** the agent calls `cos task-create` then `cos task-start TASK-NNN`
- **Then** `.task-mode` is `propose-formal` initially, then `enforce-task-start`
  enforces a TASK marker; on the *next* prompt the mode flips to `formal`
  because `.task-current` now names `TASK-NNN`.

- **Given** UserPromptSubmit fires with `"what is `_resolve_attribution`"`
- **When** the agent runs Read / cos_graph_query
- **Then** mode is `query`, no enforcement marker is required, and the
  agent never has to fabricate a TASK to read code.

## Adapter agnosticism

The marker file lives at `$COS_AGENT_DIR/.task-mode`. Every adapter that
ships UserPromptSubmit inherits the classifier through
`make regen-adapter-templates` — no per-adapter duplication. Adapters
without UserPromptSubmit support (early Codex builds) keep the legacy
behaviour: no mode marker → enforcement runs uniformly, which matches
the pre-mode baseline.

## See also

- [docs/governance/critical-rules.md](../governance/critical-rules.md) — Rule 18 (task reconciliation), Rule 7 (governance gating).
- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — `classify-task-mode` registration.
- [src/core/board_os/_agent_runtime.py](../../src/core/board_os/_agent_runtime.py) — `resolve_agent_session` (G1, attribution resolver) shares the same "stay adapter-agnostic" contract.
