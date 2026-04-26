<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-07 -->
# Scripts & Make System — Full Audit

Purpose: Historical audit of the scripts/Makefile situation, captured mid-bootstrap. Kept as a reference for why certain structural decisions were made.
Read when: Investigating why `core/scripts/` is organized the way it is, or tracking down old gaps.
Skip when: You just need current behavior — all gaps listed here are now resolved.
Read next: `architecture.md` for the current state, `development-roadmap.md` for status.

## Current State

coding-os has **zero** task management scripts and **no** Makefile. The plan item `core/scripts/` was listed but never extracted.

NakoDigital has 12 scripts (1,523 lines) in `infrastructure/scripts/` that form the task management backbone:

| Script | Lines | Purpose | Portable? |
|--------|-------|---------|-----------|
| `task-start.sh` | 243 | Start task, create detail file, mark [/] | **90%** — needs `.claude/` path fixes |
| `task-done.sh` | 229 | Mark done, log to changes.log, record outcome | **90%** — same |
| `task-context.sh` | 249 | Show compact task context for agents | **85%** — uses domain-config.json |
| `task-create.sh` | 130 | Create new task + detail file | **95%** — almost universal |
| `task-block.sh` | 130 | Block task + log to questions.md | **95%** |
| `task-next.sh` | 83 | Show next recommended task | **95%** |
| `task-list.sh` | 62 | List tasks by status | **100%** — fully portable |
| `log-write.sh` | 131 | Write structured log entry | **100%** |
| `log-latest.sh` | 103 | Show recent log entries | **100%** |
| `log-search.sh` | 86 | Search log by keyword | **100%** |
| `ref-resolve.sh` | 68 | Resolve REF shortcodes to file paths | **80%** — needs foundation-map.md |
| `_lib.sh` | 9 | Shared output helpers (info/ok/warn/err) | **100%** |

## Hardcoded Dependencies in Scripts

### `.claude/` path references (must be parameterized):

| Script | Line | Reference | Fix |
|--------|------|-----------|-----|
| `task-start.sh` | 196 | `Path(".claude/thinking_os/thinking_os.db")` | → `COS_DB_PATH` env |
| `task-start.sh` | 217 | `Path(".claude/.thinking_os-gate")` | → `COS_STATE_DIR` env |
| `task-start.sh` | 223 | `sys.path.insert(0, ".claude/thinking_os")` | → `COS_BRAIN_DIR` env |
| `task-start.sh` | 240 | `bash .claude/hooks/write-state.sh .claude/.task-current` | → `COS_HOOKS_DIR` / `COS_STATE_DIR` |
| `task-done.sh` | 172 | `Path(".claude/thinking_os/record_outcome.py")` | → `COS_BRAIN_DIR` |
| `task-done.sh` | 186 | `Path(".claude/thinking_os/thinking_os.db")` | → `COS_DB_PATH` |
| `task-done.sh` | 199 | `nako_learn_narrative` | → `cos_learn_narrative` |
| `task-done.sh` | 208-216 | Same DB + sys.path | Same fixes |

### Project-specific dependencies:

| Script | Dependency | Universal? |
|--------|-----------|------------|
| `task-start.sh` | `docs/tasks.md` (index file) | Yes — any project can have this |
| `task-start.sh` | `infrastructure/scripts/domain-config.json` | **No** — project-specific mapping |
| `task-start.sh` | `docs/governance/templates/task-detail.md` | **No** — needs a default template |
| `task-context.sh` | `docs/foundation-map.md` (REF codes) | **No** — project-specific |
| `task-block.sh` | `docs/questions.md` | Yes — any project can have this |

## Make vs Custom CLI Analysis

### Current Makefile targets (NakoDigital):

**Universal (should be in coding-os):**
- `session-init` — show project phase, recent changes, task summary
- `task-start TASK=N` — start a task
- `task-done TASK=N TYPE=t MSG="m" WHAT="w" FILES="f"` — complete a task
- `task-block TASK=N REASON="r"` — block a task
- `task-create NUM=N TITLE="t"` — create new task
- `task-next` — show next recommended task
- `task-list` — list all tasks
- `task-context TASK=N` — show task context
- `log-write` / `log-latest` / `log-search` — change log management
- `ref REF=code` — resolve REF shortcodes
- `verify-hooks` / `test-hooks` — hook system verification

**Project-specific (should NOT be in coding-os):**
- `dev` / `down` / `logs` — Docker Compose
- `migrate` / `makemigrations` / `shell` — Django
- `lint-backend` / `test-backend` — Backend tools
- `lint-frontend` / `test-frontend` — Frontend tools
- `build-frontend` ��� Next.js build
- `deploy` / `rollback` / `backup` — Infrastructure
- `docs-lint` — Doc integrity checks
- `ci-gate` / `qa-gate` — CI/CD

### Recommendation: Hybrid Approach

**Keep Make** for the task/workflow system. Here's why:
1. `make` is available on every Unix system
2. Short commands: `make task-start TASK=43` vs `coding-os task start 43`
3. Tab completion works out of the box
4. No Python dependency for basic task operations
5. Composable: project-specific targets can extend the base Makefile

**Use CLI** (`coding-os`) only for:
- Installation: `coding-os init --agent claude,codex`
- Health checks: `coding-os health`
- Adapter management: `coding-os add-adapter codex`

### Proposed Makefile structure:

```
coding-os/templates/_base/Makefile.template   → Universal targets
coding-os/templates/django/Makefile.include   → Django-specific targets
```

Projects include both:
```makefile
# Project Makefile
include .coding-os/Makefile.base       # Universal targets from coding-os
include .coding-os/Makefile.template   # Stack-specific targets (if any)

# Project-specific targets below
```
