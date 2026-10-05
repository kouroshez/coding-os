---
id: TASK-1049
title: "Make cos adopt and eject safe for repos that already run an agent harness"
swimlane: infra
kind: bug
epic: null
labels: [ready]
status: icebox
priority: P1
appetite: 3d
created: 2026-10-05
started: null
completed: null
agent_session: null
depends_on: []
blocked_by: []
references: []
---

# TASK-1049: Make cos adopt and eject safe for repos that already run an agent harness

**Outcome (one sentence):** On a brownfield repo that already commits AGENTS.md, rendered agent settings and symlinked rules/skills, `cos adopt` changes nothing the user authored and `cos eject` restores the tree byte-identical to its pre-adopt state, as meta-project.md already promises.

## Read First
- docs/architecture/meta-project.md
- src/cli/install_commands.py
- src/core/scripts/install-adapter.sh
- src/adapters/claude/install.sh
- src/adapters/codex/install.sh

## Repro Steps
Sandbox (HOME and COS_REGISTRY_PATH pointed into a temp dir, --no-register): git-archive a ~3.8k-file polyglot monorepo that commits AGENTS.md (CLAUDE.md symlinked to it), a hook-rendered .claude/settings.json (38 hooks) and .codex/hooks.json (36), .claude/rules and .claude/skills symlinked into a tracked .agents/ dir, and eslint.config.mjs. Run `cos adopt --yes --agent claude,codex --no-register --no-index`, then `cos eject --yes`, then `git status --porcelain --untracked-files=all` against the baseline commit. Observed at main 5d016f64: adopt replaced both hook files (0 of 38 / 0 of 36 user hooks kept), wrote 151 links through the user symlinks into the tracked .agents/ dir (149 new, plus two same-named SKILL.md files replaced by links), wrote greenfield root files (tsconfig.json, eslint.config.js which ESLint resolves before eslint.config.mjs, vitest.config.ts, src/index.ts, src/shared/*, Makefile, .prettierrc.json, .editorconfig, changes.log) plus 43 scaffold docs, appended .claude/ .codex/ .mcp.json to .gitignore, and detected only typescript-plain (nested go.mod / pyproject.toml ignored). eject then deleted the user's AGENTS.md and CLAUDE.md (install_commands.py lists project/AGENTS.md unconditionally), deleted the two replaced SKILL.md files, and left the replaced hook files plus 45 untracked scaffold files behind.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a repo with a user-authored AGENTS.md and a CLAUDE.md symlink to it, **When** adopt then eject run, **Then** both files survive byte-identical.
- **Given** .claude/settings.json or .codex/hooks.json carrying user hooks, **When** adopt runs, **Then** the user hooks are kept (merge) or adopt stops with a clear message, and eject restores the pre-adopt bytes.
- **Given** .claude/rules or .claude/skills is a symlink into a tracked directory, **When** adopt links assets, **Then** nothing is written through it and no same-named user file is replaced.
- **Given** an existing repo root, **When** adopt applies a stack template, **Then** no greenfield scaffold file is written unless explicitly requested.
- **Given** build markers below the root (apps/*/go.mod, apps/*/pyproject.toml), **When** adopt detects stacks, **Then** each one is reported.
- **Given** adopt followed by eject, **When** git status runs, **Then** the tree equals the baseline.

## Work Log
