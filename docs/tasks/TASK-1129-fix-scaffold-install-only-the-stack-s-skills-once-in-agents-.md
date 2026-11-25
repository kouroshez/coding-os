---
id: TASK-1129
title: "fix(scaffold): install only the stack's skills, once, in .agents/skills; unwire disabled-module hooks"
swimlane: templates
kind: bug
epic: null
labels: [governance, docs-update, ready]
status: complete
priority: P1
appetite: 1d
created: 2026-11-25
started: 2026-11-24
completed: 2026-11-25
agent_session: ses-claude-20261124-204737-f93d
depends_on: []
blocked_by: []
references: []
---
# TASK-1129: fix(scaffold): install only the stack's skills, once, in .agents/skills; unwire disabled-module hooks

**Outcome (one sentence):** A consumer gets only the skills its stacks declare, stored once under .agents/skills and linked for Claude, and no hook or command from a module it turned off.

## Read First
- src/cli/_init_phase.py
- src/cli/_init_scaffold.py
- src/cli/skills_list.py
- src/core/subsystems.yaml
- docs/architecture/meta-project.md

## Repro Steps
cos init -a claude,codex -t fastapi -n probe --yes --no-register --no-git; ls probe/.claude/skills | wc -l (47, expected 18); ls probe/.codex/skills | wc -l (47 duplicate); rg nudge-model-routing probe/.claude/settings.json (wired while cognition is off)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a fresh fastapi scaffold, **When** skills are listed, **Then** only base + stack required/recommended + extra_skills minus disabled_skills are present, each stored once in .agents/skills.
- **Given** Claude and Codex, **When** each lists its skills, **Then** each skill appears exactly once.
- **Given** an existing project with all core skills, **When** cos update runs, **Then** unneeded untouched skills are removed, user-edited or extra ones kept, and the layout is migrated.
- **Given** cognition is disabled, **When** settings.json and the commands dir are read, **Then** no cognition hook is wired and no role-* command is present.
- **Given** the same scaffold before and after, **When** file count and always-on tokens are measured, **Then** both figures are recorded.

## Work Log
- 2026-11-25 [claude]: probe codex 0.171 debug prompt-input: .agents/skills + symlinked skill load; .codex/skills dup listed twice;…
- 2026-11-25 [claude]: probe claude 2.1.330 (haiku -p): symlinked .claude/skills/x -> .agents loads; .agents/skills alone not read
- 2026-11-25 [claude]: Plan: one selected_skill_names SSOT + reconcile at init/add/remove-stack/update; install.sh stays candidate pool…
- 2026-11-25 [claude]: part A: fastapi init 47->18 skills, 677->469 files; update migrates (edited copy kept, report honest); enable/disable…
- 2026-11-25 [claude]: commit b3c8a662f2 — fix(scaffold): install only the skills a project's stacks declare, not the whole core catalog
- 2026-11-25 [claude]: commit b3c8a662 part A; green: test_cli+stack_rule 298, scaffold 177, golden 10, adapters 24(+1 local .DS_Store),…
- 2026-11-25 [claude]: commit e706597194 — fix(scaffold): disabled-module hooks and role commands stay out; Codex gets no unread commands dir
- 2026-11-25 [claude]: part 3 committed: cognition-off settings 238->198 hook entries; role-* under cognition; no .codex/commands; files…
- 2026-11-25 [claude]: commit e0511fb0ac — fix(scaffold): skills are stored once in .agents/skills; Claude links its copies there
- 2026-11-25 [claude]: part 2 commit e0511fb0: claude+codex fastapi 432->377 entries, 174 real files; skills 1 copy (720K); migration keeps…
- 2026-11-25 [claude]: commit 5e9751bcdf — docs(rules): shipped banner and git rules keep the agent contract; coding-os internals move to docs
- 2026-11-25 [claude]: rules trim 5e9751bc: always-on AGENTS+rules 14098->12164, banner 2169->755, git-workflow 2010->1662; internals moved…
- 2026-11-25 [claude]: rules trim 5e9751bc: always-on AGENTS+rules 14098->12164, banner 2169->755, git-workflow 2010->1662; internals moved…
- 2026-11-25 [claude]: review r1 fixes: S1 manifest path validation, S2 parked edits survive, adapters from config (.agents/memory bug),…
- 2026-11-25 [claude]: also: add-adapter applies module gating, user hooks kept on re-register, '..' paths blocked, doctor walk loop-safe
- 2026-11-25 [claude]: left documented: Codex hooks.json keeps cognition entry (runtime allowlist gates it); .agents/skills literal in 4 places
- 2026-11-25 [claude]: commit 0058934ce4 — fix(scaffold): validate managed-file paths, keep parked edits, and read installed agents from config
- 2026-11-25 [claude]: commit f1e3e8687a — fix(scaffold): migrate legacy Codex manifests, keep alias edits shared, gate sync-all and re-init
- 2026-11-25 [claude]: r2 fixes f1e3e868; legacy claude+codex migration e2e: old dirs gone, 17 aliases+1 edit kept, idempotent, doctor 0 FAIL
- 2026-11-25 [claude]: commit 10f570a0b4 — fix(scaffold): Codex hooks.json also drops a disabled module's hooks; doctor flags one left wired
- 2026-11-25 [claude]: r3 fix 10f570a0: codex hooks.json gated (init 0, enable 1, disable 0); doctor flags wired disabled hook; cli 302,…
- 2026-11-25 [claude]: token figures are chars/4 tokens; r4 low: doctor stale test both agents; cos hooks = all shipped scripts…
- 2026-11-25 [claude]: commit 7467a43b9f — fix(doctor): a disabled module's hook left wired is flagged for both agents
- 2026-11-25 [claude]: Status transitioned to complete via cos task-done.
