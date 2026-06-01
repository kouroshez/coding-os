<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-24 -->
# Adapter Parity — Claude vs Codex Coverage

Purpose: Concrete answer to "is Codex in sync with Claude?" — which hooks fire on which runtime, why some don't, and the single command to keep them aligned.

Read when: Codex behavior differs from Claude · evaluating whether a new hook will work for Codex users · auditing adapter coverage before a release.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## TL;DR

- **All 45 core hook scripts are symlinked into BOTH** `.claude/hooks/` AND `.codex/hooks/`. No file is missing. (36 baseline hooks + 6 Scrumban hooks + 3 dispatcher scripts.)
- **Only Claude wires most of them as events** (≈39). Codex wires ≈12. The remaining gap is architectural — Codex's runtime supports fewer event/matcher combinations than Claude's.
- **Installed Codex hook commands are absolute paths.** Relative `.codex/hooks/...` commands break when Codex starts in a nested cwd instead of the project root.
- **One command to sync:** `make sync`. Runs `regen-adapter-templates` + `dogfood-full` — re-links core, stack, rule, command, skill trees for both adapters and regenerates settings files.

## Parity matrix (as of 2026-04-18)

The renderer at [src/cli/hook_renderer.py](../../src/cli/hook_renderer.py) reads [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) and **filters every (event, matcher) pair** against each adapter's capabilities declared in [src/adapters/<id>/adapter.yaml](../../src/adapters/claude/adapter.yaml). A pair the runtime cannot trigger is skipped silently.

Run the live audit yourself:

```bash
uv run python - <<'PY'
import json, yaml
from pathlib import Path
REPO = Path(".")
reg = yaml.safe_load((REPO/"src/core/hooks/registry.yaml").read_text())
claude = json.loads((REPO/".claude/settings.json").read_text())["hooks"]
codex  = json.loads((REPO/".codex/hooks.json").read_text()).get("hooks", {})
# …same comparison logic as docs/engineering/adapter-parity.md
PY
```

### Hook coverage summary

| Hook | Event | Matcher | Claude | Codex | Why the gap |
|---|---|---|---|---|---|
| `block-secrets` | PreToolUse | Bash | ✓ | ✓ | both runtimes support Bash |
| `block-secrets` | PreToolUse | `Write\|Edit` | ✓ | — | Codex doesn't emit Write/Edit events |
| `block-dangerous-commands` | PreToolUse | Bash | ✓ | ✓ | both |
| `block-uv-heredoc` | PreToolUse | Bash | ✓ | ✓ | both |
| `block-bad-patterns` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `block-protected-files` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `block-migration-conflict` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `block-hardcoded-literals` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-verify` | PreToolUse | Bash | ✓ | ✓ | both |
| `enforce-template` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-doc-anchor` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-memory-check` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-skill` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-task-start` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `enforce-zoom` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `thinking_os-gate` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `warn-template-drift` | PreToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `capture-observation` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `verify-changed-file` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `check-agents-md-size` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `check-agents-md-refs` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `doc-sync-reminder` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `regen-reminder` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `test-first-reminder` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `remind-dogfood` | PostToolUse | `Write\|Edit` | ✓ | — | Codex Write/Edit gap |
| `remind-learn-validate` | PostToolUse | Bash | ✓ | ✓ | both (Codex runs via `codex-posttool-dispatch.sh` so `agent-presence.sh` still fires after Bash tools) |
| `track-skill` | PostToolUse | Skill | ✓ | — | Codex has no Skill matcher |
| `session-context` | SessionStart | startup | ✓ | ✓ | both |
| `session-context` | SessionStart | `compact\|resume` | ✓ | `resume` | renderer narrows to the Codex-supported subset |
| `session-context` | UserPromptSubmit | `` | — | ✓ | Claude's dedicated one is SessionStart; Codex uses UserPromptSubmit |
| `classify-task-mode` | UserPromptSubmit | `` | ✓ | ✓ | both (Codex via `codex-userpromptsubmit-dispatch.sh`) |
| `nudge-thinking-os` | UserPromptSubmit | `` | ✓ | ✓ | both (Codex via dispatcher) |
| `nudge-graph-os` | UserPromptSubmit | `` | ✓ | ✓ | both (Codex via dispatcher) |
| `nudge-docs-first` | UserPromptSubmit | `` | ✓ | ✓ | both (Codex via dispatcher) — recommends `cos_doc_search` before code-edit |
| `warn-mcp-down` | SessionStart | startup | ✓ | ✓ | both |
| `warn-mcp-down` | SessionStart | `compact\|resume` | ✓ | `resume` | renderer narrows to the Codex-supported subset |
| `session-end` | Stop | `` | ✓ | ✓ | both |
| `check-capture-worked` | Stop | `` | ✓ | ✓ | both |

**Totals:** Claude fires 37/38 registered event pairs. Codex fires 15/38 (UserPromptSubmit cognition nudges delivered via `codex-userpromptsubmit-dispatch.sh`).

## Why Codex fires fewer events (this is by design)

Codex's hook runtime (per the Codex CLI spec at <https://developers.openai.com/codex/hooks>) only raises:

- `PreToolUse` / `PostToolUse` for the **Bash** tool (no Write/Edit distinction — Codex writes files without a dedicated event).
- `SessionStart` with `startup` and `resume` matchers (still no Claude-style `compact` source).
- `UserPromptSubmit`, `Stop` (both empty-matcher).

Two Codex wire-format details matter in practice:

- `UserPromptSubmit` payloads carry `prompt`, not `source`. Hooks shared with `SessionStart` must not default that event to `startup`, or they'll rotate `session-id` / clear volatile state on every prompt submit.
- `Stop` expects JSON on stdout when exiting 0. A dispatcher that succeeds silently should emit `{}` rather than plain text or an empty human banner.

As of **April 18, 2026**, the Codex docs also require the feature flag below for hooks to fire at all:

```toml
[features]
codex_hooks = true
```

`src/adapters/codex/install.sh` now enables that flag idempotently in the project's `.codex/config.toml` so Codex hooks and MCP stay repo-scoped by default.

Claude's runtime additionally emits:

- `PreToolUse`/`PostToolUse` for `Write|Edit` and `Skill`.
- `SessionStart` with `compact|resume` matchers.

Every Write/Edit-gated hook we ship is silently dropped for Codex. This is documented at install time:

```
NOTE: Codex PreToolUse/PostToolUse only support the Bash tool.
      Write/Edit-triggered enforcement (doc-anchor, migration-conflict,
      hardcoded-literals) is Claude-only until Codex adds those events.
```

### Intent enforcement layer (TASK-004) — Claude / Cursor only

The 8 hooks introduced by the intent enforcement layer (TASK-004 phase P
— intent-primer, detect-exhaustive-intent, enforce-audit-artifact,
inject-resume-prompt, verify-completion-claim, prevent-premature-done,
enforce-count-grounding, enforce-subagent-delegation) all rely on at
least one Codex-incapable matcher: `SessionStart compact|resume`,
`PreToolUse Write|Edit`, or `Stop` with rich envelopes.  The renderer
emits **0/8** for the Codex adapter and **10/10 matcher pairs for
Claude** (full coverage); Cursor renders the single SessionStart
event-only entry it supports.

Codex CLI users therefore receive **no intent-enforcement coverage**
under exhaustive-scope prompts — the agent sees no SessionStart prime,
no detect-exhaustive-intent classifier, no Stop guardian.  The
contract is enforced live only on Claude / Cursor sessions.  When
OpenAI ships `Write|Edit` matchers (and a richer Stop envelope), update
`src/adapters/codex/adapter.yaml::hook_capabilities` and re-run
`make regen-adapter-templates`; no other code changes are needed.

**Implication for Codex users:** the deterministic "agent cannot write without skill X" guarantee that Claude gets via `enforce-skill.sh` is not enforceable. Agents using Codex must rely on prompt-level discipline + the rule files shipped in `.codex/rules/`. What we can enforce reliably on Codex today is the Bash path plus session-start / stop observability.

## What this session changed for each adapter

| Change (this session) | Scope | Claude gets | Codex gets |
|---|---|---|---|
| `cos_log_hook` now emits `agent=X session=Y task=Z` | `src/core/hooks/cos-env.sh` | ✓ (all wired hooks) | ✓ (all wired hooks) |
| `COS_AGENT` env detection + `.coding-os/.agent` marker | `src/core/hooks/cos-env.sh` + both `install.sh` | ✓ | ✓ |
| `cos hooks-log --agent/--session/--task/--hook` filters | `src/cli/main.py` | ✓ (CLI is shared) | ✓ |
| `src/core/skills/backend-fundamentals/SKILL.md` | skill → adapter symlink | ✓ | ✓ (after `make sync`) |
| `src/core/skills/frontend-fundamentals/SKILL.md` | skill → adapter symlink | ✓ | ✓ (after `make sync`) |
| `depends_on` frontmatter on stack skills | `src/templates/<stack>/skills/*/SKILL.md` | ✓ | ✓ (after `make sync`) |
| New hook: `doc-sync-reminder.sh` (enhanced) | PostToolUse Write\|Edit | ✓ | ✗ by design — no Write/Edit on Codex |
| New docs (`docs/engineering/*.md`) | `docs/` tree | N/A — docs are single-project assets, not adapter-specific | N/A |
| `cos-env.sh` task format improvement (TASK-### extraction) | shared logger | ✓ | ✓ |
| `adapter/*/install.sh` now links stack skills from `installed-manifest.json` | both `install.sh` | ✓ (re-run automatic) | ✓ (re-run automatic) |
| `make sync` target | Makefile | N/A | N/A |

**Everything that's adapter-agnostic (logging, CLI, helpers, skill composition)** — BOTH adapters get it. **Everything that requires Write/Edit events** — Claude only, by Codex runtime limits.

## The canonical "sync after changes" command

```bash
make sync
```

Does three things in order:
1. `make regen-adapter-templates` → re-renders `src/adapters/claude/settings.template.json` + `src/adapters/codex/hooks.template.json` from `src/core/hooks/registry.yaml` (filtered by each adapter's capabilities).
2. `bash src/adapters/claude/install.sh` → symlinks latest `src/core/{hooks,rules,skills,commands}/` + links stack skills from `installed-manifest.json` + regenerates `.claude/settings.json` from the template.
3. `bash src/adapters/codex/install.sh` → same for `.codex/`.

**Rule:** after any edit in `src/core/**`, `src/templates/<stack>/skills/**`, or `src/adapters/*/adapter.yaml`, run `make sync`. Then reload your agent runtime (Claude Code or Codex CLI) to pick up the refreshed config.

The `remind-dogfood.sh` hook fires on edits inside `src/core/**` to remind you, but **only for Claude** (Codex has no Write/Edit event — you need to remember on Codex).

## FAQ

**Q: Can I see exactly which hooks fire for my agent right now?**
A: `cos hooks-list --agent claude` or `cos hooks-list --agent codex` — reads the registry + capability matrix and prints what's wired.

**Q: I added a new `.sh` hook in `src/core/hooks/` but it doesn't fire on Codex.**
A: Check its event/matcher in `registry.yaml`. If it uses `Write|Edit`, it's claude-only by Codex design.

**Q: Why is `enforce-skill.sh` the "loud" hook?**
A: Because it's the one that BLOCKS the agent most often on Claude. On Codex, it's silently skipped — Codex users don't see the block, so they must self-discipline.

**Q: Skills aren't appearing in `.codex/skills/` but are in `.claude/skills/`.**
A: Until 2026-04-18, `src/adapters/codex/install.sh` only symlinked `src/core/skills/`, not `src/templates/<stack>/skills/`. Fixed as of this session — both `install.sh` files now call `link-stack-skills.sh` based on `installed-manifest.json`.

**Q: I made a change in `src/core/` — what should I rerun?**
A: `make sync`. One command, both adapters, all assets.

**Q: My Codex hooks work from repo root but fail from a subdirectory.**
A: That was caused by relative commands in `.codex/hooks.json`. The installer now writes absolute hook paths so nested cwd sessions still find the dispatcher scripts.

## `adapter.yaml::presence` — Hub board contract

Optional block on each adapter manifest (validated by [src/core/schemas/adapter.schema.json](../../src/core/schemas/adapter.schema.json)):

- **`signal`:** today only `hook_timestamps` — session JSON is updated by [src/core/hooks/agent-presence.sh](../../src/core/hooks/agent-presence.sh) on lifecycle hooks.
- **`presence_events`:** documentation list of which events refresh presence for this runtime (mirrors `hook_capabilities` + dispatchers; not interpreted by Python logic beyond the Hub manifest reader).
- **`hub_glyph` / `hub_color`:** pill metadata for `GET /api/board/list` → `agent_manifest` ([src/core/board_os/hub_adapter_manifest.py](../../src/core/board_os/hub_adapter_manifest.py)).

## `adapter.yaml::runtime_session_marker` — per-panel identity contract

Each adapter declares how `src/core/hooks/cos-env.sh::_cos_resolve_panel_id` and `cos_panel_upgrade_from_payload` derive the per-panel id from its runtime. The block exists on every adapter manifest:

```yaml
runtime_session_marker:
  stdin_field: session_id      # JSON key the agent's hook payload carries
  env_vars:                    # priority-ordered fallback when stdin missing
    - CLAUDE_CODE_SESSION_ID   # the var Claude Code actually exports to hooks
    - CLAUDE_SESSION_ID        # forward-compat alias (the original wrong guess)
    - ANTHROPIC_SESSION_ID
```

Resolution order (highest first), implemented once in core:

1. `$COS_PANEL_ID` — explicit caller override (tests, manual debug).
2. Stdin `session_id` (or `sessionId`) — set by `cos_panel_upgrade_from_payload` after the hook reads stdin. **Strongest signal**; Claude/Codex/Cursor hook specs all carry it.
3. The adapter's `env_vars` list, probed in declared order. cos-env.sh today probes the union across all adapters (`CLAUDE_CODE_SESSION_ID` · `CLAUDE_SESSION_ID` · `CURSOR_SESSION_ID` · `CURSOR_TRACE_ID` · `CODEX_SESSION_ID` · `GEMINI_SESSION_ID` · `ANTHROPIC_SESSION_ID`) so an env var set by any adapter wins regardless of which adapter currently owns the hook subprocess. **(TASK-054: `CLAUDE_CODE_SESSION_ID` is what Claude Code actually exports — the originally-listed `CLAUDE_SESSION_ID` never matched, so Claude hooks fell to the PPID fallback and scattered state; corrected & verified 2026-06-01.)**
4. PPID-derived hash — last-resort safety net for raw shell tests.

**Adding a new adapter** (e.g. `src/adapters/gemini/`) requires zero code change in `src/core/`: drop a `runtime_session_marker` block into `src/adapters/gemini/adapter.yaml` declaring its env var(s) and stdin field, then the per-panel routing in `cos-env.sh` / `write-state.sh` / `check-state.sh` / `session-context.sh` works for that adapter immediately. The data-drivenness is enforced by Rule 11 — `tests/test_no_hardcoded_anthropic.py` would catch any leak of an adapter-specific session var into `src/core/` or `src/cli/`.

The contract pairs with [docs/engineering/state-files.md § Panel-id resolution](state-files.md#panel-id-resolution--multi-adapter-data-driven) — the canonical multi-panel scenario (P6) doc.

## Claude adapter — curriculum alignment + Agent SDK (P8)

- **Anthropic “Certified Architect — Foundations” instructor guide** (internal copy: [instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md](../code-os-core-docs/instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md)) frames Domain 1 orchestration, **Task 1.5** (hooks for deterministic enforcement vs prompt-only), MCP (Domain 2), and session lifecycle (**Task 1.7**). Use it as a **design checklist** when extending `src/adapters/claude/` hooks or documentation — not as exam content copied into `src/core/`.
- **Official Claude Agent SDK:** any programmatic SDK usage stays under `src/adapters/claude/` (e.g. [sdk_dispatcher.py](../../src/adapters/claude/sdk_dispatcher.py)). **Rule P8** in `AGENTS.md` — never import an adapter SDK from `src/core/**`; the kernel exposes MCP tools (`cos_*`) and hook contracts only.

## References

- [src/core/hooks/registry.yaml](../../src/core/hooks/registry.yaml) — SSOT for hook registrations
- [src/adapters/claude/adapter.yaml](../../src/adapters/claude/adapter.yaml) + [src/adapters/codex/adapter.yaml](../../src/adapters/codex/adapter.yaml) — capability declarations
- [src/cli/hook_renderer.py](../../src/cli/hook_renderer.py) — the filter
- [docs/engineering/hooks-reference.md](hooks-reference.md) — per-hook catalog
- Codex CLI hook spec: <https://developers.openai.com/codex/hooks>
