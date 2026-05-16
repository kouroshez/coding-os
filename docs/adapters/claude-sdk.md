<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-05-04 -->
# Claude Adapter — Full Reference

> P: Everything `src/adapters/claude/` does for a consumer project — install, hook rendering, MCP wiring, formula-agent dispatch, observability.
> R: Touching `src/adapters/claude/**`, debugging the Claude install, adding/renaming hooks, enabling new SDK features, planning permission or MCP changes for Claude users.
> S: Working on `src/core/`, other adapters, or pure docs.
> N: [claude-sdk-architecture.md](claude-sdk-architecture.md), [claude-deepening-checklist.md](claude-deepening-checklist.md), [claude-migration-2026-05.md](claude-migration-2026-05.md)

> Nav: [Adapters Index](./00-index.md) | [Docs Index](../00-index.md)

> SDK floor: `claude-agent-sdk>=0.1.73,<0.2.0`. CLI floor: `@anthropic-ai/claude-code>=2.1.119` (stable). Renamed 2026-05-04 from "Claude-SDK Dispatcher" to full adapter reference.

## 1. The mRNA layer — what this adapter is

Claude is the **primary** adapter coding-os targets. Codex and Cursor are
secondary; they reuse the same kernel but expose fewer capabilities (Codex
has Bash-only PreToolUse; Cursor has no skills/agents at all). This file
documents the Claude-specific translation of the agent-agnostic kernel.

```
src/core/  ──►  src/adapters/claude/  ──►  consumer project's .claude/
(DNA)        (mRNA — this file)     (phenotype)
```

Three jobs:
1. **Install** — render `.claude/{settings.json,settings.local.json,.mcp.json,agents,skills,commands,rules,hooks}` into a consumer project (via [install.sh](../../src/adapters/claude/install.sh) + [src/core/scripts/install-adapter.sh](../../src/core/scripts/install-adapter.sh)).
2. **Dispatch** — spawn formula-agent sub-sessions via `claude-agent-sdk` ([sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py)).
3. **Declare capabilities** — tell the kernel which `{event, matcher}` pairs Claude's CLI can actually fire ([adapter.yaml](../../src/adapters/claude/adapter.yaml)).

## 2. SDK + tooling versions (audit 2026-05-04)

| Component | Floor | Latest | Notes |
|---|---|---|---|
| `claude-agent-sdk` (PyPI) | `>=0.1.73,<0.2.0` | 0.1.73 (2026-05-04) | Pinned in `pyproject.toml::optional-dependencies.claude-sdk`. |
| `mcp` (PyPI) | `>=1.27.0` | 1.27.0 (2026-04-02) | Used by central FastMCP server. |
| `@anthropic-ai/claude-code` (npm CLI) | 2.1.119 stable | 2.1.128 latest | User-installed; `brew install claude-code` or `npm i -g @anthropic-ai/claude-code`. |
| `@anthropic-ai/claude-agent-sdk` (npm) | n/a (Py only) | 0.2.128 | Reference only — coding-os uses the Py SDK exclusively. |

Verify:

```bash
uv pip show claude-agent-sdk mcp | grep -E "^(Name|Version)"
claude --version          # CLI on PATH
```

## 3. Install flow

`bash src/adapters/claude/install.sh` invoked from a consumer project root:

1. Calls shared installer ([src/core/scripts/install-adapter.sh](../../src/core/scripts/install-adapter.sh)) which:
   - Creates `.claude/{hooks,rules,skills,commands,agents}/` symlinking to `src/core/{hooks,rules,skills,commands,thinking_os/agents}/`.
   - Writes `.claude/cos-env.sh` (sources `COS_AGENT_DIR`, `COS_AGENT`, etc.).
2. Renders `.claude/settings.json` from [settings.template.json](../../src/adapters/claude/settings.template.json) (substituting the `HOOKS_DIR` placeholder).
3. Adds `coding-os` entry to `.mcp.json` via [_install_helpers/update_mcp_json.py](../../src/adapters/claude/_install_helpers/update_mcp_json.py):
   - Prefers `cos server-start` if `cos` is on `PATH`.
   - Falls back to `uv run --directory <CODING_OS_ROOT>/core/thinking_os python server.py`.
4. Symlinks role prompts to `.claude/agents/role-*.md` (SDK reads from this dir for filesystem-fallback `AgentDefinition`).
5. Copies [settings.local.template.json](../../src/adapters/claude/settings.local.template.json) to `.claude/settings.local.json` (only if absent — never overwrites user customizations).

## 4. settings.json (rendered, do not hand-edit)

`src/adapters/claude/settings.template.json` is **derived** from
`src/core/hooks/registry.yaml` via `make regen-adapter-templates`. Hand-edits
are caught by `src/core/hooks/warn-template-drift.sh`.

Hook events declared (post-2026-05-04 hardening):

| Event | Matchers | Why |
|---|---|---|
| `PreToolUse` | `Bash`, `Write\|Edit`, `Write\|Edit\|MultiEdit`, `Skill` | Block secrets, dangerous commands, missing doc anchor, missing memory check, missing skill invocation. |
| `PostToolUse` | `Bash`, `Write\|Edit`, `Write\|Edit\|MultiEdit`, `Skill`, `mcp__coding-os__cos_backtrack_log` | Capture observation, regen doc index, route backtrack-log calls. |
| `PostToolUseFailure` | `""` | (NEW 2026-05-04) keep agent-presence accurate when a tool errors. |
| `Stop` | `""` | Session summary + memory enrichment. |
| `SubagentStart` | `""` | (NEW 2026-05-04) agent-presence ping when sub-session spawns. |
| `SubagentStop` | `""` | (NEW 2026-05-04) agent-presence ping when sub-session exits. |
| `SessionStart` | `startup`, `compact\|resume` | Bootstrap session, decay scan, MCP liveness probe. |
| `UserPromptSubmit` | `""` | Caveman-mode gating, presence ping. |

Events the Py SDK supports but coding-os does NOT yet wire:
`PreCompact`, `Notification`, `PermissionRequest`. These are TS-only or
filesystem-hook-only as of SDK 0.1.73 — leave them off until a need
emerges.

## 5. settings.local.json (user-scoped allow-list)

Template at [settings.local.template.json](../../src/adapters/claude/settings.local.template.json).
Copied **once** during install; never overwritten so user customizations
survive `cos sync-all`.

Critical entry added 2026-05-04:

```json
{ "permissions": { "allow": [ ..., "mcp__coding-os__*" ] } }
```

**Why required:** Claude Agent SDK 0.1.73 evaluates permissions in this
order (digest §B.4): hooks → deny rules → permission_mode → allow rules
→ `can_use_tool`. `acceptEdits` mode auto-approves filesystem ops only —
**MCP tools are NOT auto-approved**. Without the `mcp__coding-os__*`
wildcard, every `cos_*` call would either deny silently (in `dontAsk`)
or prompt the user (in `default`).

## 6. .mcp.json wiring

Generated by [_install_helpers/update_mcp_json.py](../../src/adapters/claude/_install_helpers/update_mcp_json.py)
during install. Loaded by Claude Code only when `setting_sources` includes
`"project"` (default).

The central server lives at [src/core/thinking_os/server.py](../../src/core/thinking_os/server.py)
and exposes ~60 tools under the `cos_*` namespace (categories in
[AGENTS.md](../../AGENTS.md) §Four-Layer Retrieval).

Claude addresses these tools as `mcp__coding-os__cos_<name>` per SDK
docs §D.2.

## 7. Formula-agent dispatcher

[src/adapters/claude/sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py) — the only place
in coding-os that calls `claude_agent_sdk.query()`.

### 7.1 Why a dispatcher

formula roles (researcher, analyst, architect, …, refactorer)
need to run as **real sub-sessions** so the supervisor (`cos_supervise`)
can collect parallel evidence and merge it into a typed `EvidenceBundle`.
The dispatcher converts a `DispatchRequest` into a single-turn SDK
`query()` call.

### 7.2 Hardened options (2026-05-04)

```python
ClaudeAgentOptions(
    system_prompt={
        "type": "preset",
        "preset": "claude_code",
        "append": <role spec + dispatch context + JSON instruction>,
        "exclude_dynamic_sections": True,   # cross-cwd cache reuse
    },
    max_turns=1,
    allowed_tools=[..., "mcp__coding-os__*"],  # MCP wildcard always added
    permission_mode="dontAsk",                  # headless; no prompts
    setting_sources=["project"],                # isolate from ~/.claude/
    model=request.model,
    effort="max" if request.model in OPUS_47_IDS else None,
    skills=role_skills,                         # from agent frontmatter
    cwd=request.cwd,
)
```

Why each line:

| Line | Reason |
|---|---|
| `system_prompt = preset claude_code + append` | Default SDK prompt is **minimal** since the rename. Without the `claude_code` preset, formulas lose Claude Code's coding/safety baseline. |
| `exclude_dynamic_sections=True` | Strips cwd/git/date/OS/memory_paths from the system prompt, emits them as a first-user-message block. Lets the prompt cache survive across consumer-project cwds. |
| `permission_mode="dontAsk"` | Headless — never prompt the user. Allow-list is the contract; unmatched tools deny silently. |
| `setting_sources=["project"]` | Sub-sessions must be reproducible across machines. Default loads `user`+`project`+`local` — `~/.claude/` would silently change behavior. |
| `allowed_tools` includes `mcp__coding-os__*` | `acceptEdits` does NOT auto-approve MCP. Always inject the wildcard alongside caller-provided allow-list. |
| `effort="max"` on Opus 4.7 | Py SDK 0.1.73 caps at `"max"` (no `"xhigh"` yet — TS-only as of 2026-05-04). |
| `skills=role_skills` | Sub-sessions don't inherit parent skills. Each role's `skills:` frontmatter declares dependencies (e.g. implementer → `["clean-code"]`). |

### 7.3 Contract

**Input** — [DispatchRequest](../../src/core/thinking_os/dispatcher.py):

| field | type | description |
|---|---|---|
| `formula_id` | str | e.g. `"implementer"`. Restricted to `[A-Za-z0-9_-]+`. |
| `agent_file` | str | **absolute** path to role md file. Dispatcher rejects relative paths. |
| `prompt` | str | composed system+user prompt. |
| `input_slice` | dict | upstream-only bundle view from `build_input_slice()`. |
| `persona_id` | str\|None | dispatch persona. |
| `intensity` | `"light"\|"standard"\|"full"` | filters role step list. |
| `allowed_tools` | list[str] | caller-provided allow-list — `mcp__coding-os__*` is always appended. |
| `timeout_s` | float | hard timeout, default 300s. |
| `cwd` | str\|None | project root for the sub-session. |
| `model` | str\|None | (NEW) model id. None = SDK default. |

**Output** — `DispatchResult`:

| field | type |
|---|---|
| `status` | `"ok"\|"timeout"\|"error"\|"skipped"` |
| `output_json` | parsed JSON from the formula's ```json``` block |
| `latency_ms` | wall clock |
| `dispatcher_name` | `"claude-sdk"` or `"default"` |
| `error` | str\|None |
| `raw_transcript` | str\|None |

### 7.4 Failure modes

| Failure | Status | Note |
|---|---|---|
| `claude_agent_sdk` not importable | `error` | Factory falls back to `default` dispatcher. |
| `agent_file` is relative | `error` | Dispatcher rejects to avoid silent cwd-search ambiguity. |
| Agent file missing | `error` | `FileNotFoundError`. |
| Sub-session exceeds `timeout_s` | `timeout` | Includes partial transcript. |
| No `json` block in transcript | `error` | "no JSON block found in agent output". |
| Tool denied by permission_mode | n/a | Logged in `result.permission_denials`; transcript continues without that tool. |

### 7.5 MCP envelope path

After successful dispatch, callers should NOT call `cos_supervise_record_output`
manually — `cos_dispatch_formula_run` (in [src/core/thinking_os/tools/cognition.py](../../src/core/thinking_os/tools/cognition.py))
persists the bundle and writes the `formula_dispatches` audit row.

## 8. Subagent skill inheritance

Agent SDK 0.1.73 docs are explicit: "Subagents do NOT inherit skills
unless listed in `AgentDefinition.skills`." This adapter implements that
contract by reading `skills:` from each role's frontmatter and forwarding
to `ClaudeAgentOptions.skills`.

Current mapping (2026-05-04):

| Role | Skills declared |
|---|---|
| `implementer` | `[clean-code]` |
| `reviewer` | `[clean-code]` |
| `debugger` | `[search, codebase-explorer]` |
| `security_auditor` | `[security-web, clean-code]` |
| `refactorer` | `[clean-code, search]` |
| `researcher` | `[search, codebase-explorer]` |
| `analyst` | `[thinking_os]` |
| `architect` | `[thinking_os]` |
| `documenter`, `deployer`, `observer` | `(none)` |

Add a skill to a role: edit `src/core/thinking_os/agents/<role>.md` frontmatter.
Other adapters that don't understand `skills:` ignore it (Rule 1 — core
stays agent-agnostic).

## 9. Permissions — gotchas the SDK docs flag

Evaluation order (digest §B.4):
1. Hooks
2. Deny rules (`disallowedTools` + settings.json `deny`) — wins even in `bypassPermissions`.
3. Permission mode
4. Allow rules (`allowedTools` + settings.json `allow`)
5. `can_use_tool` callback (skipped in `dontAsk`)

**Multi-decision precedence:** `deny > defer > ask > allow`.

| Mode | Behavior | Use for coding-os |
|---|---|---|
| `default` | Unmatched tools call `can_use_tool`; no callback = deny | NOT used (would prompt). |
| `acceptEdits` | Auto-approves Edit/Write/filesystem-Bash within cwd | NOT used in dispatcher (would still prompt for MCP). |
| `dontAsk` | Never prompts; only allow-listed tools run | **Dispatcher uses this.** |
| `plan` | No tool execution; `AskUserQuestion` only | n/a. |
| `bypassPermissions` | All tools run; deny rules + hooks still apply; `allowed_tools` does NOT constrain | NEVER use — security hole. |
| `auto` | Model classifier per call | Reserve for interactive UI. |

Subagent inheritance warning: parent in `bypassPermissions`/`acceptEdits`/`auto`
inherits to all children — cannot override per-subagent. Dispatcher uses
`dontAsk` so this is moot for our tree.

## 10. Skills — frontmatter contract

Per SDK docs §E.1:

| Field | Limit | Notes |
|---|---|---|
| `name` | ≤64 chars, lowercase + digits + hyphens | Cannot contain "anthropic"/"claude". |
| `description` | ≤1024 chars | Third-person voice. |
| `name + description + when_to_use` | ≤1,536 chars listing budget | Otherwise truncated in skill listing. |

Spot-check by running:

```bash
uv run python -c "from pathlib import Path; import yaml; [print(p, len(yaml.safe_load(p.read_text().split('---', 2)[1])['description'])) for p in Path('src/core/skills').rglob('SKILL.md')]"
```

YAML gotcha: descriptions containing `: ` (colon-space) MUST be quoted.
The SDK loader uses YAML — unquoted colon-space breaks the parser
(found and fixed in `src/core/skills/search/SKILL.md` 2026-05-04).

## 11. Plugins

Loadable via `plugins=[{type:"local", path}]` only — SDK 0.1.73 has no
remote plugin registry. coding-os "templates" model is compatible —
distribute as local plugin paths.

Plugin layout per SDK §E.2:

```
my-plugin/
├── .claude-plugin/plugin.json    # required
├── skills/<name>/SKILL.md
├── commands/*.md                 # legacy
├── agents/*.md
├── hooks/hooks.json
└── .mcp.json
```

coding-os does not currently package any plugin manifests; templates ship
as scaffold overlays instead.

## 12. Observability

### 12.1 Cost / usage

`ResultMessage.total_cost_usd` is a **client-side estimate** — do NOT
bill from it. Use Anthropic's Usage and Cost API for billing.

Per-step:
- `assistant_msg.usage.input_tokens / output_tokens / cache_read_input_tokens / cache_creation_input_tokens`
- Dedupe by `assistant_msg.message_id` (parallel tool calls share IDs).

Per-model breakdown: `result.model_usage` map.

### 12.2 OpenTelemetry

| Signal | Enable env | Notes |
|---|---|---|
| Metrics | `OTEL_METRICS_EXPORTER=otlp` | Tokens, cost, sessions, LoC. |
| Logs | `OTEL_LOGS_EXPORTER=otlp` | Prompts, API requests, tool results. |
| Traces | `OTEL_TRACES_EXPORTER=otlp` + `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1` | Hook spans require `ENABLE_BETA_TRACING_DETAILED=1`. |

**Never** use `console` exporter — it collides with the SDK's stdout
pipe. Override `OTEL_SERVICE_NAME` (default `claude-code`) per-adapter
when shipping multiple agents in one collector.

### 12.3 Sessions

Stored at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` where
`<encoded-cwd>` replaces non-alphanumerics with `-`. Cross-host = ship
the .jsonl.

### 12.4 File checkpointing

NOT enabled by default in dispatcher. To enable:

```python
ClaudeAgentOptions(
    enable_file_checkpointing=True,
    extra_args={"replay-user-messages": None},
    ...
)
```

Caveats:
- Only tracks `Write`, `Edit`, `NotebookEdit` — `Bash` mutations bypass.
- Same-session only; rewind requires `resume: sessionId` + empty `""`
  prompt + `rewind_files(uuid)` + break.

## 13. Verification

```bash
# Unit + smoke
uv run --extra claude-sdk --extra rag pytest src/core/thinking_os/tests/test_dispatcher.py -q

# Adapter install + parity
uv run pytest tests/test_adapters.py tests/test_adapter_parity.py tests/test_adapter_registry.py -q

# Real CLI dispatch (requires Claude CLI on PATH + Anthropic API key)
uv run --extra claude-sdk python src/scripts/e2e_dispatch_tool.py

# Hook syntax
make verify-hooks

# SDK version smoke
uv pip show claude-agent-sdk mcp | grep -E "^(Name|Version)"
claude --version
```

## 14. Branding

Per Anthropic licensing: cannot ship as "Claude Code" / "Claude Code
Agent". OK: "Claude Agent", "Powered by Claude". coding-os internal
tooling is fine; user-facing surfaces (UI labels, README, marketing)
require review.

## 15. What this adapter does NOT do (yet)

1. **`PermissionRequest` hook** — SDK supports it, would let coding-os
   centralize permission UX. Not wired.
2. **Plugin manifests** — coding-os ships skills directly under
   `.claude/skills/`, no `plugin.json`. Reasonable trade-off; revisit
   when consumer projects need third-party plugin discovery.
3. **`auto` permission mode UI** — TS preview reaches further than Py;
   leave off until coding-os has an interactive permission surface.
4. **OTEL collector defaults** — env vars work, but no project-default
   collector endpoint in install.sh. Future enhancement.
5. **`PreCompact` hook** — useful for memory-state rehydration; SDK
   supports it but no coding-os hook listens yet.

## 16. Related

- [src/adapters/claude/adapter.yaml](../../src/adapters/claude/adapter.yaml) — capability declaration
- [src/adapters/claude/sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py) — formula dispatcher
- [src/adapters/claude/install.sh](../../src/adapters/claude/install.sh) — install entry
- [src/adapters/claude/settings.template.json](../../src/adapters/claude/settings.template.json) — rendered hook config (do not hand-edit)
- [src/adapters/claude/settings.local.template.json](../../src/adapters/claude/settings.local.template.json) — user permission seed
- [src/core/thinking_os/dispatcher.py](../../src/core/thinking_os/dispatcher.py) — Protocol + factory
- [src/core/thinking_os/dispatchers/default.py](../../src/core/thinking_os/dispatchers/default.py) — non-Claude fallback
- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — hook SSOT
- [docs/engineering/adapter-parity.md](../engineering/adapter-parity.md) — cross-adapter contract
- [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md) — `cos_*` response shape
- [docs/playbooks/adapter-authoring.md](../playbooks/adapter-authoring.md) — generic adapter authoring contract
- [docs/playbooks/mcp-tool-authoring.md](../playbooks/mcp-tool-authoring.md) — MCP tool authoring

## 17. Changelog

| Date | Change |
|---|---|
| 2026-04-20 | Initial Claude-SDK dispatcher (`claude-agent-sdk>=0.1.0`). |
| 2026-04-24 | Doc anchor pinned at v0.1.0 dispatcher reference. |
| 2026-05-04 | **Q-bundle:** SDK floor → `>=0.1.73,<0.2.0`; dispatcher hardened (preset+exclude_dynamic_sections+setting_sources+dontAsk+Opus 4.7 effort gate+abs-path assertion+role-skills inheritance); `mcp__coding-os__*` added to `settings.local.template.json`; `SubagentStart`/`SubagentStop`/`PostToolUseFailure` declared in `registry.yaml` + `adapter.yaml`; `agent-presence.sh` extended; skill descriptions audited (`search` SKILL.md frontmatter quoted); doc rewritten as full reference (TASK-002). |
| 2026-05-05 | **Q.deep P0 wave:** `output_format` JSON Schema enforcement; `max_budget_usd` ceiling; programmatic `PreToolUse`+`PostToolUseFailure` hooks; OTEL env propagation; `disallowed_tools` deny-list; schema migration v23 (6 cost columns on `formula_dispatches`); skill `paths:` globs + pytest gate; `ClaudeAgentOptions` regression test; `.claude/agents/` cleanup (D2); `cos sync-all` propagation (TASK-003 P0 wave). |
| 2026-05-05 | **Q.deep P1 wave:** `UserMessage.uuid` capture for file checkpointing (T9); `session_id` forwarded to SDK (T7.1); `error_max_structured_output_retries` surfaced in `DispatchResult.error` (T1.5); `long_context: true` on researcher frontmatter (T10.3); `enable_file_checkpointing` on implementer/refactorer (T9.1); dispatch metrics emitted via `agent_metrics` (T2.5/T8.4); hub `/api/cognition/cost`+`/dispatchers`+`/dispatchers/{id}/tools` endpoints (T2.4/T19.1/T19.2); `cos doctor --otel` probe (T8.3); `sdk_e2e` pytest marker (T12.2); import-failure test (T12.4). |
| 2026-05-05 | **Q.deep wave 3:** schema migration v27 — `formula_dispatches` gains `sub_session_id` / `model` / `checkpoints_jsonb` columns + 2 indices for SDK telemetry persistence; `_persist_dispatch_output` writes 18-column INSERT including the 3 new fields; T1.6 — Pydantic validate runs before INSERT, malformed output skips row; T19.3 — `/api/board/list` exposes `sub_session_counts`; T16.2 — branding test (`test_branding.py`); T17.1 — version 0.2.0 → 0.3.0. |

## 17a. Architectural Decisions (D1–D6)

Decisions settled 2026-05-05 during TASK-003. See [claude-deepening-checklist.md](claude-deepening-checklist.md) for full rationale.

| ID | Decision | Rationale |
|---|---|---|
| **D1** | KEEP `query()` per formula | `agents={…}` + Agent tool forces sub-sessions to inherit parent `permission_mode`; headless `dontAsk` contract would break. Cache reuse via `exclude_dynamic_sections` already achieved. |
| **D2** | DELETE `.claude/agents/` symlinks | D1 keeps `query()` so symlinks are misleading scaffolding. Slash-command path (`.claude/commands/role-*.md`) retained. Removed in `install.sh` + `scaffold_manifest.json`. |
| **D3** | KEEP scaffold (no plugin manifest) | Plugins target third-party distribution; coding-os ships its own kernel. Revisit when external consumers want plug-and-play. |
| **D4** | ALLOW adapter-private hooks under `src/adapters/claude/hooks/` | Cross-adapter hooks stay in `src/core/hooks/`; SDK-only matchers (SubagentStart etc.) live adapter-side. `hook_renderer.py` respects `adapter_scope:` field. |
| **D5** | Leave OTEL collector to operator | coding-os exports the env-var contract; bundling a collector would couple the kernel to a specific backend. `cos doctor --otel` probes the configured endpoint instead. |
| **D6** | Long context opt-in per request | Formula bundles fit in 200k; only big-doc research needs 1M. `DispatchRequest.long_context: bool` + role frontmatter `long_context: true` (researcher). |
