---
id: TASK-002
title: "Claude adapter Q-bundle: SDK pins, dispatcher hardening, hook parity, permissions"
swimlane: infra
kind: refactor
epic: null
labels: [claude, adapter, sdk, permissions, hooks]
status: complete
priority: P1
appetite: "2d"
created: 2026-05-05
started: 2026-05-04
completed: 2026-05-04
agent_session: null
depends_on: []
blocked_by: []
references: []
---
# TASK-002: Claude adapter Q-bundle

**Outcome (one sentence):** Claude adapter aligned with claude-agent-sdk 0.1.73 (latest as of 2026-05-04) — system-prompt-preset opt-in restored, MCP allowlist closed, SubagentStart + PostToolUseFailure hooks declared, skill descriptions audited, adapter doc rewritten, SDK installed and verified via real `cos_dispatch_formula_run`.

## Read First
- [docs/adapters/claude-sdk.md](../adapters/claude-sdk.md)
- [adapters/claude/adapter.yaml](../../adapters/claude/adapter.yaml)
- [adapters/claude/sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py)
- [adapters/claude/settings.local.template.json](../../adapters/claude/settings.local.template.json)
- [core/hooks/registry.yaml](../../core/hooks/registry.yaml)

## Acceptance (G/W/T) — *this IS the Definition of Done*
- **Given** a Claude consumer project rendered from this repo with `uv sync --extra claude-sdk`
- **When** running `uv run --extra claude-sdk python scripts/e2e_dispatch_tool.py` after these changes
- **Then** all of the following hold:
  1. `claude-agent-sdk` resolves to `>=0.1.73,<0.2.0`; `mcp` resolves to `>=1.27.0`.
  2. `ClaudeSDKDispatcher` constructs `ClaudeAgentOptions` with `system_prompt={type:'preset',preset:'claude_code'}` (or documented append) and `setting_sources=['project']`.
  3. `settings.local.template.json` includes `mcp__coding-os__*` entry under `permissions.allow`.
  4. `core/hooks/registry.yaml` declares at least one `SubagentStart` and one `PostToolUseFailure` hook; `adapter.yaml::hook_capabilities` includes both events; `make regen-adapter-templates` produces no diff after run.
  5. `make verify-hooks` passes; `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py core/thinking_os/tests/test_dispatcher.py -q` passes.
  6. `e2e_dispatch_tool.py` reports `dispatcher: claude-sdk` and at least one formula returns `status=ok` with non-empty `output_json`.
  7. `docs/adapters/claude-sdk.md` covers full adapter surface (settings, hooks, permissions, skills, MCP, observability) — not just dispatcher.

## Work Log

### 2026-05-04 — Q-bundle landed

**Q.1 — pins:** bumped `claude-agent-sdk` floor from `>=0.1.0` to
`>=0.1.73,<0.2.0` and `mcp` floor from `>=1.26.0` to `>=1.27.0` in
`pyproject.toml`. `uv sync --extra claude-sdk --extra rag --extra graph_os
--extra board_os --extra web` resolves cleanly. `claude-agent-sdk==0.1.73`
+ `mcp==1.27.0` confirmed via `uv pip show`.

**Q.2 — dispatcher hardening:** `adapters/claude/sdk_dispatcher.py` now:
opt-in `claude_code` preset with `exclude_dynamic_sections=True` (cross-
cwd cache), `setting_sources=["project"]` (isolate from `~/.claude/`),
`permission_mode="dontAsk"` (headless), absolute-path assertion on
`agent_file`, Opus 4.7 → `effort="max"` gate, `mcp__coding-os__*` always
appended to allow-list, `skills=` forwarded from role frontmatter,
debug log of dispatch options. Added optional `model` field to
`DispatchRequest` (core stays agent-agnostic — generic concept).

**Q.3 — MCP allowlist:** added `"mcp__coding-os__*"` to
`adapters/claude/settings.local.template.json::permissions.allow`.

**Q.4 — hook parity:** `core/hooks/registry.yaml` `agent-presence`
entry extended with `PostToolUseFailure`, `SubagentStart`, `SubagentStop`
events. `adapters/claude/adapter.yaml::hook_capabilities` declares the
same. `core/hooks/agent-presence.sh` case-statement extended.
`make regen-adapter-templates` ran clean; `settings.template.json` now
has 17 event/matcher groups (was 14). `make verify-hooks` passes. No
`Task`-vs-`Agent` literal renames needed (no filters in core/cli).

**Q.5 — skills audit:** wrote `scripts/audit_skill_descriptions.py` —
all 11 skills under SDK limits (description ≤1024, listing ≤1,536).
Real bug: `core/skills/search/SKILL.md` had unquoted `:` inside the
description, which broke YAML parsing — fixed with single-quoted form.

**Q.6 — subagent skills:** added `skills:` frontmatter to 8 roles —
implementer/reviewer/refactorer = `[clean-code]`-flavored;
debugger/researcher = `[search, codebase-explorer]`; analyst/architect
= `[thinking_os]`; security_auditor = `[security-web, clean-code]`.
Dispatcher reads them from `agent_meta` and forwards to
`ClaudeAgentOptions(skills=…)` (validated as list[str] before use).

**Q.7 — doc rewrite:** replaced narrow dispatcher-only
`docs/adapters/claude-sdk.md` with full adapter reference: install,
settings, MCP, dispatcher, permissions, skills, plugins, observability,
verification, branding, gaps. 17 sections, ~370 lines. Changelog row at
the bottom.

**Verification:**
- `make verify-hooks` → OK (shell syntax + shellcheck warnings).
- `pytest core/thinking_os/tests/test_dispatcher.py` → **19 passed**.
- `pytest tests/test_adapters.py tests/test_adapter_parity.py tests/test_adapter_registry.py` → **58 passed**.
- `pytest core/thinking_os/tests/` → 1096 passed, 2 failed
  (`test_auto_reindex.py` × 2 — pre-existing 10s timeout in
  `core/hooks/auto-reindex-docs.sh`; last modified by commit `95f1dbd`,
  unrelated to this task).
- `python scripts/smoke_sdk_dispatch.py` → **SMOKE: PASS**, dispatcher
  spawned a real Claude Code sub-session for `debugger` (light
  intensity) in 19.9s, returned a valid `DebuggerOutput` JSON with
  `root_cause / fault_chain / fix_applied / regression_tests_added /
  prevention_recommendation / _meta`.

**Out of scope (deferred):** OTEL collector defaults in install.sh,
`PreCompact` / `PermissionRequest` hook wiring, file checkpointing in
the dispatcher, plugin manifest packaging. Tracked in claude-sdk.md §15.
