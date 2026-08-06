---
id: TASK-345
title: "Hook chain latency budget: every Bash call pays 9 PreToolUse + 9 PostToolUse spawns (~p50 92ms each); verify-ish commands pay +1.2s"
swimlane: core
kind: refactor
epic: null
labels: [ready]
status: archive
priority: P2
appetite: 1d
created: 2026-06-10
started: 2026-06-10
completed: 2026-06-10
agent_session: ses-claude-20260610-182235-2444
depends_on: []
blocked_by: []
references: []
---
# TASK-345: Hook chain latency budget: every Bash call pays 9 PreToolUse + 9 PostToolUse spawns (~p50 92ms each); verify-ish commands pay +1.2s

**Outcome (one sentence):** Median wall-clock overhead per ordinary Bash tool call from coding-os hooks drops below 250ms total (measured via .hooks.log dt), by giving every Bash-matcher hook a first-line cheap fast-path (string match before any python3/jq spawn) and consolidating duplicate stdin parses — without changing any enforcement semantics.

## Read First
- src/core/hooks/registry.yaml
- src/core/hooks/record-verify-auto.sh
- src/core/hooks/enforce-verify.sh
- src/core/hooks/test-governor.sh

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a no-op Bash command (e.g. ls), **When** the full hook chain runs, **Then** summed dt across its Pre+Post hooks ≤ 250ms (today: ~9×40-90ms each side).
- **Given** verify-ish commands, **When** gated, **Then** record-verify-auto + enforce-verify + test-governor combined ≤ 600ms (today ~610+269+350ms).
- **Given** make verify-hooks + make test-hooks, **When** run, **Then** green.

## Work Log
- 2026-06-10 [claude]: Edit git-workflow.md
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit transparency-banner.md
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit anti-overengineering.md
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit memory.md
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit memory.md
- 2026-06-10 [claude]: Edit useBoardStream.ts
- 2026-06-10 [claude]: Edit api-contract-discipline.md
- 2026-06-10 [claude]: Edit test-discipline.md
- 2026-06-10 [claude]: Edit model-routing.md
- 2026-06-10 [claude]: Edit CosBoardPage.tsx
- 2026-06-10 [claude]: Edit CosBoardPage.tsx
- 2026-06-10 [claude]: Edit block-dangerous-commands.sh
- 2026-06-10 [claude]: Edit docs-lint.sh
- 2026-06-10 [claude]: Edit docs-lint.sh
- 2026-06-10 [claude]: Edit block-dangerous-commands.sh
- 2026-06-10 [claude]: Edit CosBoardPage.tsx
- 2026-06-10 [claude]: Edit CosBoardPage.tsx
- 2026-06-10 [claude]: Edit block-dangerous-commands.sh
- 2026-06-10 [claude]: Edit block-dangerous-commands.sh
- 2026-06-10 [claude]: Edit useBoardStream.test.ts
- 2026-06-10 [claude]: Edit how-to-write-skills.md
- 2026-06-10 [claude]: Edit agile-scrum-guide.md
- 2026-06-10 [claude]: Edit a reference document under docs/
- 2026-06-10 [claude]: Edit TechSpec_Template.md
- 2026-06-10 [claude]: Edit formulas-en.md
- 2026-06-10 [claude]: Edit block-secrets.sh
- 2026-06-10 [claude]: Edit formulas-v2.md
- 2026-06-10 [claude]: commit f961febcbd — docs(rules): relocate Why/rationale prose to critical-rules.md, slim always-on payload
- 2026-06-10 [claude]: Edit a reference document under docs/
- 2026-06-10 [claude]: Edit block-uv-heredoc.sh
- 2026-06-10 [claude]: Edit a reference document under docs/
- 2026-06-10 [claude]: Added pure-bash case fast-paths + spawn-dedup to all 18 Bash-matcher hooks. No-op ls chain process spawns: 34 jq+5 py =
- 2026-06-10 [claude]: Status transitioned to complete via cos task-done.
- 2026-08-06 [claude]: committed 1783d623 · 3 files
