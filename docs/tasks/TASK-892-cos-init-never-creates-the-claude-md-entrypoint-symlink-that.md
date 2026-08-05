---
id: TASK-892
title: "cos init never creates the CLAUDE.md entrypoint symlink that eject already assumes exists"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: in_progress
priority: P1
appetite: 1d
created: 2026-08-05
started: 2026-08-05
completed: null
agent_session: ses-claude-20260803-180632-5fca
depends_on: []
blocked_by: []
references: []
---
# TASK-892: cos init never creates the CLAUDE.md entrypoint symlink that eject already assumes exists

---
id: TASK-892
title: "cos init never creates the CLAUDE.md entrypoint symlink that eject already assumes exists"
swimlane: cli
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 1d
created: 2026-08-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-892: cos init never creates the CLAUDE.md entrypoint symlink that eject already assumes exists

**Outcome (one sentence):** Every consumer project gets the entrypoint file its agent runtime actually reads, created from a declaration in the adapter's own yaml rather than a literal in CLI code.

## Read First
- `src/cli/main.py:2722-2727` — `eject` already calls it "the generated symlink to AGENTS.md"
- `src/adapters/*/adapter.yaml` — where a runtime's own conventions belong (Rule 11)
- `src/cli/main.py:758-770` — the generated-artifact path set the manifest is built from

## Repro Steps
1. `cos init --agent claude --name probe --no-git --no-register --yes` into a scratch directory.
2. `ls -la probe/` — only `AGENTS.md` exists; `CLAUDE.md` is absent entirely.
3. Contrast with the meta-repo itself, where `CLAUDE.md` is a symlink to `AGENTS.md`, and with `cos eject`, which contains removal logic for a symlink nothing ever creates.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a project scaffolded for an adapter whose yaml declares an entrypoint filename,
- **When** `cos init` and `cos update` finish,
- **Then** that filename exists as a relative symlink to `AGENTS.md`, `cos eject` removes it, an adapter that declares none gets nothing, and no adapter filename is hardcoded in `src/cli/**` (Rule 11).

## Work Log
- 2026-08-05 [claude]: Edit adapter-authoring.md
- 2026-08-05 [claude]: Edit adapter-authoring.md
- 2026-08-05 [claude]: Edit adapter.schema.json
- 2026-08-05 [claude]: Edit adapter.yaml
- 2026-08-05 [claude]: Edit adapter.yaml
- 2026-08-05 [agent]: Edit _data_types.py
- 2026-08-05 [claude]: Edit _data_types.py
- 2026-08-05 [claude]: Edit _data_types.py
- 2026-08-05 [claude]: Edit adapter_registry.py
- 2026-08-05 [claude]: Edit adapter_registry.py
- 2026-08-05 [claude]: Edit _init_helpers.py
- 2026-08-05 [claude]: Edit main.py
- 2026-08-05 [claude]: Edit main.py
- 2026-08-05 [claude]: Edit main.py
- 2026-08-05 [claude]: Edit main.py
- 2026-08-05 [claude]: Edit update.py
- 2026-08-05 [claude]: Edit update.py
- 2026-08-05 [claude]: Edit update.py
- 2026-08-05 [claude]: Edit test_adapter_registry.py
- 2026-08-05 [claude]: Edit test_cli.py
- 2026-08-05 [claude]: Edit test_cli.py
- 2026-08-05 [claude]: Edit test_cli.py
- 2026-08-05 [claude]: Edit test_cli_update.py
- 2026-08-05 [claude]: Added adapter.yaml::entrypoint_file (claude=CLAUDE.md, codex=null) + schema/registry guard rejecting non-bare…
- 2026-08-05 [claude]: Verified by execution: cos init in a scratch dir produces CLAUDE.md -> AGENTS.md (relative symlink), cos eject…
- 2026-08-05 [claude]: committed eed07bb8 · 12 files
