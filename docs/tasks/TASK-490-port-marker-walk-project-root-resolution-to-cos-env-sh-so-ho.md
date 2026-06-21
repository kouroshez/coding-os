---
id: TASK-490
title: "Port marker-walk project-root resolution to cos-env.sh so hooks never create nested .coding-os when CLAUDE_PROJECT_DIR is unset"
swimlane: core
kind: bug
epic: null
labels: [state-resolution, hooks, pre-launch, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-06-20
started: 2026-06-20
completed: 2026-06-20
agent_session: ses-claude-20260620-223048-0760
depends_on: []
blocked_by: []
references: []
---
# TASK-490: Port marker-walk project-root resolution to cos-env.sh so hooks never create nested .coding-os when CLAUDE_PROJECT_DIR is unset

**Outcome (one sentence):** cos-env.sh resolves the coding-os project root via a pure-Bash upward marker-walk that MIRRORS database.py::_find_project_root_from_cwd exactly (same _ROOT_MARKERS set + .coding-os/-co-location requirement) plus an explicit hard-stop below $HOME and /, used only when COS_STATE_DIR is the bare default AND CLAUDE_PROJECT_DIR/COS_PROJECT_ROOT are unset — so a hook firing from a subdir (cwd=src/backend) resolves COS_STATE_DIR to <root>/.coding-os instead of creating a stray nested .coding-os/, and shell and Python provably agree on one root (no split-brain), locked by a parity test.

## Read First
- src/core/hooks/cos-env.sh
- src/core/thinking_os/database.py
- docs/engineering/state-files.md

## Repro Steps
cd /Users/ciro/Files/Project/streamos/src/backend && env -u CLAUDE_PROJECT_DIR -u COS_PROJECT_ROOT -u COS_STATE_DIR bash -c 'source /Users/ciro/Files/Project/streamos/.claude/hooks/cos-env.sh; echo "$COS_STATE_DIR"' → today resolves a relative .coding-os under src/backend (bug); expected <root>/.coding-os.

## Resolution Order (cos-env.sh, only when COS_STATE_DIR is the bare `.coding-os`)
1. COS_STATE_DIR set to a non-default value → used verbatim (unchanged from today).
2. CLAUDE_PROJECT_DIR set → `$CLAUDE_PROJECT_DIR/.coding-os` (unchanged from today).
3. COS_PROJECT_ROOT set → `$COS_PROJECT_ROOT/.coding-os` (explicit escape hatch; the documented VSCode settings.json workaround).
4. Upward marker-walk (the fix): from `$PWD` resolved with `cd -P` (Rule 5), walk parents; accept the first ancestor that has a `.coding-os/` dir AND co-locates one of _ROOT_MARKERS (.git, .coding-os.yaml, pyproject.toml, package.json, go.mod, AGENTS.md) — identical contract to database.py; else fall back to the innermost bare `.coding-os/`. HARD-STOP below `$HOME` and `/`: never inspect or accept `$HOME/.coding-os` (the global hub).
5. No match → leave the relative `.coding-os` default (today's behavior; no regression).

## Acceptance (G/W/T) — *this IS the Definition of Done*

1. **Given** a project with `.coding-os/` + a marker at root and both `CLAUDE_PROJECT_DIR` and `COS_PROJECT_ROOT` unset, **When** a hook sources cos-env.sh with cwd=`<root>/src/backend`, **Then** `COS_STATE_DIR == <root>/.coding-os` (NOT `src/backend/.coding-os`).
2. **Given** the upward walk reaches `$HOME` without finding a marked `.coding-os/` below it, **When** resolving, **Then** it never selects `$HOME/.coding-os` (the global hub) and falls back to the relative default.
3. **Given** a stray nested `src/backend/.coding-os/` (no co-located marker) and a marked root above it, **When** resolving from `src/backend`, **Then** the walk skips the stray and anchors on the marked root (same marked-ancestor preference as database.py:96-103).
4. **Given** `COS_STATE_DIR` set to a non-default value OR `CLAUDE_PROJECT_DIR` set, **When** sourcing, **Then** behavior is byte-identical to today (strict superset; existing test `test_claude_project_dir_anchors_default_state_dir` and `test_default_state_dir` still pass).
5. **Given** a repo under a `/tmp` symlink (macOS `/tmp` -> `/private/tmp`), **When** walking, **Then** `$PWD` and `$HOME` are resolved (`cd -P`) before the boundary comparison (Critical Rule 5).
6. **Given** a battery of fixture trees (marked root, nested stray, no-marker, monorepo .git-above-root), **When** resolved by BOTH the shell walk and `database.py::_find_project_root_from_cwd`, **Then** they return the identical root — enforced by a new parity test so the two implementations can never silently drift.

## Deliverables
- `_cos_find_project_root()` pure-Bash helper in cos-env.sh (defined before the line-34 case), no python spawn.
- Corrected line-29 comment (drop the false `.coding-os.yaml`-parse claim; describe the real precedence) + a DRIFT-WARNING comment cross-referencing database.py::_ROOT_MARKERS (same pattern as the existing _detect_agent_runtime drift note).
- SSOT contract section in docs/engineering/state-files.md documenting the resolution order + marker set + $HOME stop (Rule 19 — docs are the contract).
- Tests in tests/test_hooks.py: the 5 acceptance cases above + the shell↔Python parity test (#6).

## Verify
make verify-hooks · uv run --extra rag pytest tests/test_hooks.py -q · python src/core/thinking_os/server.py --test

## Out of Scope (deferred — see TASK-491)
- Consolidating the ~9 cwd-only Python resolvers + logging_os.config onto resolve_db_path, and adding the $HOME hard-stop to database.py. None CAUSE this bug; bundling widens blast radius on a max-symlink-reach src/core change.

## Work Log
- 2026-06-21 [claude]: Edit cos-env.sh
- 2026-06-21 [claude]: Edit test_hooks.py
- 2026-06-21 [claude]: Edit test_hooks.py
- 2026-06-21 [claude]: commit 13e48dc86e — fix(hooks): marker-walk project-root resolution in cos-env.sh (no nested .coding-os from subdirs)
- 2026-06-21 [claude]: Ported database.py marker-walk to cos-env.sh (_cos_find_project_root, pure Bash, $HOME hard-stop, cd -P). +SSOT…
- 2026-06-21 [claude]: Edit cos-env.sh
- 2026-06-21 [claude]: Edit test_hooks.py
- 2026-06-21 [claude]: commit ee334e2676 — fix(hooks): guard cos-env.sh root-walk against infinite loop on relative PWD
- 2026-06-21 [claude]: Adversarial review (general-purpose agent) found a major infinite-loop bug on relative/stale $PWD (dirname fixpoint).…
- 2026-06-21 [claude]: Status transitioned to complete via cos task-done.
