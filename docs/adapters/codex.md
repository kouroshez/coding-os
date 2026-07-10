<!-- domain:ADAPTERS | layer:reference | ssot:true | updated:2026-07-10 -->
# Codex Adapter

Purpose: Current contract for the OpenAI Codex adapter: execution backends, hook translation, capability bounds, dependency policy, and the path to full interactive parity.
Read when: editing `src/adapters/codex/`, changing adapter manifests or hook rendering, or adding a programmatic Codex runtime.
Skip when: the change is Claude-only and does not alter a shared adapter port.

> Nav: [AGENTS.md](../../AGENTS.md) > [adapters](.) > **codex**
> Status: live for install, MCP, skills, hooks, and formula dispatch; Hub chat remains roadmap pending the shared runtime port.

---

## Verified Baseline

The following was verified on 2026-07-10 against package registries, the installed binaries, official documentation, and executable smoke tests.

| Surface | Repository state | Current upstream | Decision |
|---|---|---|---|
| Codex CLI | installed `0.144.1` | stable `0.144.1` | Primary production backend. No upgrade needed. |
| TypeScript Codex SDK | not a repo dependency | `@openai/codex-sdk` `0.144.1` | Do not add a Node-to-Python bridge. The SDK itself wraps `codex exec` and JSONL. |
| Python Codex SDK | optional `codex-sdk` extra | `openai-codex` `0.1.0b3` | Optional beta backend only; never replace the stable CLI automatically. |
| Generic Python OpenAI SDK | not a repo dependency | `openai` `2.45.0` | Do not add it for Codex dispatch. It is an API client, not the Codex thread runtime. |
| Claude Agent SDK | locked `0.2.110` | `0.2.115` | Comparison baseline only; a Claude patch refresh is independent of Codex parity. |

The Python Codex SDK is official but still beta. Version `0.1.0b3` pins `openai-codex-cli-bin==0.137.0a4`, while the stable CLI is `0.144.1`. Its `CodexConfig(codex_bin=...)` override successfully ran a read-only turn against `0.144.1`, but `models()` failed validation because the newer CLI reports `max` and `ultra` reasoning levels that the beta SDK does not yet model. Therefore:

1. Stable CLI execution is the default.
2. The Python SDK may be installed through an optional extra and selected explicitly.
3. SDK calls must use the active `codex` binary, not the older bundled binary.
4. Protocol validation failures must not silently fall back after a turn has started, because that could execute the same task twice.
5. `runtime: in_process` stays false until the shared Hub runtime port exists and the SDK model/session surface passes compatibility checks.

## Hexagonal Boundary

The kernel owns `DispatchRequest` and `DispatchResult`. The Codex adapter owns every Codex-specific detail:

```text
thinking_os DispatchRequest
          |
          v
src/adapters/codex/sdk_dispatcher.py
          |
          +-- default: codex exec --json, prompt over stdin
          |
          +-- optional: openai-codex AsyncCodex/app-server
          |
          v
thinking_os DispatchResult
```

The kernel must not import `openai_codex`, know Codex CLI flags, parse Codex JSONL, or translate Codex hook payloads. A second adapter should require a manifest, installer, optional dispatcher, and tests, not provider conditionals in `src/core/`.

The current exception is Hub chat: `src/core/web/routes/cognition.py` imports `claude_agent_sdk` directly and loads a Claude-only session-options builder. That is a real hexagonal violation. Making Codex interactive there requires extracting a shared runtime port and migrating Claude behind it; it is not an adapter-local edit.

## Dispatcher Contract

The stable CLI backend runs one ephemeral, read-only formula turn:

```text
codex --ask-for-approval never exec --ignore-user-config --disable hooks --config 'mcp_servers={}' --json --ephemeral --sandbox read-only -
```

`request.model` adds `--model <id>`. The composed prompt is written to stdin, avoiding command-line length limits and process-list exposure. The adapter parses JSONL and takes the last completed `agent_message` as the final response. It then extracts the EvidenceBundle JSON block into `DispatchResult.output_json`.

User configuration is ignored and formula hooks plus MCP servers are disabled for the sub-run. This prevents recursive lifecycle hooks and removes external mutation paths that a read-only filesystem sandbox cannot constrain. Roles that opt into structured output pass their Pydantic schema through CLI `--output-schema` or SDK `output_schema`.

The former invocation, `codex --no-interactive --json <prompt>`, is not valid on current Codex. Non-interactive execution is the `exec` subcommand, and `--no-interactive` is not a current flag.

The optional Python SDK backend uses `AsyncCodex` with:

- the active `codex` path through `CodexConfig(codex_bin=...)`;
- `Sandbox.read_only` and `ApprovalMode.deny_all` for formula output;
- `developer_instructions` for the formula body;
- `thread.run()` for one turn;
- an outer timeout owned by the adapter.

No Codex backend currently enforces `max_budget_usd`. A request that supplies it fails before dispatch; silently dropping a financial ceiling violates the dispatcher contract.

## Capability Matrix

Parity means equivalent kernel outcomes, not identical provider APIs.

| Capability | Claude adapter | Codex adapter target | State |
|---|---|---|---|
| Durable repository guidance | `CLAUDE.md`/`AGENTS.md` | `AGENTS.md` hierarchy | native |
| Reusable skills | Claude skills | Codex agent skills | native |
| Slash-command Markdown | `.claude/commands` | Codex custom prompts are deprecated; skills are the supported replacement | degraded, migrate to skills |
| MCP client | stdio/HTTP through Claude config | stdio/HTTP through `.codex/config.toml` | native |
| Formula dispatch | Claude Agent SDK | stable CLI plus optional Python SDK | implemented by adapter |
| Structured output | SDK output format | CLI `--output-schema` / SDK output schema | native and wired |
| Session continuation | SDK resume | CLI `exec resume` / SDK thread resume | native, not required by one-turn formula dispatch |
| Sandbox | SDK permissions and tools | `read-only`, `workspace-write`, `danger-full-access` | native |
| Per-tool allowlist | SDK `allowed_tools`/`disallowed_tools` | no equivalent Python SDK argument | degraded; formula runs narrow to read-only with MCP disabled |
| Pre/Post Bash hooks | native | native | parity |
| Pre/Post file-edit hooks | `Write`/`Edit` payload | `apply_patch`, alias-matched as `Edit`, patch in `tool_input.command` | adapter translation implemented |
| MCP tool hooks | native matchers | native MCP tool-name matchers | parity |
| Prompt context injection | `UserPromptSubmit` output | `UserPromptSubmit.additionalContext` | parity |
| Compact lifecycle | SessionStart compact plus SDK hooks | SessionStart compact, PreCompact, PostCompact | Codex has the required events |
| Subagent lifecycle | start/stop | start/stop | parity for shared events |
| Tool-failure hook | `PostToolUseFailure` | no matching Codex event | impossible today; observe error items instead |
| Permission hook | SDK/CLI permission callbacks | `PermissionRequest` | native, output schemas differ |
| Hook trust | project/settings trust | hash-based review for non-managed hooks | explicit operator step required |
| Hub interactive chat | in process | blocked by Claude-coupled core route | requires shared runtime port |

## Hook Translation

Codex `PreToolUse` and `PostToolUse` can intercept Bash, MCP calls, and file edits performed through `apply_patch`. For file edits, Codex keeps `tool_name: "apply_patch"` and puts the patch in `tool_input.command`; Claude-oriented core hooks expect `tool_name: "Edit"` and `tool_input.file_path`.

The translation belongs at the adapter boundary:

1. The manifest uses `Edit` as Codex's canonical alias so all registry matchers (`Write|Edit`, `Write|Edit|MultiEdit`, and `Edit`) collapse into one deterministic group.
2. An adapter-private normalizer extracts every `Add File`, `Update File`, `Delete File`, and `Move to` path from the patch.
3. The edit dispatcher invokes the unchanged core hooks once per affected path with a Claude-shaped payload.
4. PreToolUse exits `2` immediately when a delegate blocks.
5. PostToolUse is advisory because the edit has already happened.

This avoids leaking Codex patch grammar into `src/core/hooks/**` and keeps the kernel agent-agnostic. The cost is proportional to `files x hooks`; typical patches are small, while correctness requires checking every affected path.

Codex runs multiple matching command hooks concurrently. Dispatcher groups therefore preserve the registry's safety-to-observability ordering. A dispatcher must also forward delegate `additionalContext`; dropping stdout makes prompt, Stop, and reminder hooks silent even though the runtime supports them.

## Hook Trust

Non-managed Codex command hooks are trusted by exact hash. New or changed hooks are skipped until reviewed with `/hooks`. The installer must:

- enable the canonical `hooks` feature;
- install and render the project hook configuration;
- print a clear `/hooks` review step;
- never mutate Codex's private trust store or use `--dangerously-bypass-hook-trust` as a persistent default.

Managed enterprise deployments may enforce trusted hooks through `requirements.toml`; that is an administrator policy surface, not a project installer shortcut.

## Adapter Complexity

These are engineering estimates derived from this repository's contracts, not provider promises.

| Scope | Typical effort | Main risk |
|---|---:|---|
| Manifest + idempotent installer + MCP wiring | 0.5-1 day | filesystem/config conventions |
| Skills/rules/instructions mapping | 1-2 days | provider UX differences and deprecated surfaces |
| Hook enforcement parity | 2-4 days | event coverage, payload translation, ordering, trust |
| One-turn formula dispatcher | 1-2 days | timeout, auth, sandbox, stream parsing, structured result |
| Interactive Hub runtime | 4-8 days after a shared port exists | resume, streaming, cancellation, tools, presence, models |
| New provider with weak hooks or no SDK | 1-3 weeks | honest degraded modes and executable end-to-end evidence |

Adding a directory is easy. Shipping an adapter that preserves safety, lifecycle, observability, and UX is not. The architecture should make provider differences declarative or adapter-local; it cannot manufacture lifecycle events that a provider does not expose.

## Delivery Plan

### Phase A - Current Adapter Closure (completed 2026-07-10)

- Correct the stable CLI dispatcher and JSONL parsing.
- Add the latest Python SDK as an optional beta extra, with explicit backend selection and active-binary override.
- Update Codex hook capabilities to current official events and MCP/edit matchers.
- Add adapter-private `apply_patch` normalization and deterministic edit dispatchers.
- Forward `additionalContext` from prompt, Stop, pre-tool, and post-tool dispatcher groups.
- Regenerate templates and golden fixtures; run adapter, hook, dispatcher, and real read-only smoke tests.

### Phase B - Shared Interactive Runtime Port

Extract an adapter-loaded protocol from Hub cognition with operations for:

- availability and capability discovery;
- start/resume/send/cancel;
- normalized stream events (`text`, `tool_start`, `tool_end`, `usage`, `error`, `done`);
- model and reasoning-effort discovery;
- session identity, presence, and transcript lookup;
- sandbox, approval, tool, and budget capabilities.

Migrate Claude behind that port without changing behavior, then add Codex. This phase changes the Claude path and requires its own migration task and rollback evidence.

### Phase C - Command UX Consolidation

Move reusable command semantics into skills, keep provider-specific slash commands as thin aliases where supported, and stop treating `.codex/commands` as a native Codex surface. Evaluate a coding-os Codex plugin only if it removes installer/config duplication without weakening project-local versioning.

### Phase D - Cross-Adapter Orchestration

After both runtimes implement the shared port, let the supervisor select an adapter from declared capabilities, model policy, budget, and task shape. Adapter choice must remain observable and overridable; no hidden provider switch is allowed.

## Sources

- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Codex CLI reference](https://developers.openai.com/codex/cli/reference)
- [Codex MCP](https://developers.openai.com/codex/mcp)
- [Codex subagents](https://developers.openai.com/codex/subagents)
- [Codex skills](https://developers.openai.com/codex/skills)
- [Codex custom prompts](https://developers.openai.com/codex/custom-prompts)
- [Codex TypeScript SDK source](https://github.com/openai/codex/tree/main/sdk/typescript)
- [Codex Python SDK source](https://github.com/openai/codex/tree/main/sdk/python)
- [Claude Agent SDK hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)

## See Also

- [Adapter authoring playbook](../playbooks/adapter-authoring.md)
- [Adapter parity](../engineering/adapter-parity.md)
- [Dispatcher contract](../engineering/dispatcher-contract.md)
- [Claude SDK reference](claude-sdk.md)
