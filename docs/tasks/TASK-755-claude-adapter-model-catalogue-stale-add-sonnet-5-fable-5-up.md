---
id: TASK-755
title: "Claude adapter model catalogue stale \u2014 add Sonnet 5 / Fable 5, upgrade claude-agent-sdk off a pre-launch bundled CLI"
swimlane: adapters
kind: bug
epic: null
labels: [claude-sdk, hub, model-picker, ready]
status: archive
priority: P1
appetite: 2h
created: 2026-07-01
started: 2026-07-01
completed: 2026-07-01
agent_session: ses-system-auto-archive
depends_on: []
blocked_by: []
references: []
---
# TASK-755: Claude adapter model catalogue stale — add Sonnet 5 / Fable 5, upgrade claude-agent-sdk off a pre-launch bundled CLI

**Outcome (one sentence):** Hub chat model picker shows every currently-GA Claude model (Fable 5, Opus 4.8, Sonnet 5, Haiku 4.5) and formula/chat dispatch can actually reach Sonnet 5, with every hardcoded model-id reference in the adapter, its skill docs, and its stale-id scanner brought back into sync with the single adapter.yaml SSOT.

## Read First
- src/adapters/claude/adapter.yaml
- src/adapters/claude/sdk_dispatcher.py
- src/core/web/routes/config.py
- docs/adapters/claude-sdk.md
- src/templates/meta/skills/claude-sdk-integration/scripts/check_model_ids.py

## Repro Steps
Hub UI /model picker (src/core/web/routes/config.py::config_adapters reading src/adapters/claude/adapter.yaml::models) lists Opus 4.8 (default), Sonnet 4.6, Haiku 4.5 — no Sonnet 5, no Fable 5, even though both are GA per platform.claude.com/docs/en/about-claude/models/overview (verified live 2026-07-01). Root cause is twofold: (1) adapter.yaml's models: list is a hand-maintained snapshot that wasn't updated after the Sonnet 5 / Fable 5 launch, and independently drifted from src/templates/meta/skills/claude-sdk-integration/scripts/check_model_ids.py's own CURRENT dict (which also had a broken prefix-tolerance that silently never flagged prior-generation opus/sonnet ids) and SKILL.md prose; (2) installed claude-agent-sdk==0.2.95 bundles Claude CLI 2.1.170, released the same day as the Fable-5/Sonnet-5 GA cutover (2026-06-09) — verified via platform.claude.com/docs/en/about-claude/model-deprecations that claude-sonnet-4-6 and claude-opus-4-7 are still Active (not retired), so this is a picker-completeness/freshness bug, not an imminent-404 bug.

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** adapter.yaml::models is updated, **When** the Hub loads /api/config/adapters, **Then** the claude entry lists fable-5/opus-4-8/sonnet-5/haiku-4-5 with correct labels and exactly one default, no stale ids.
- **Given** check_model_ids.py's CURRENT map, its dated/alias tolerance, its test, and SKILL.md prose are updated to claude-sonnet-5, **When** check_model_ids.py is run against adapter.yaml, **Then** it reports zero findings; sdk_dispatcher.py's `_XHIGH_EFFORT_MODEL_PREFIXES` intentionally keeps the still-Active `claude-opus-4-7` and is a confirmed non-bug, not a required-zero target.
- **Given** pyproject.toml pins claude-agent-sdk>=0.2.110,<0.3.0, **When** `uv run python -c "import claude_agent_sdk; print(claude_agent_sdk.__version__)"` runs, **Then** it prints 0.2.110 or newer.
- **Given** the SDK pin changed, **When** docs/adapters/claude-sdk.md's SDK-floor line is checked, **Then** it matches the new pin + bundled CLI version.

## Work Log
- 2026-07-01 [claude]: committed 12608aa0 · 8 files
- 2026-07-01 [claude]: Verified live against platform.claude.com/docs (2026-07-01): added claude-fable-5 + claude-sonnet-5 to adapter.yaml…
