<!-- domain:DOCS | layer:reference | ssot:false | updated:2026-05-21 -->
# Audit — Complete the legacy `make task-*` → Scrumban migration

Task: [TASK-006](../TASK-006-purge-legacy-make-task-workflow-from-governance-template-doc.md)
Status: complete
Date: 2026-05-21

## Scope

The repo was mid-migration from the legacy file-based task system (`task-*.sh`
scripts + a flat `docs/tasks.md` index, driven by `make task-*`) to Scrumban
(`cos task-*` + `board_os` + per-task `docs/tasks/TASK-NNN-*.md`). This audit
records completing that cutover across the Makefile, scripts, hooks, and docs.

## Category table

| # | Category | Detection | Before | After | Verified |
|---|---|---|---|---|---|
| 1 | `Makefile.base` legacy targets shelling to `task-*.sh` | `grep 'COS_SCRIPTS./task-' src/templates/_base/Makefile.base` | 4 (start/done/block/create) | 0 — start/done/block delegate to `cos task-*`, create is a guidance stub | yes |
| 2 | Legacy `task-*.sh` scripts | `ls src/core/scripts/task-*.sh` | 7 (start·done·block·create·next·context·list) | 0 — deleted; no Python/hook caller (record_outcome.py is driven by `board_commands.py`) | yes |
| 3 | Hook help-text / comments naming `make task-*` or deleted scripts | `grep -n 'make task-\|task-*.sh' src/core/hooks/*.sh` | 9 hooks | advice → `cos task-*`; `docs/tasks.md` read/protect logic removed from block-protected-files / session-context / session-end / verify-agent-system | yes |
| 4 | Workflow SSOT docs describing the legacy system | manual | task-lifecycle.md, agent-workflow.md (×2 lineages each) | rewritten to Scrumban; status enum `icebox…archive`, kind enum corrected | yes |
| 5 | Other docs referencing `make task-*` / `docs/tasks.md` | `grep 'make task-' docs/ src/templates/` | docs-first-protocol, _meta/questions+roadmap, template-enforcement, hooks-reference, playbooks ×3 | all → `cos task-*` | yes |
| 6 | Stale Python comments/docstrings naming legacy scripts | `grep 'make task-\|task-done.sh' src/cli src/core/thinking_os` | setup.py, main.py, task_sync.py, task_parser.py, cognition.py, record_outcome.py, health_check.py | all → `cos task-*` | yes |
| 7 | Vestigial duplicates | manual | `src/core/docs/{task-lifecycle,agent-workflow}.md`, `_templates/task-list.md` (×2) | deleted; 2 engineering-doc links redirected to `docs/governance/agent-workflow.md` | yes |
| 8 | Slash-command discoverability gap | manual | README + workflow-guide only (TASK-005) | added to AGENTS.md (Tool Routing) + CONTRIBUTING.md (Contribution Loop) | yes |

## Key decisions

- **`make task-*` wrappers kept, not deleted.** `Makefile.base` retains
  `task-start` / `task-done` / `task-block` as thin `cos`-delegating wrappers
  for muscle-memory parity (consistent with the board-section wrappers).
  `task-create` became a guidance stub because `cos task-create` requires
  `--swimlane` / `--kind` flags a `make` target cannot supply.
- **`docs/tasks.md` is fully retired.** Hooks that read or protected it had
  that logic removed (the reads were already `-f`-guarded dead code in
  Scrumban-native projects); `session-end.sh` now resolves the active task
  from the `.task-current` marker, `verify-agent-system.sh` counts
  `docs/tasks/TASK-*.md` files.
- **`record_outcome.py` retained.** It is the outcome-recording step and is
  invoked by `cos task-done` (`board_commands.py`); only its legacy caller
  `task-done.sh` was removed.

## Verification

- `make verify-hooks` — syntax + shellcheck clean.
- `uv run --extra rag pytest src/core/thinking_os/tests/ -q` — 1195 passed.
- `uv run pytest tests/test_cli.py` — passed (TASK-007 verify fix).
- Golden snapshots regenerated; `tests/test_golden_parity.py` re-run.
- `tests/test_template_scaffold.py` re-run after scaffold doc edits + the
  `task-list.md` template removal (its assertion was dropped from the test).
- Post-fix grep for `make task-(create|start|done|block|next|context|list)`
  outside golden/audit/historical-audit files returns only the intentional
  wrapper-documentation table in `task-lifecycle.md` and the accurate
  hook-regex comments in `enforce-verify.sh` / `remind-learn-validate.sh`.
