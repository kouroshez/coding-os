---
id: TASK-099
title: "Skills rich-anatomy program: standard + version-refresh tool + enrich/add all skills to 10/10"
swimlane: core
kind: feature
epic: null
labels: [skills, epic, rich-anatomy, ssot, ready]
status: in_progress
priority: P1
appetite: "3d"
created: 2026-06-04
started: 2026-06-04
completed: null
agent_session: ses-claude-20260527-151803-0b9f
depends_on: []
blocked_by: []
references: []
---
# TASK-099: Skills rich-anatomy program: standard + version-refresh tool + enrich/add all skills to 10/10

**Outcome (one sentence):** Every coding-os skill is rich (SKILL.md + scripts/ + references/ + assets/), data-driven, token-efficient, version-pinned to 2026. Canonical rich-skill standard exists as SSOT. A refresh script keeps reference versions current. Missing global skills (shell-scripting, technical-writing, sql-authoring, linux-sysadmin) and stack skills added.

## Read First
- docs/code-os-core-docs/how-to-write-skills.md
- src/core/rules/skill-enforcement.md
- src/templates/fastapi/skills/python-fastapi/scripts/new_endpoint.py

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a canonical rich-skill standard doc and a version-refresh tool exist
- **When** each in-scope skill is enriched/created against the standard (SKILL.md + scripts/ + references/ + assets/, data-driven, version-pinned) and committed individually
- **Then** no in-scope skill is thin (SKILL.md only), scripts pass `make verify-hooks`/syntax, references carry a dated version stamp the refresh tool can update, and `cos doctor` + skill-enforcement regen stay green

## Sub-tasks (per-commit units)
- [ ] S1: Rich Skill Standard doc (SSOT) + scoring rubric
- [ ] S2: version-refresh tool (`refresh-skill-versions.py` + per-skill `versions.json` convention)
- [ ] S3: reference impl — `shell-scripting` skill (gold template)
- [ ] S4: `technical-writing` skill
- [ ] S5: `sql-authoring` skill
- [ ] S6: `linux-sysadmin` skill
- [ ] S7: enrich thin core skills (testing-strategy, observability, deployment-cicd, llm-patterns, backend/frontend-fundamentals, codebase-explorer, agent-memory, incident-response)
- [ ] S8: enrich thin meta skills (7) with real references/
- [ ] S9: stack skills — docker, redis, supabase, php/wordpress, typescript, node, e2e
- [ ] S10: go-patterns + go-fiber + react-native deepening against 2026 refs
- [ ] S11: merge duplicates (frontend-design→nextjs-react, rn-patterns→rn-mobile)

## Work Log

## Work Log
