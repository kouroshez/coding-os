<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-07-10 -->
# Claude Session-Options Builder (SSOT)

> **Purpose:** One function — `claude_session_options(profile, …)` in
> [src/adapters/claude/sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py) —
> is the single constructor of `ClaudeAgentOptions` for every Claude SDK
> entry point (Hub chat, task-author, onboard, formula dispatch). It
> collapses the five hand-rolled option sites (audit P1) so a
> capability/security/policy is written once and reused.

## Why

Five independent `ClaudeAgentOptions(...)` sites drifted. The Hub chat
paths (`chat_new`, `chat_send`) omitted MCP registration (**P2** — the
system prompt invites `cos_*` while `setting_sources=[]` + no
`mcp_servers` leaves them unregistered) and the destructive-Bash deny
floor (**P3** — `rm -rf` / `git push --force` unguarded under
`permission_mode="dontAsk"`), while author/onboard/dispatch each spelled
the same constants (`mcp__coding-os__*`, the deny tuple, the
`claude_code` preset) differently. The builder removes the drift.

## Contract

```
claude_session_options(
    profile, *, cwd, model, system_prompt,
    resume=None, fork=False, effort=None,
) -> ClaudeAgentOptions
```

Profiles: `chat` · `chat_resume` · `author` · `onboard` · `dispatch`.

**Shared spine (every profile):**
- `permission_mode="dontAsk"`.
- `mcp_servers` = the `coding-os` server read from the project `.mcp.json`
  — capability is unconditional and independent of `setting_sources` (**P2**).
- `allowed_tools` includes `mcp__coding-os__*` (`dontAsk` does not
  auto-approve MCP).
- If the profile permits Bash → `disallowed_tools` includes the
  `_DESTRUCTIVE_BASH_DENY` floor (**P3**).
- `env` includes the Claude-auth override from `_claude_auth_env(cwd)`
  (**TASK-756**) — `ANTHROPIC_API_KEY` set when Hub Settings → Claude Auth is
  in `api_key` mode, explicitly cleared (not merely omitted) otherwise, so a
  stray key in the Hub server's own shell can never silently override a
  project's chosen subscription/API-key mode.

**Per-profile deltas (the only variation):** tool allow/deny class,
`max_turns`, `include_partial_messages`, `setting_sources`.

**Derives from (never hardcoded):** MCP launch command ← `.mcp.json`
(the installer's output); deny floor + MCP wildcard ← the module
constants in `sdk_dispatcher.py`; model/effort ← caller; auth env ←
`hub-settings.json::claude_auth` (adapter-resolved from `cwd`, not
caller-supplied — see [claude-sdk.md](claude-sdk.md)).

## Layering (P4 / P8)

The builder lives in the adapter (it owns SDK **construction**). Core/web
loads it via the existing dynamic adapter-load seam (the
`thinking_os.dispatcher` importlib pattern), so `src/core/**` never
constructs `ClaudeAgentOptions` — that is the enforced P8 boundary
(guard: `tests/test_no_hardcoded_anthropic.py::test_no_claude_agent_options_construction_in_core`).

Three lazy, fail-soft `claude_agent_sdk` imports remain in core/web as a
documented carve-out — each degrades to a typed `unavailable` envelope or
a non-SDK fallback when the SDK is absent, and none constructs SDK types:

- `src/core/web/routes/cognition.py::_claude_sdk` — chat/transcript module access.
- `src/core/web/routes/presence.py::_latest_claude_chat_uuid` — transcript project-key helper.
- `src/core/web/routes/roles.py::_dispatch_available` — dispatch capability probe.

Moving these behind the seam is deliberately deferred (Rule 22 — no
speculation): it pays only when a second adapter ships a chat runtime.

## Anti-recurrence

`tests/test_session_options_parity.py` asserts each profile's
`mcp_servers` + deny floor + allow pattern; a guard prevents any new
`ClaudeAgentOptions(` construction site outside the builder.

## See also

- [src/adapters/claude/sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py) — the builder + dispatcher.
- [docs/adapters/claude-sdk.md](claude-sdk.md) — the full SDK contract.
