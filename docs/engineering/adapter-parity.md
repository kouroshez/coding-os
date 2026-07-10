<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-07-10 -->
# Adapter Parity - Claude vs Codex Coverage

Purpose: Define equivalent behavior across Claude and Codex without claiming that their runtime APIs are identical.
Read when: a hook, skill, dispatcher, MCP integration, or lifecycle behavior differs by adapter.
Skip when: the change is entirely inside an adapter and does not alter a shared contract.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Parity Rule

Parity is measured at the kernel outcome:

- Was a protected edit blocked before it happened?
- Was task and memory state updated after the operation?
- Did lifecycle context reach the model?
- Did formula dispatch return the same `DispatchResult` shape?
- Is a missing capability explicit rather than silently skipped?

The implementation may differ. Claude can receive a native `Write` payload while Codex reports an `apply_patch` command; the adapter translates both to the same core-hook input contract.

## Current Summary

- Both adapters install the shared hooks, rules, skills, and MCP server.
- Claude and Codex both support Bash, file-edit, MCP, prompt, compact, subagent, Stop, and permission lifecycle hooks, but their event names and payload shapes differ.
- Codex file edits are intercepted through `apply_patch`. Its adapter canonicalizes the runtime alias to `Edit`, extracts every affected path, and sequences the unchanged core hooks.
- Codex still has no `PostToolUseFailure` equivalent and no native Claude `Skill` tool matcher. These remain honest deficits.
- Non-managed Codex hooks require hash-based review through `/hooks`; installation cannot safely auto-trust them.
- Formula dispatch is adapter-loaded for both providers. Hub chat is not yet fully hexagonal because its core route imports the Claude SDK directly.

## Runtime Event Matrix

Verified against the official runtime documentation on 2026-07-10.

| Outcome | Claude | Codex | Adapter handling |
|---|---|---|---|
| Shell pre/post gate | `PreToolUse`/`PostToolUse` Bash | same | direct or sequential dispatcher |
| File edit pre/post gate | `Write`/`Edit` with `file_path` | `apply_patch` with patch in `tool_input.command`; aliases `Edit`/`Write` | Codex edit normalizer |
| MCP pre/post gate | MCP tool matcher | MCP tool-name matcher | direct registry render |
| Prompt context | `UserPromptSubmit` | `UserPromptSubmit` | dispatcher forwards `additionalContext` |
| Session startup/resume | `SessionStart` | `SessionStart` | native |
| Compaction | compact source / `PreCompact` | compact source, `PreCompact`, `PostCompact` | shared hooks only where registered |
| Subagent lifecycle | start/stop | start/stop | native shared pair |
| Stop continuation/context | `Stop` | `Stop` JSON output | Codex dispatcher aggregates output |
| Permission request | supported | supported | provider-specific decision schema |
| Tool failure | `PostToolUseFailure` | no equivalent hook | Codex stream/error observation only |
| Skill invocation | `Skill` matcher | no native matcher | skill guidance, not tool-hook parity |

## Hook Coverage

The renderer reads [registry.yaml](../../src/core/hooks/registry.yaml), filters each event/matcher through `adapter.yaml::hook_capabilities`, then replaces selected groups with adapter dispatchers.

| Hook family | Claude | Codex | Notes |
|---|---|---|---|
| Bash safety and verification | yes | yes | Codex coalesces concurrent matches into `codex-pretool-dispatch.sh`. |
| Edit safety (`block-*`) | yes | yes | Codex receives one normalized payload per patch path. |
| Docs/task/skill gates | yes | yes for file edits | Codex edit dispatcher preserves fail-closed exit `2`. |
| Post-edit capture/index/reminders | yes | yes | Advisory after the patch has applied. |
| Prompt cognition/context | yes | yes | Dispatcher output must not be discarded. |
| Session start/recovery | yes | yes | `startup`, `resume`, and `compact` are supported. |
| Presence on tool failure | yes | no | No Codex `PostToolUseFailure` event. |
| Presence on subagents | yes | yes | Start and stop are shared. |
| Skill-use telemetry | yes | no | Codex has skills but not a `Skill` tool hook. |

Run the executable report rather than counting this table by hand:

```bash
cos hooks-list --agent claude
cos hooks-list --agent codex
uv run pytest tests/test_adapter_parity.py tests/test_hook_renderer.py -q
```

## Deterministic Ordering

Multiple Codex command hooks that match one event start concurrently. Coding OS therefore coalesces groups whose order is a safety contract.

```text
safety -> enforcement -> cognition -> task -> retrieval
       -> observability -> reminder -> meta
```

The registry renderer owns category ordering. `adapter.yaml::hook_dispatchers` owns the corresponding delegate order for a coalesced Codex group. `tests/test_adapter_parity.py` requires each dispatcher loop to equal its manifest delegate set.

For edit events, one patch may affect several paths. The adapter runs the ordered delegate list for each path and stops immediately on a PreToolUse block. This is intentionally stricter than checking only the first file in a patch.

## Payload Boundary

Core hooks consume this canonical edit subset:

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "path/to/file.py",
    "content": "adapter-provided edit content"
  }
}
```

Claude already provides a compatible shape. Codex provides:

```json
{
  "tool_name": "apply_patch",
  "tool_input": {
    "command": "*** Begin Patch\n*** Update File: path/to/file.py\n..."
  }
}
```

The Codex adapter translates this at its boundary. Patch grammar must never leak into `src/core/hooks/**`; otherwise every kernel hook becomes provider-aware.

If an `apply_patch` PreToolUse payload cannot be parsed into at least one path, the edit dispatcher fails closed with an actionable error. PostToolUse parsing failure is logged because side effects have already happened.

## Output Boundary

Adapter dispatchers must preserve model-visible hook output:

- `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, and `Stop` may return `additionalContext`.
- PreToolUse exit `2` blocks and forwards stderr as the reason.
- PostToolUse cannot undo an operation; it can replace or annotate the tool result.
- Stop exit `0` must emit valid JSON when it has output; `{}` is valid for no-op success.

Dropping delegate stdout is a parity bug, not a harmless implementation detail.

## Trust And Installation

The Codex installer writes absolute hook commands so nested working directories resolve correctly. It enables the canonical feature:

```toml
[features]
hooks = true
```

Project-local hooks still require project trust plus `/hooks` review. Trust is recorded against the exact hook hash; regeneration or upgrades can require review again. The installer reports this step and never modifies Codex's private trust state.

## Remaining Capability Bounds

| Bound | Consequence | Mitigation |
|---|---|---|
| No Codex `PostToolUseFailure` hook | failure-only capture is weaker | inspect JSONL error/failed items in programmatic runs |
| No Codex `Skill` tool hook | no exact skill-use telemetry | use skill instructions and downstream outcome evidence |
| Python SDK beta lags stable CLI schema | model discovery can fail validation | stable CLI default; SDK opt-in and compatibility smoke |
| Hub route imports Claude SDK | Codex cannot be marked `runtime: in_process` honestly | extract and migrate a shared interactive runtime port |
| Codex custom prompts deprecated | `.codex/commands` is not a durable native UX | move command semantics into skills |

Do not paper over these bounds with aspirational manifest entries. A capability is enabled only after an official spec check and an executable runtime test.

## Sync And Verification

After adapter capability or registry changes:

```bash
make regen-adapter-templates
uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q
make verify-hooks
bash src/adapters/codex/install.sh
```

Review regenerated templates and golden fixtures line by line. A larger Codex template is expected when a newly supported event closes a real gap; an unexplained expansion is not.

## Adapter Manifest Contracts

`presence` describes how the Hub detects a runtime and labels it. `runtime_session_marker` describes how shared hooks derive the per-panel session id. Both are data-driven so adding an adapter does not require provider literals in core code.

Resolution priority is:

1. explicit `$COS_PANEL_ID`;
2. hook stdin `session_id`/`sessionId`;
3. manifest-declared environment variables;
4. PPID fallback for raw shell tests.

## Sources

- [Codex hooks](https://developers.openai.com/codex/hooks)
- [Codex configuration](https://developers.openai.com/codex/config-advanced)
- [Claude Agent SDK hooks](https://platform.claude.com/docs/en/agent-sdk/hooks)
- [Codex adapter reference](../adapters/codex.md)
- [Adapter authoring playbook](../playbooks/adapter-authoring.md)
