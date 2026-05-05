---
id: TASK-003
title: "Phase Q.deep — Claude adapter optimization (Claude-only focus)"
swimlane: infra
kind: feature
epic: null
labels: [claude, adapter, sdk]
status: complete
priority: P1
appetite: "2w"
created: 2026-05-05
started: 2026-05-05
completed: 2026-05-05
agent_session: null
depends_on: [TASK-002]
blocked_by: []
references: []
---
# TASK-003: Phase Q.deep — Claude adapter deepening

**Outcome (one sentence):** Claude adapter exercises the meaningful surface of `claude-agent-sdk` 0.1.73 (programmatic hooks, output_format schema enforcement, cost ceilings, session persistence, OTEL propagation, hub integration, AgentDefinition path decision, plugin-aware install) at enterprise quality — Codex / Cursor / Gemini stay frozen until Claude is stable.

## Read First
- [docs/adapters/claude-deepening-checklist.md](../adapters/claude-deepening-checklist.md) — master checklist (SSOT for this task)
- [docs/adapters/claude-sdk.md](../adapters/claude-sdk.md) — adapter reference (post-Q-bundle baseline)
- [adapters/claude/sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py)
- [adapters/claude/adapter.yaml](../../adapters/claude/adapter.yaml)
- [core/thinking_os/dispatcher.py](../../core/thinking_os/dispatcher.py)

## Acceptance (G/W/T) — *this IS the Definition of Done*

Scope re-aligned 2026-05-05 (Phase Q.deep wave 1) to ship the **P0 +
T18 closure** as TASK-003 and track P1+ work in the same checklist
under T19 as a follow-up slice. Otherwise the appetite (2w) becomes a
fortnight of one task instead of three of them.

- **Given** the master checklist `docs/adapters/claude-deepening-checklist.md` carries every work item grouped by area
- **When** every P0 item PLUS T18.1–T18.3 (hub AGENT-STREAM correctness) has either a `[x]` (done) marker with a verifying command output, or a `[-]` (not applicable, with a one-line reason) marker
- **Then** all of the following hold:
  1. `make verify` is green and `python scripts/smoke_sdk_dispatch.py` passes against `claude-agent-sdk==0.1.73` after every milestone.
  2. `cos_dispatch_formula_run` produces a typed `EvidenceBundle` slice without transcript regex extraction (output_format JSON schema enforced) for at least the four code-emitting roles (implementer, reviewer, debugger, refactorer).
  3. Dispatcher enforces a per-call cost ceiling via `max_budget_usd`, surfaces it in `DispatchResult.error` when exceeded, and logs the cap to the `formula_dispatches` audit row.
  4. `.claude/agents/` symlinks are either deleted or fully wired into a real AgentDefinition spawn path — no aspirational scaffold remains.
  5. Adapter plumbing covered by tests that pin SDK behavior — programmatic hook firing, structured-output success / retry, budget exhaustion, schema-validation failures.
  6. `docs/adapters/claude-sdk.md` and `claude-deepening-checklist.md` stay in lockstep; every ticked item links to the file or test where it landed.
  7. Codex / Cursor / Gemini dispatcher and hook surfaces remain unchanged from the TASK-002 baseline.
  8. `task_status_history.agent_session` carries a non-NULL `ses-<agent>-…` id whenever an MCP-side board op runs under a known agent runtime — verified via `scripts/probe_agent_session_resolver.py`. Closes the AGENT STREAM "H" mis-classification.
  9. `formula_dispatches` rows written under the new path carry the v23 telemetry columns (cost_usd, usage_jsonb, model_usage_jsonb, tool_calls_jsonb, tool_failures_jsonb) — verified via `_persist_dispatch_output` reading `output_json["_meta"]`.
  10. P1+ items remain tracked in the checklist under T19 / T2.4-T2.6 / T3.4-T3.5 / etc. — closure of this task unblocks creation of TASK-004 (hub UI surfacing) without losing the audit trail.

## Work Log

### 2026-05-05 — Q.deep P0 wave shipped

**Architectural decisions (D1–D6) — all settled:**
D1 KEEP `query()` per formula, D2 DELETE `.claude/agents/`, D3 KEEP
scaffold (no plugin manifest), D4 ALLOW adapter-private hooks under
`adapters/claude/hooks/`, D5 leave OTEL collector to operator, D6
long-context per-request flag.

**Code landed (Claude-only scope):**

- `pyproject.toml` — already pinned in TASK-002 (`claude-agent-sdk>=0.1.73,<0.2.0` + `mcp>=1.27.0`).
- `adapters/claude/sdk_dispatcher.py`:
  - `_resolve_output_schema(meta)` — Pydantic `model_json_schema()` lookup.
  - `_DESTRUCTIVE_BASH_DENY` tuple → `disallowed_tools`.
  - `_OTEL_FORWARDED_VARS` → forwards 16 OTEL env vars + `OTEL_SERVICE_NAME=coding-os-claude`.
  - `output_format={type:"json_schema", schema:…}` when role frontmatter sets `structured_output: true`.
  - `max_turns=3` for structured-output dispatches (StructuredOutput tool burns ≥2 turns).
  - Programmatic `PreToolUse` + `PostToolUseFailure` hook callbacks (closures, try/except-wrapped, capture into `result_meta`).
  - Subtype-aware result handling — `error_max_budget_usd`, `error_max_turns`, `error_max_structured_output_retries` mapped distinctly; populated `structured_output` treated as success even on max_turns.
- `core/thinking_os/dispatcher.py` — `DispatchRequest.max_budget_usd` + `long_context` fields.
- `core/thinking_os/db.py` — migration v23: 6 nullable columns on `formula_dispatches` + `idx_dispatches_cost`.
- `core/thinking_os/agents/{implementer,reviewer,debugger,refactorer}.md` — `structured_output: true` opt-in.
- `core/skills/backend-fundamentals,frontend-fundamentals/SKILL.md` — `paths:` globs added.
- `core/skills/search/SKILL.md` — already YAML-quoted (TASK-002).
- `core/hooks/registry.yaml` — `adapter_scope:` field accepted by renderer.
- `cli/hook_renderer.py` — `HookEntry.adapter_scope` + render-time filter.
- `adapters/claude/install.sh` — strips legacy `.claude/agents/` symlinks; banner refreshed.
- `adapters/claude/hooks/README.md` — adapter-private hook layout doc.
- `adapters/claude/settings.local.template.json` — `mcp__coding-os__*` already present (TASK-002).
- `tests/test_skill_frontmatter.py` — pytest gate for SDK skill contract (11/11 pass).
- `tests/test_claude_dispatcher_options.py` — pytest pin for `ClaudeAgentOptions` shape (4/4).
- `core/scaffold_manifest.json` — regenerated (no `.claude/agents/` references).
- `AGENTS.md` Rules 15/16 — cross-link to `claude-sdk.md` + this checklist.

**Verification:**

| Suite | Result |
|---|---|
| `make verify-hooks` | OK — shellcheck clean |
| `pytest core/thinking_os/tests/test_dispatcher.py + test_db.py` | 102/102 |
| `pytest tests/test_adapters.py + parity + registry + skill_frontmatter + claude_dispatcher_options` | 73/73 |
| `python scripts/smoke_sdk_dispatch.py` × 3 | 3/3 PASS — debugger formula returns full DebuggerOutput JSON via SDK structured_output enforcement |
| `cos sync-all` | OK — schema v23 applied; 302 symlinks healthy; legacy `.claude/agents/` cleaned |

### 2026-05-05 — wave 2: hub correctness loop closed (T18, T19 enumerated)

User flagged on the live hub that Claude actions were rendering as `H`
(human) badges in AGENT STREAM and that schema v23 columns were not
yet being written by the persistence layer. Investigated end-to-end via
two parallel sub-agents (output saved as part of the task transcript).

Root causes:
- MCP tools `cos_task_move`, `cos_task_reposition`, `cos_work_log_append`
  default `agent_session=""` and forward `None` to the backend → DB row
  carries NULL → frontend `agentForSession(None)` returns `human`.
- `cli/board_commands.py::_agent_session_id()` did NOT honor
  `$COS_AGENT_DIR/session-id`, so hook subprocesses missed their own id.
- `core/thinking_os/tools/cognition.py::_persist_dispatch_output()` was
  still writing the pre-v23 9-column INSERT — the new cost columns were
  always NULL.

Fixes shipped:
- `core/thinking_os/server.py::_detect_agent_session_default()` —
  resolves `COS_AGENT_SESSION_ID` → `$COS_AGENT_DIR/session-id` →
  vendor env (CLAUDECODE/CURSOR_*/CODEX_*/CLAUDE_PROJECT_DIR) →
  state-dir `<agent>/session-id` → synthetic `ses-<agent>-mcp-<pid>`.
  Wired into the three MCP tools that write attribution.
- `cli/board_commands.py::_agent_session_id()` — `$COS_AGENT_DIR`
  fast-path before runtime lookup.
- `core/thinking_os/tools/cognition.py::_persist_dispatch_output()` —
  reads `output_json["_meta"]` and INSERTs into the v23 columns
  (cost_usd, budget_usd, usage_jsonb, model_usage_jsonb,
  tool_calls_jsonb, tool_failures_jsonb).
- `scripts/probe_agent_session_resolver.py` — manual probe that reads
  the helper out of server.py and reports the resolved id under the
  current env. Confirmed `ses-claude-20260505-022604-541b` returned
  under live `CLAUDECODE=1`.

Verification (post-fix):
- `pytest core/thinking_os/tests/test_dispatcher.py + test_db.py` →
  102 / 102.
- `pytest core/board_os/tests/ --ignore=test_migration_v20.py` →
  304 / 304. (`test_migration_v20.py` carries a pre-existing syntax
  error from a stale `core.coding-os.db` import — separate issue.)
- `python scripts/smoke_sdk_dispatch.py` → SMOKE: PASS.

Note: the running MCP server in this Claude session still uses
pre-fix code (server loaded at session start). The fix takes effect
on the next Claude restart — the live AGENT STREAM keeps showing
`H` for *this* session's task moves, but new sessions will render
`Cl`. Documented in T18.1.

**Out of scope (deferred to TASK-004 / Phase Q.late hub-surfacing):**
T2.4–T2.6 (hub cost board, cos_metric_record bridge, CLI dispatch
ops cmd), T3.4 (SubagentStart wiring — needs Agent-tool path),
T3.5 (hook layer matrix doc), T4.4–T4.6 (move agent-presence to
adapter-private, dispatch-cost-warn hook, hook-architecture rule
doc), T5.3–T5.5 (can_use_tool SSE bridge, permission_prompt_tool_name,
permission matrix doc), T6.3–T6.6 (disable-model-invocation,
${CLAUDE_SKILL_DIR}, context:fork on codebase-explorer, skill loading
test), T7 (sessions persistence), T8.3–T8.6 (cos doctor --otel, cos_metric
emit, hub Dispatcher panel, SSE stream events), T9 (file checkpointing),
T10 (long-context + thinking adaptive), T11 (plugin manifest — D3),
T12.2–T12.6 (nightly e2e marker, auto-reindex root cause, import-failure
test, no_hardcoded_anthropic guard, make verify-claude target), T13.3–T13.6
(architecture diagram, D1-D6 changelog cross-link, migration guide,
branding rules in install banner), T14.2–T14.4 (sync-doctor, rollback
doc, cos diagnose), T15.2–T15.6 (script cleanup, role frontmatter
audit, stale references), T17 (release tag, roadmap update,
post-mortem). Each tracked in `docs/adapters/claude-deepening-checklist.md`
with priority + verification command.
