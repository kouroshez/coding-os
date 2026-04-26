<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-24 -->
# Adapter Parity — Claude vs Codex Coverage

Purpose: Concrete answer to "is Codex in sync with Claude?" — which hooks fire on which runtime, why some don't, and the single command to keep them aligned.

Read when: Codex behavior differs from Claude · evaluating whether a new hook will work for Codex users · auditing adapter coverage before a release.

## TL;DR

- **All 45 core hook scripts are symlinked into BOTH** `.claude/hooks/` AND `.codex/hooks/`. No file is missing. (36 pre-Phase-L hooks + 6 Phase L hooks + 3 dispatcher scripts.)
- **Only Claude wires most of them as events** (≈39). Codex wires ≈12. The remaining gap is architectural — Codex's runtime supports fewer event/matcher combinations than Claude's.
- **Installed Codex hook commands are absolute paths.** Relative `.codex/hooks/...` commands break when Codex starts in a nested cwd instead of the project root.
- **One command to sync:** `make sync`. Runs `regen-adapter-templates` + `dogfood-full` — re-links core, stack, rule, command, skill trees for both adapters and regenerates settings files.

## Parity matrix (as of 2026-04-18)

The renderer at [cli/hook_renderer.py](../../cli/hook_renderer.py) reads [core/hooks/registry.yaml](../../core/hooks/registry.yaml) and **filters every (event, matcher) pair** against each adapter's capabilities declared in [adapters/<id>/adapter.yaml](../../adapters/claude/adapter.yaml). A pair the runtime cannot trigger is skipped silently.

Run the live audit yourself:

```bash
uv run python - <<'PY'
import json, yaml
from pathlib import Path
REPO = Path(".")
reg = yaml.safe_load((REPO/"core/hooks/registry.yaml").read_text())
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
| `warn-mcp-down` | SessionStart | startup | ✓ | ✓ | both |
| `warn-mcp-down` | SessionStart | `compact\|resume` | ✓ | `resume` | renderer narrows to the Codex-supported subset |
| `session-end` | Stop | `` | ✓ | ✓ | both |
| `check-capture-worked` | Stop | `` | ✓ | ✓ | both |

**Totals:** Claude fires 33/34 registered event pairs. Codex fires 11/34.

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

`adapters/codex/install.sh` now enables that flag idempotently in the project's `.codex/config.toml` so Codex hooks and MCP stay repo-scoped by default.

Claude's runtime additionally emits:

- `PreToolUse`/`PostToolUse` for `Write|Edit` and `Skill`.
- `SessionStart` with `compact|resume` matchers.

Every Write/Edit-gated hook we ship is silently dropped for Codex. This is documented at install time:

```
NOTE: Codex PreToolUse/PostToolUse only support the Bash tool.
      Write/Edit-triggered enforcement (doc-anchor, migration-conflict,
      hardcoded-literals) is Claude-only until Codex adds those events.
```

**Implication for Codex users:** the deterministic "agent cannot write without skill X" guarantee that Claude gets via `enforce-skill.sh` is not enforceable. Agents using Codex must rely on prompt-level discipline + the rule files shipped in `.codex/rules/`. What we can enforce reliably on Codex today is the Bash path plus session-start / stop observability.

## What this session changed for each adapter

| Change (this session) | Scope | Claude gets | Codex gets |
|---|---|---|---|
| `cos_log_hook` now emits `agent=X session=Y task=Z` | `core/hooks/cos-env.sh` | ✓ (all wired hooks) | ✓ (all wired hooks) |
| `COS_AGENT` env detection + `.coding-os/.agent` marker | `core/hooks/cos-env.sh` + both `install.sh` | ✓ | ✓ |
| `cos hooks-log --agent/--session/--task/--hook` filters | `cli/main.py` | ✓ (CLI is shared) | ✓ |
| `core/skills/backend-fundamentals/SKILL.md` | skill → adapter symlink | ✓ | ✓ (after `make sync`) |
| `core/skills/frontend-fundamentals/SKILL.md` | skill → adapter symlink | ✓ | ✓ (after `make sync`) |
| `depends_on` frontmatter on stack skills | `templates/<stack>/skills/*/SKILL.md` | ✓ | ✓ (after `make sync`) |
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
1. `make regen-adapter-templates` → re-renders `adapters/claude/settings.template.json` + `adapters/codex/hooks.template.json` from `core/hooks/registry.yaml` (filtered by each adapter's capabilities).
2. `bash adapters/claude/install.sh` → symlinks latest `core/{hooks,rules,skills,commands}/` + links stack skills from `installed-manifest.json` + regenerates `.claude/settings.json` from the template.
3. `bash adapters/codex/install.sh` → same for `.codex/`.

**Rule:** after any edit in `core/**`, `templates/<stack>/skills/**`, or `adapters/*/adapter.yaml`, run `make sync`. Then reload your agent runtime (Claude Code or Codex CLI) to pick up the refreshed config.

The `remind-dogfood.sh` hook fires on edits inside `core/**` to remind you, but **only for Claude** (Codex has no Write/Edit event — you need to remember on Codex).

## FAQ

**Q: Can I see exactly which hooks fire for my agent right now?**
A: `cos hooks-list --agent claude` or `cos hooks-list --agent codex` — reads the registry + capability matrix and prints what's wired.

**Q: I added a new `.sh` hook in `core/hooks/` but it doesn't fire on Codex.**
A: Check its event/matcher in `registry.yaml`. If it uses `Write|Edit`, it's claude-only by Codex design.

**Q: Why is `enforce-skill.sh` the "loud" hook?**
A: Because it's the one that BLOCKS the agent most often on Claude. On Codex, it's silently skipped — Codex users don't see the block, so they must self-discipline.

**Q: Skills aren't appearing in `.codex/skills/` but are in `.claude/skills/`.**
A: Until 2026-04-18, `adapters/codex/install.sh` only symlinked `core/skills/`, not `templates/<stack>/skills/`. Fixed as of this session — both `install.sh` files now call `link-stack-skills.sh` based on `installed-manifest.json`.

**Q: I made a change in `core/` — what should I rerun?**
A: `make sync`. One command, both adapters, all assets.

**Q: My Codex hooks work from repo root but fail from a subdirectory.**
A: That was caused by relative commands in `.codex/hooks.json`. The installer now writes absolute hook paths so nested cwd sessions still find the dispatcher scripts.

## `adapter.yaml::presence` — Hub board contract

Optional block on each adapter manifest (validated by [core/schemas/adapter.schema.json](../../core/schemas/adapter.schema.json)):

- **`signal`:** today only `hook_timestamps` — session JSON is updated by [core/hooks/agent-presence.sh](../../core/hooks/agent-presence.sh) on lifecycle hooks.
- **`presence_events`:** documentation list of which events refresh presence for this runtime (mirrors `hook_capabilities` + dispatchers; not interpreted by Python logic beyond the Hub manifest reader).
- **`hub_glyph` / `hub_color`:** pill metadata for `GET /api/board/list` → `agent_manifest` ([core/board_os/hub_adapter_manifest.py](../../core/board_os/hub_adapter_manifest.py)).

## Claude adapter — curriculum alignment + Agent SDK (P8)

- **Anthropic “Certified Architect — Foundations” instructor guide** (internal copy: [instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md](../code-os-core-docs/instructor_Claude+Certified+Architect+–+Foundations+Certification+Exam+Guide.md)) frames Domain 1 orchestration, **Task 1.5** (hooks for deterministic enforcement vs prompt-only), MCP (Domain 2), and session lifecycle (**Task 1.7**). Use it as a **design checklist** when extending `adapters/claude/` hooks or documentation — not as exam content copied into `core/`.
- **Official Claude Agent SDK:** any programmatic SDK usage stays under `adapters/claude/` (e.g. [sdk_dispatcher.py](../../adapters/claude/sdk_dispatcher.py)). **Rule P8** in `AGENTS.md` — never import an adapter SDK from `core/**`; the kernel exposes MCP tools (`cos_*`) and hook contracts only.

## References

- [core/hooks/registry.yaml](../../core/hooks/registry.yaml) — SSOT for hook registrations
- [adapters/claude/adapter.yaml](../../adapters/claude/adapter.yaml) + [adapters/codex/adapter.yaml](../../adapters/codex/adapter.yaml) — capability declarations
- [cli/hook_renderer.py](../../cli/hook_renderer.py) — the filter
- [docs/engineering/hooks-reference.md](hooks-reference.md) — per-hook catalog
- Codex CLI hook spec: <https://developers.openai.com/codex/hooks>
