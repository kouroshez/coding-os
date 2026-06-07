---
id: TASK-083
title: "Codex CLI 0.135.0 hook parity — apply_patch/Edit/Write matchers + tool_input normalization + hook-trust install"
swimlane: infra
kind: feature
epic: null
labels: [codex, hooks, enforcement, supersedes-TASK-081]
status: archive
priority: P1
appetite: "1d"
created: 2026-06-04
started: null
completed: null
agent_session: ses-claude-20260606-135311-dd32
depends_on: []
blocked_by: []
references: []
---
# TASK-083: Codex CLI 0.135.0 hook parity — apply_patch/Edit/Write matchers + tool_input normalization + hook-trust install

**Outcome (one sentence):** Codex reaches near-Claude enforcement parity using the real 0.135.0 hook surface (no server-side backstop needed — supersedes TASK-081). Four parts: (1) update src/adapters/codex/adapter.yaml::hook_capabilities to declare PreToolUse/PostToolUse matchers apply_patch|Edit|Write + MCP tool names, SessionStart source `compact`, and new events PreCompact/PostCompact/PermissionRequest/SubagentStart/SubagentStop; (2) NORMALIZE tool_input — Codex apply_patch uses tool_input.command (a patch blob), NOT tool_input.file_path; add a shared helper in cos-env.sh that extracts the edited path from either Claude's file_path OR Codex's apply_patch blob, and route the ~20 enforce-*/block-*/capture-* hooks through it so they fire correctly on Codex edits; (3) HOOK-TRUST — Codex hash-trusts non-managed hooks and SKIPS them until trusted via /hooks; make install.sh register trust or emit managed-hook config, else document the trust step in cos init output; (4) re-evaluate whether the codex dispatcher coalescing is still needed now that individual matchers work. Regen adapter templates + golden; verify gates actually fire AND block on a real `codex exec` apply_patch edit (not just rendered config).

## Read First
- docs/engineering/adapter-parity.md
- src/adapters/codex/adapter.yaml
- src/core/hooks/cos-env.sh
- https://developers.openai.com/codex/hooks

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** ...
- **When** ...
- **Then** ...

## Work Log
