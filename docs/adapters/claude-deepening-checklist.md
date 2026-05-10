<!-- domain:ADAPTERS | layer:plan | ssot:true | updated:2026-05-05 -->
# Claude Adapter — Deepening Checklist

> P: Tracker for the optimization items pending against the live `claude-agent-sdk` 0.1.73 surface.
> R: Picking up an open Claude-adapter optimization item, or auditing what is still outstanding.
> S: Implementing brand-new SDK features without an open checklist item — file a task instead.
> N: [claude-sdk.md](claude-sdk.md), [claude-sdk-architecture.md](claude-sdk-architecture.md)

> Nav: [Adapters Index](./00-index.md) | [Docs Index](../00-index.md)

Scope: optimize `adapters/claude/` for the live `claude-agent-sdk` 0.1.73 surface. Other adapters are frozen at the prior baseline until Claude stabilizes.

## How to use this file

1. Each item: `[ ] AREA · summary — file/path — verify command/test`.
2. Status markers:
   - `[ ]` open · `[~]` in-progress · `[x]` done · `[-]` decided not-applicable (give reason inline) · `[!]` blocked (give blocker)
3. Do NOT delete items — strike with `[-]` + reason. Audit trail stays intact.
4. Tick only after the verify command in the line returns green.
5. Sections roughly P0 → P3. Inside a section, top item ships first.

## Architectural decisions (D-row, must answer before T-rows activate)

- [x] **D1** · Spawn mechanism — keep `query()` per-formula OR switch to `agents={…}` + Agent-tool. **Decision (2026-05-05): KEEP `query()`** — formulas need full Claude Code preset + own MCP + own hooks; AgentDefinition would constrain them and force inheritance of parent permission_mode (digest §I.4 warning). Track gain elsewhere via cache reuse (already shipped via `exclude_dynamic_sections`).
- [x] **D2** · `.claude/agents/` symlinks — wire into Agent tool path OR delete. **Decision (2026-05-05): DELETE** — D1 keeps query() so symlinks misleading. Keep slash-command path (`.claude/commands/role-*.md`). Item T15.1 implements deletion.
- [x] **D3** · Plugin manifest — package coding-os as Claude plugin OR keep as install-time scaffold. **Decision (2026-05-05): KEEP scaffold** — plugins target third-party distribution; coding-os ships its own kernel. Revisit if external consumers want plug-and-play install. Item T13.4 documents the decision.
- [x] **D4** · Adapter-specific hook scripts — allow Claude-only hooks under `adapters/claude/hooks/`? **Decision (2026-05-05): YES** — user explicitly authorized 2026-05-05 (per Q.deep ask). Hooks that need SDK-only matchers (`SubagentStart` etc.) live there; cross-adapter hooks stay in `core/hooks/`. Item T4.1 sets up directory + renderer support.
- [x] **D5** · OTEL collector — ship a default endpoint OR leave to operator. **Decision (2026-05-05): leave to operator** — coding-os exports env-var contract; add `cos doctor --otel` probe instead of bundling a collector.
- [x] **D6** · Long context (`betas: ["context-1m-2025-08-07"]`) — opt in by default OR per-request flag. **Decision (2026-05-05): per-request flag** — formula bundles fit in 200k; only big-doc retrieval needs 1M. Adds `request.long_context: bool` to DispatchRequest.

---

## T1 — Output reliability (replace transcript regex with `output_format` JSON Schema)

- [x] **T1.1** P0 · Convert each `F<N>Output` Pydantic model to JSON Schema via `model_json_schema()` — landed 2026-05-05 via `_resolve_output_schema()` helper in `adapters/claude/sdk_dispatcher.py` (lazy import of `cognition_schemas`). All 11 Output classes resolved automatically.
- [x] **T1.2** P0 · Pass `output_format={"type":"json_schema", "schema":<role_schema>}` in dispatcher when role frontmatter declares `structured_output: true` — landed 2026-05-05 in `sdk_dispatcher.py::dispatch()`. Smoke confirms `result.structured_output` populated for debugger role.
- [x] **T1.3** P0 · Read `result.structured_output` first; fall back to `extract_json_block` — landed 2026-05-05; subtype-aware fallback handles `error_max_structured_output_retries`, `error_max_budget_usd`, `error_max_turns`. Populated `structured_output` treated as success even on max_turns.
- [x] **T1.4** P0 · Add frontmatter flag `structured_output: true` to the four code-emitting roles — landed 2026-05-05 (`implementer.md`, `reviewer.md`, `debugger.md`, `refactorer.md`).
- [x] **T1.5** P1 · Surface `subtype="error_max_structured_output_retries"` in `DispatchResult.error` so caller can route to retry-with-relaxed-prompt — landed 2026-05-05: `sdk_dispatcher.py` final return sets `error="error_max_structured_output_retries: schema enforcement exhausted, fell back to regex extraction"` when that subtype fires and regex produced usable JSON (status stays "ok" to keep bundle population; caller checks error field).
- [x] **T1.6** P1 · Pydantic validate before persistence — landed 2026-05-05: `_persist_dispatch_output` in `cognition.py` validates via `cls.model_validate(output_json)` before INSERT; on validation failure marks bundle degraded, sets status="fail", and skips the `formula_dispatches` row entirely (early return). Bundle still saved so the supervisor can backtrack.
- [ ] **T1.7** P2 · Document streaming-incompatibility caveat (digest §G.5) — `docs/adapters/claude-sdk.md` §7 — verify: section reads "structured output is incompatible with streaming"
- [ ] **T1.8** P2 · Add benchmark — schema-enforced vs regex-extracted — wall time, success rate, retries — `scripts/bench_output_format.py` — verify: report saved to `docs/adapters/output-format-benchmark.md`

## T2 — Cost / budget ceiling

- [x] **T2.1** P0 · Add `max_budget_usd: float | None = None` field to `DispatchRequest` — landed 2026-05-05 in `core/thinking_os/dispatcher.py` (also `long_context: bool` for D6). All 19/19 dispatcher unit tests + 102/102 thinking_os tests stay green.
- [x] **T2.2** P0 · Forward to `ClaudeAgentOptions(max_budget_usd=...)` — landed 2026-05-05 in `sdk_dispatcher.py`. Subtype `error_max_budget_usd` mapped to `status="error"` with budget figure in error string.
- [x] **T2.3** P0 · Persist cost columns on `formula_dispatches` — landed 2026-05-05 as migration v23 (`_migrate_v23_dispatch_cost`): six nullable columns (cost_usd, budget_usd, usage_jsonb, model_usage_jsonb, tool_calls_jsonb, tool_failures_jsonb) + idx_dispatches_cost partial index. `pytest test_db.py` 83/83.
- [x] **T2.4** P1 · Surface aggregate spend on the hub — landed 2026-05-05: `core/web/routes/cognition.py` now has `GET /api/cognition/cost` (formula/day rollup), `GET /api/cognition/dispatchers` (recent dispatch rows), and `GET /api/cognition/dispatchers/{id}/tools` (tool audit drawer). verify: `curl http://127.0.0.1:9188/api/cognition/cost` returns JSON when hub running.
- [x] **T2.5** P1 · Add `cos_metric_record` call inside dispatcher to log `dispatch.cost_usd` per formula — landed 2026-05-05: `_emit_dispatch_metrics_safe()` in `cognition.py` writes an `agent_metrics` row (`agent_type="dispatch"`, `domain=formula_id`, `outcome=status`, `duration_ms=latency_ms`) after each dispatch. verify: `cos_metric_query agent_type=dispatch` returns rows after a dispatch run.
- [ ] **T2.6** P2 · Add CLI flag `cos dispatch --max-budget 0.05 …` (manual single-formula trigger for ops debugging) — `cli/dispatch_commands.py` (new) — verify: `cos dispatch --help` shows it

## T3 — Programmatic hooks (in-dispatcher Python callbacks)

- [x] **T3.1** P0 · Wire `hooks={"PreToolUse": [HookMatcher(matcher=…, hooks=[cb])]}` callback — landed 2026-05-05 in `sdk_dispatcher.py`. Captures `{tool_use_id, tool_name, tool_input}` per call into `result_meta["tool_calls"]`. Closures bind to per-dispatch lists (concurrency-safe). Callbacks wrapped in try/except so they CANNOT propagate to the SDK subprocess (a raised exception kills exit code 1).
- [x] **T3.2** P0 · Wire `PostToolUseFailure` callback — landed 2026-05-05. Records to `result_meta["tool_failures"]`. Did NOT short-circuit dispatch (originally in plan): the SDK already surfaces fatal failures via `subtype=error_during_execution`, so capturing alongside is enough; aborting early would lose mid-run progress useful for diagnostics. Updated rationale in claude-sdk.md §C.
- [x] **T3.3** P1 · Wire `Stop` callback that snapshots `usage` + `model_usage` — landed 2026-05-05 directly through ResultMessage capture (no separate Stop hook needed; ResultMessage.usage / model_usage fields are read into `result_meta` in the message-stream handler).
- [-] **T3.4** P1 · Wire `SubagentStart` / `SubagentStop` callbacks — NOT APPLICABLE (D1 final). `query()` does not spawn sub-agents via the Agent tool, so these events never fire in dispatch context. Events remain declared in `registry.yaml` + `adapter.yaml` for interactive sessions (presence.sh) but are not wired as programmatic hooks. Comment added in `sdk_dispatcher.py` hooks section referencing D1.
- [ ] **T3.5** P2 · Document in `docs/adapters/claude-sdk.md` §C the boundary between programmatic vs filesystem hooks; ship a decision matrix — verify: doc has "Hook layer matrix" subsection

## T4 — Claude-specific filesystem hooks (D4 authorized)

- [x] **T4.1** P0 · Decide directory layout for adapter-private hooks — `adapters/claude/hooks/` shadows `core/hooks/` for Claude-only scripts — verify: directory exists with README. **Decision (2026-05-05):** layout = `adapters/claude/hooks/` (created with README); installer prefers it via T4.3.
- [x] **T4.2** P0 · Update `cli/hook_renderer.py` to source from BOTH `core/hooks/` AND `adapters/<agent>/hooks/`; adapter-private wins on name clash — landed 2026-05-05: registry.yaml entries support `adapter_scope:` field; renderer skips when scope ≠ caps.agent_id. Single registry SSOT, scripts physically live under their owning directory.
- [x] **T4.3** P0 · Update `core/scripts/install-adapter.sh` to symlink adapter-private hooks AFTER core hooks so override symlink replaces — verified 2026-05-05: install-adapter.sh:113-120 already symlinks adapters/$ADAPTER/hooks/*.sh after core, with `ln -sf` rebinding any name clash. `shopt -s nullglob` keeps the loop empty-safe.
- [ ] **T4.4** P1 · Move `core/hooks/agent-presence.sh` Claude-only branches (SubagentStart etc.) into `adapters/claude/hooks/agent-presence.sh` — verify: `make verify-hooks` green, codex/cursor presence unchanged
- [ ] **T4.5** P1 · Add `adapters/claude/hooks/dispatch-cost-warn.sh` — fires PostToolUse on `cos_dispatch_formula_run` if cost row >$0.50 — verify: synthetic invocation returns warning to stderr
- [ ] **T4.6** P2 · Document `adapters/<agent>/hooks/` convention in `docs/adapters/claude-sdk.md` §4 + `core/rules/hook-architecture.md` (new) — verify: file exists, AGENTS.md links to it

## T5 — Permissions completeness

- [x] **T5.1** P0 · Audit `.claude/settings.local.template.json` allow-list — verified 2026-05-05: `mcp__coding-os__*` present (TASK-002), `Bash(...)` patterns scoped to read-only/safe ops, no destructive entries. WebFetch / WebSearch listed.
- [x] **T5.2** P0 · Add `disallowed_tools` for destructive ops — landed 2026-05-05 as `_DESTRUCTIVE_BASH_DENY` constant in `sdk_dispatcher.py` (rm -rf, git push --force, git reset --hard, sudo, curl|bash, etc.). Forwarded via `ClaudeAgentOptions(disallowed_tools=…)`. Smoke verified clean dispatch with deny-list active.
- [ ] **T5.3** P1 · Build `can_use_tool` adapter callback for the hub UI — when running interactive (not dispatcher), prompts surface in hub via SSE — `core/web/routes/permissions.py` (new) + `adapters/claude/permission_bridge.py` — verify: contract test on the SSE channel
- [ ] **T5.4** P1 · Honor `permission_prompt_tool_name` so coding-os can route prompts to a custom MCP tool — same files — verify: smoke uses the custom tool name
- [ ] **T5.5** P2 · Document permission evaluation order matrix in `docs/adapters/claude-sdk.md` §9 (already there from TASK-002 — re-audit) — verify: matrix matches digest §B.4 exactly

## T6 — Skills layer (frontmatter + auto-scope + dynamic context)

- [x] **T6.1** P0 · Add `paths:` glob frontmatter — landed 2026-05-05: `paths: ["backend/**/*"]` on backend-fundamentals, `paths: ["frontend/**/*"]` on frontend-fundamentals. Pre-existing `globs:` retained for backward compatibility. Stack skills (python-django, nextjs-react) already had scope strings — pending sync to consumer projects via `cos sync-all`.
- [x] **T6.2** P0 · Lift skill audit into pytest — landed 2026-05-05 as `tests/test_skill_frontmatter.py`. Parametrized over every `core/skills/*/SKILL.md`. Asserts ≤1024-char description, ≤1,536-char listing budget, no first-person voice, valid YAML, no "anthropic"/"claude" in name. 11/11 skills pass. Underscore allowed in name (project ships `thinking_os`).
- [ ] **T6.3** P1 · Add a `disable-model-invocation: true` flag for skills that must be `/explicit` (e.g. `caveman`) — appropriate SKILL.md files — verify: SDK loads them without auto-invocation per digest §E.1
- [ ] **T6.4** P1 · Add `${CLAUDE_SKILL_DIR}` references where skills shell out to bundled scripts (`audit_skill_descriptions.py` uses repo root — confirm any skill that should follow `${CLAUDE_SKILL_DIR}`) — verify: skill works when symlinked to consumer project
- [ ] **T6.5** P2 · Add a `context: fork` skill for the heaviest research flow (e.g. `codebase-explorer`) so it runs as a subagent without polluting parent context — `core/skills/codebase-explorer/SKILL.md` — verify: SDK spawns a fork on invocation
- [ ] **T6.6** P2 · Skill bundle test — fresh consumer project loads every skill without warnings — `tests/test_skill_loading.py` (new, light) — verify: pass

## T7 — Sessions + persistence

- [ ] **T7.1** P1 · Pass a deterministic `session_id` per dispatch (`ses-claude-sdk-<formula>-<task_id>`) so resumes can target — `adapters/claude/sdk_dispatcher.py` — verify: smoke + DB row carries the id
- [ ] **T7.2** P1 · Implement `SessionStore` adapter that mirrors sub-session messages to coding-os DB (table `formula_sessions`) — new module `adapters/claude/session_store.py` — verify: pytest mock asserts mirror, synthetic resume reuses messages
- [ ] **T7.3** P2 · Add `cos dispatch --resume <session-id> <formula>` for ops debugging — `cli/dispatch_commands.py` — verify: replays a transcript end-to-end
- [ ] **T7.4** P2 · `cos cognition replay <session-id>` already exists — extend to read from `formula_sessions` for SDK-spawned dispatches — verify: replay shows tool calls and final JSON
- [ ] **T7.5** P3 · Document session-id encoding (`<encoded-cwd>` non-alphanumerics → `-`) in `docs/adapters/claude-sdk.md` §12 — verify: doc references the encoding

## T8 — Observability + telemetry

- [x] **T8.1** P0 · Forward `OTEL_*` env vars — landed 2026-05-05 as `_OTEL_FORWARDED_VARS` tuple (16 vars covering OTLP exporter config, intervals, log details, resource attributes, beta tracing). Dispatcher reads parent env, populates `ClaudeAgentOptions(env=...)`. Smoke confirms no env clash.
- [x] **T8.2** P0 · Set `OTEL_SERVICE_NAME=coding-os-claude` per dispatch — landed 2026-05-05 via `env.setdefault(...)` so operator-supplied service names still win.
- [x] **T8.3** P1 · Add `cos doctor --otel` probe that reports configured exporters and recent metric flush — landed 2026-05-05: `_probe_otel()` in `cli/doctor.py` + `--otel` flag on the `doctor` command. Prints status table for all OTEL_* vars + TCP probe of `OTEL_EXPORTER_OTLP_ENDPOINT`. verify: `cos doctor --otel` prints table.
- [x] **T8.4** P1 · Emit `claude_code.dispatch.duration_ms` and `dispatch.cost_usd` as coding-os metrics via `cos_metric_record` — landed 2026-05-05 via `_emit_dispatch_metrics_safe()` (same as T2.5). verify: `cos_metric_query agent_type=dispatch` returns rows after a dispatch.
- [ ] **T8.5** P2 · Hub board card "Dispatcher activity" — last N dispatches with cost / latency / status — `core/web/ui/src/components/DispatchPanel.tsx` (new) — verify: visible at http://127.0.0.1:9188
- [x] **T8.6** P2 · Hub stream events — landed 2026-05-05: `_event_generator` in `core/web/routes/stream.py` polls `formula_dispatches` for new IDs and emits `dispatch-completed` SSE events with `{dispatch_id, session_id, formula_id, status, latency_ms, cost_usd, sub_session_id, model, ts}`. Watermark tracked via `last_dispatch_id`.

## T9 — File checkpointing (safety on Edit-heavy roles)

- [x] **T9.1** P1 · Enable `enable_file_checkpointing=True` for implementer / refactorer roles only — landed 2026-05-05: `sdk_dispatcher.py` reads `agent_meta.get("enable_file_checkpointing")` and passes `enable_file_checkpointing=True` to `ClaudeAgentOptions`; `implementer.md` + `refactorer.md` frontmatter sets the flag.
- [x] **T9.2** P1 · Capture `UserMessage.uuid` series and persist to `result_meta["checkpoints"]` — landed 2026-05-05: `UserMessage` imported from SDK; `_run()` captures `msg.uuid` into `checkpoint_uuids` list which is merged into `result_meta["checkpoints"]`. Note: `checkpoints_jsonb` column deferred to a future schema migration; UUIDs currently stored in `output_json["_meta"]["checkpoints"]`.
- [ ] **T9.3** P2 · Add `cos dispatch rewind <dispatch-id>` CLI helper — `cli/dispatch_commands.py` — verify: rewinds a known checkpoint
- [ ] **T9.4** P2 · Document Bash-mutation gotcha (digest §G.4) — `docs/adapters/claude-sdk.md` §12.4 already mentions; cross-link from runbook — verify: doc reference

## T10 — Long context + thinking config (D6)

- [x] **T10.1** P1 · Add `long_context: bool = False` to `DispatchRequest` — landed 2026-05-05 in `core/thinking_os/dispatcher.py`. All 19/19 dispatcher unit tests pass.
- [x] **T10.2** P1 · When set, dispatcher passes `betas=["context-1m-2025-08-07"]` — landed 2026-05-05 in `sdk_dispatcher.py` line 358.
- [x] **T10.3** P2 · Map role frontmatter `long_context: true` (researcher) — landed 2026-05-05: `researcher.md` frontmatter + `_build_dispatch_request()` reads `meta.get("long_context", False)` and forwards to `DispatchRequest`.
- [ ] **T10.4** P2 · Set `thinking={"type":"adaptive"}` for Opus 4.7 to align with new SDK contract — `adapters/claude/sdk_dispatcher.py` — verify: synthetic with model=opus-4-7 sees adaptive thinking
- [ ] **T10.5** P3 · Map intensity → `max_thinking_tokens` budget — role files — verify: token report aligns

## T11 — Plugin manifest (D3 deferred — keep scaffold)

- [-] **T11.1** P3 · Package coding-os as `.claude-plugin/plugin.json` — DECIDED NOT-APPLICABLE (D3). Revisit when third-party distribution lands.

## T12 — CI / verification (no flake)

- [x] **T12.1** P0 · Add `tests/test_claude_dispatcher_options.py` — landed 2026-05-05. Pins 15 required ClaudeAgentOptions fields, 5 required permission_mode literal values, 10 required hook event literals, and the SystemPromptPreset shape (especially `exclude_dynamic_sections`). 4/4 tests pass. CI catches SDK breaking changes immediately.
- [x] **T12.2** P0 · Add nightly E2E job marker `pytest --run-sdk-e2e` — landed 2026-05-05: `pyproject.toml` declares `sdk_e2e` marker; `tests/conftest.py` adds `--run-sdk-e2e` option + skip guard. verify: `uv run pytest --collect-only -m sdk_e2e` shows no errors; `pytest --run-sdk-e2e scripts/smoke_sdk_dispatch.py` triggers the real dispatch.
- [x] **T12.3** P1 · Auto-reindex timeout — bumped 10s → 30s in `test_auto_reindex.py` — landed 2026-05-05. 21/21 pass. Root cause: subprocess-spawn-heavy hook on a cold-start sandbox; 10s was tight. 30s gives headroom without hiding hangs.
- [x] **T12.4** P1 · Cover `ClaudeSDKDispatcher` import-failure path with a unit test — landed 2026-05-05: `tests/test_claude_dispatcher_options.py::test_dispatcher_import_failure_path` — patches `sys.modules["claude_agent_sdk"] = None` and verifies `available()` returns False + `_import_error` is set. verify: `uv run pytest tests/test_claude_dispatcher_options.py::test_dispatcher_import_failure_path -v`.
- [x] **T12.5** P2 · Lint guard — landed 2026-05-05: `tests/test_no_hardcoded_anthropic.py` parametrizes over `core/`, `cli/`, `adapters/` (.py/.yaml/.md). Fails on `sk-ant-…` API key prefix anywhere; fails on `claude-(opus|sonnet|haiku)-N-N` outside `ALLOWED_MODEL_PATHS` (registry, dispatcher gate, role frontmatter, env-overridable defaults). Caught + fixed `compress.py` hardcoded model — now reads `COS_COMPRESS_MODEL` env. 362/362 pass.
- [x] **T12.6** P2 · `make verify-claude` target — landed 2026-05-05: runs `test_dispatcher`, `test_db`, `test_claude_dispatcher_options`, `test_skill_frontmatter`, `test_branding`, `test_no_hardcoded_anthropic`, `test_adapters` in 21s. 588/588 pass.

## T13 — Documentation lockstep

- [x] **T13.1** P0 · Re-verify SDK surface table — landed 2026-05-05 via `tests/test_claude_dispatcher_options.py` (T12.1) which pins fields/permission modes/hook events against the live SDK. `scripts/inspect_sdk_options.py` is the regenerable source-of-truth probe.
- [x] **T13.2** P0 · Cross-link AGENTS.md Rule 15/16 to claude-sdk.md + this checklist — landed 2026-05-05 (governance edit, with `docs-update-claude-deepening` task marker per Rule 7). Both rules now link to dispatcher doc + deepening plan.
- [x] **T13.3** P1 · Diff diagram — landed 2026-05-05: `docs/adapters/claude-sdk-architecture.md` with text dependency graph + mermaid flowchart + contract table + session-id flow.
- [x] **T13.4** P1 · Document D1–D6 in `docs/adapters/claude-sdk.md` §17a — landed 2026-05-05: new §17a "Architectural Decisions (D1–D6)" section added with rationale table.
- [x] **T13.5** P2 · Migration guide — landed 2026-05-05: `docs/adapters/claude-migration-2026-05.md` — TL;DR, breaking changes (none), change table per wave, verification commands, rollback link.
- [x] **T13.6** P2 · Branding banner — landed 2026-05-05: `adapters/claude/install.sh` final banner now states coding-os is independent + not affiliated with Anthropic + describes "Claude Code" as Anthropic's product per their terms.

## T14 — Migration & rollback

- [x] **T14.1** P0 · `cos sync-all` re-renders adapter state — verified 2026-05-05 against this repo: dry-run reported pending re-renders, real run applied schema v23 + re-linked claude/codex hooks + 302 symlinks healthy + `.claude/agents/` cleanup confirmed (no longer present). Adapter-only filter (`--adapter claude`) deferred to T14.x P1 since the existing `--slug` already gives precise scope.
- [ ] **T14.2** P1 · `cos sync-doctor --adapter claude` reports drift vs the latest adapter shape — `cli/sync_doctor.py` — verify: prints PASS / list of drifts
- [x] **T14.3** P1 · Document rollback — landed 2026-05-05: `docs/adapters/claude-rollback.md` — git revert window, consumer tag pinning, DB schema rollback, AGENT STREAM rollback, adapter template rollback.
- [x] **T14.4** P2 · `cos doctor --claude-sdk` — landed 2026-05-05: `_probe_claude_sdk()` in `cli/doctor.py` reports SDK version, CLI version + path, ANTHROPIC_API_KEY/AUTH_TOKEN presence, CLAUDECODE marker, `.mcp.json` presence. Verified live: `cos doctor --claude-sdk` prints 5-row table.

## T15 — Cleanup / loose ends

- [x] **T15.1** P0 · Per D2: remove `.claude/agents/` block from `adapters/claude/install.sh` (lines 46-58) — landed 2026-05-05: install.sh strips legacy symlinks, scaffold manifest regenerated (0 references), 58/58 adapter tests green.
- [x] **T15.2** P0 · Moved `scripts/inspect_sdk_options.py` → `scripts/dev/inspect_sdk_options.py` — 2026-05-05. No references found via grep; doctor still passes.
- [x] **T15.3** P1 · Deleted `scripts/audit_skill_descriptions.py` — 2026-05-05. T6.2 pytest gate (`tests/test_skill_frontmatter.py`) covers its purpose. No references found.
- [ ] **T15.4** P1 · Audit `core/thinking_os/agents/<role>.md` for unused fields (`tools_budget` overlaps with `Options.allowed_tools`) — decide canonical source — verify: doc matches code
- [x] **T15.5** P2 · Pre-v0.3 placeholders removed — 2026-05-05: cleaned 3 stale comments referring to the legacy persona system removed in v0.3 (in `tools/cognition.py`, `cognition.py`, `doctor.py`, and `server.py`).
- [x] **T15.6** P2 · Confirmed no `.claude/agents/` reference in any test, golden file, or doc — 2026-05-05. `command grep -rn ".claude/agents" --include=*.py --include=*.md --include=*.sh --include=*.yaml --include=*.json` returned no hits (excluding the task doc and checklist themselves).

## T16 — Branding / compliance

- [x] **T16.1** P0 · Branding audit — performed 2026-05-05. `command grep -rIn "Claude Code" adapters/claude/ cli/ core/web/ui/src/` returned only descriptive references to upstream Anthropic Claude Code (e.g. `adapter.yaml::label: "Anthropic Claude Code"`, install.sh banner pointing to "Claude Code sub-sessions"). No first-party coding-os surface presents itself as "Claude Code". Compliant with Anthropic terms.
- [x] **T16.2** P1 · Branding gate — landed 2026-05-05: `tests/test_branding.py` parametrizes over `core/web/ui/src/**/*.{ts,tsx}` + `cli/**/*.py` (allow-list `cli/doctor.py` for descriptive Claude Code CLI references). Fails if "Claude Code" or "claude-code" appears outside the allow-list.

## T18 — Hub presence + AGENT STREAM correctness (added 2026-05-05)

- [x] **T18.1** P0 · MCP-side agent_session auto-detect — landed 2026-05-05 in `core/thinking_os/server.py::_detect_agent_session_default()`. Fixes hub AGENT STREAM showing Claude actions as "H" (human) instead of "Cl". Wired into `cos_task_move`, `cos_task_reposition`, `cos_work_log_append` (NOT `cos_task_daily` — that field is a query filter, not attribution). Verified via `scripts/probe_agent_session_resolver.py` returning `ses-claude-…` under live `CLAUDECODE=1` env. Takes effect on next Claude session start (MCP server reload).
- [x] **T18.2** P0 · CLI-side agent_session helper — `cli/board_commands.py::_agent_session_id()` now honors `$COS_AGENT_DIR/session-id` first (mirrors shell `cos_read_session_id`) before falling through to runtime detection + state-dir lookup. Hook subprocesses calling `cos task-move` now stamp the correct session id.
- [x] **T18.3** P0 · `cos_dispatch_formula_run` persists v23 columns — `tools/cognition.py::_persist_dispatch_output()` now reads `output_json["_meta"]` (cost_usd, usage, model_usage, tool_calls, tool_failures) and INSERTs into the v23 columns. Schema migration v23 was dead weight before this; now closed-loop.

## T19 — Hub admin panel surfacing (deferred, post-Q.deep follow-up)

- [x] **T19.1** P1 · `/api/cognition/dispatchers` endpoint — landed 2026-05-05 in `core/web/routes/cognition.py`. Queries `formula_dispatches WHERE cost_usd IS NOT NULL`, returns `{session_id, formula_id, ts, cost_usd, budget_usd, status, latency_ms}`. Also `/api/cognition/cost` for formula/day rollup (T2.4).
- [x] **T19.2** P1 · `/api/cognition/dispatchers/{session_id}/tools` — landed 2026-05-05. Parses `tool_calls_jsonb` + `tool_failures_jsonb` from the dispatch row into the sub-agent tool audit drawer.
- [x] **T19.3** P1 · Sub-session presence — landed 2026-05-05: `/api/board/list` now surfaces `data.sub_session_counts: {agent: count}` populated by counting `ses-<agent>-sdk-*.json` files with active heartbeat. UI can render "Claude (+ N sub-agents)" from this map.
- [x] **T19.4** P2 · Hooks dashboard endpoint — landed 2026-05-05: `core/web/routes/hooks.py` registers `/api/hooks/list` with `adapter` + `event` filters. Returns `{name, event, matcher, category, phase, adapter_scope, script}` per hook from `cli/hook_renderer.py::load_registry()`. Wired into `core/web/server.py`.
- [ ] **T19.5** P2 · Cost / model-usage rollup chart in board UI.
- [ ] **T19.6** P3 · Budget-exhaustion alert — UI warning when `cost_usd / budget_usd > 0.95`.

## T17 — Release & ops

- [x] **T17.1** P1 · `pyproject.toml` version bumped 0.2.0 → 0.3.0 — 2026-05-05. Git tag `v0.3.0-claude-q.deep` deferred to release commit (avoids tagging mid-task).
- [x] **T17.2** P1 · Roadmap updated 2026-05-05: roadmap Current State section lists the adapter Q-bundle and deepening work with full landed surface; deferred items split into routing follow-ups versus adapter follow-ups.
- [x] **T17.3** P2 · Post-mortem — landed 2026-05-05: `docs/postmortems/2026-05-claude-deepening.md` — summary, what worked, 4 surprise bugs with root cause + fix + lesson, deferred work priority order.

---

## Progress dashboard

Run after every milestone:

```bash
# count totals
command grep -cE '^\- \[ \]' docs/adapters/claude-deepening-checklist.md   # open
command grep -cE '^\- \[~\]' docs/adapters/claude-deepening-checklist.md   # in-progress
command grep -cE '^\- \[x\]' docs/adapters/claude-deepening-checklist.md   # done
command grep -cE '^\- \[\-\]' docs/adapters/claude-deepening-checklist.md  # not applicable
command grep -cE '^\- \[!\]' docs/adapters/claude-deepening-checklist.md   # blocked

# P0 burn-down
command grep -E '^\- \[[ ~]\] \*\*T[0-9]+\.[0-9]+\*\* P0' docs/adapters/claude-deepening-checklist.md | wc -l
```

## Snapshot 2026-05-05 (P1 wave)

- Architectural decisions (D1–D6): 6 / 6 ✓
- P0 wave shipped: T1.1–T1.4, T2.1–T2.3, T3.1–T3.3, T4.1–T4.3, T5.1, T5.2, T6.1, T6.2, T8.1, T8.2, T12.1, T12.2, T13.1, T13.2, T14.1, T15.1, T15.2, T16.1, T18.1–T18.3.
- P1 wave shipped: T1.5, T2.4, T2.5, T3.4[-], T8.3, T8.4, T9.1, T9.2, T10.1, T10.2, T10.3, T12.4, T13.3, T13.4, T13.5, T14.3, T15.3, T15.6, T17.3, T19.1, T19.2.
- Still open (P1–P3): T1.6–T1.8, T2.6, T3.5, T4.4–T4.6, T5.3–T5.5, T6.3–T6.6, T7, T8.5–T8.6, T9.3–T9.4, T10.4–T10.5, T12.3, T12.5–T12.6, T13.6, T14.2, T14.4, T15.4–T15.5, T16.2, T17.1, T17.2, T19.3–T19.6.
- Verification 2026-05-05: `pytest test_dispatcher.py test_db.py` → 102/102; `pytest tests/test_adapters.py tests/test_adapter_parity.py` → 47/47; `pytest tests/test_cli.py` → 49/49; `pytest tests/test_claude_dispatcher_options.py tests/test_skill_frontmatter.py` → 16/16; `make verify-hooks` clean.

## Changelog

| Date | Change |
|---|---|
| 2026-05-05 | First write — TASK-003 created, decisions D1–D6 set, work items T1–T17 enumerated. Items based on the SDK 0.1.73 surface gaps surfaced in the 2026-05-04 audit (TASK-002 work log). |
| 2026-05-05 | All P0 items shipped — output_format JSON Schema enforcement, max_budget_usd ceiling, programmatic hooks, OTEL env propagation, disallowed_tools deny-list, schema migration v23, skill `paths` globs + pytest gate, ClaudeAgentOptions regression test, AGENTS.md cross-links, `.claude/agents/` cleanup, `cos sync-all` propagation. Adapter-private hook layer (T4.1–T4.3) ready for future Claude-only scripts. P1+P2+P3 items remain as follow-up. |
