---
name: meta-engineering
description: Use when authoring inside coding-os itself — core/, cli/, adapters/, templates/, or src/core/hooks/. Enforces three-layer mental model (DNA → mRNA → phenotype), graph-first edit discipline, regen pipelines, dogfood verification, and the contract that meta-repo changes propagate to every consumer project. Pairs with graph-explorer (always primary), clean-code, and thinking_os.
last_reviewed: "2026-05-11"

---

# meta-engineering

Purpose: Internalise that **every line of code in this repo eventually
ships to N consumer projects** and act accordingly. Without this skill,
agents treat meta-repo files like a normal app — they grep, they edit,
they break consumers.

Read when: editing `src/core/**/*.py`, `src/cli/**/*.py`, `src/adapters/**/*.py`,
`src/core/hooks/*.sh`, `src/core/hooks/_helpers/*.py`, `src/templates/**/stack.yaml`,
or `src/core/hooks/registry.yaml`.

Skip when: editing `docs/`, `tests/`, or `.coding-os/` runtime state.

## The DNA → mRNA → phenotype contract

```
core/             ── DNA          ─ agent + stack agnostic
src/adapters/<id>/    ── mRNA         ─ per-agent translation
src/templates/<id>/   ── phenotype    ─ per-stack overlay
            ↓ cli/  (factory)
consumer project  ── organism     ─ Django+Claude, Next+Codex, …
```

**Before any edit, ask:** which layer does this belong in? Mis-layering
is the most common meta-repo bug. If unsure, default to **lower** layer
(more reuse) and split when a single agent or stack genuinely diverges.

## Mandatory pre-edit moves (order matters)

1. **Graph context first** — non-negotiable for `src/core/**/*.py`,
   `src/cli/**/*.py`, `src/adapters/**/*.py`:
   - `cos_graph_context(file_or_uid, depth=1)` — what's connected.
   - `cos_graph_references(uid)` — who depends on the symbol.
   - For a rename: `cos_graph_rename_plan(uid, new_name)` BEFORE first Edit.
   - For a refactor: `cos_graph_impact(uid, depth=3)`.
   The `enforce-graph-context.sh` hook records the marker for you.

2. **Skill stack** — load `Skill graph-explorer` (primary), then
   `Skill clean-code`. COMPLICATED+ adds `Skill thinking_os`.

3. **Doc anchor** — every code edit must trace to a documented spec
   (PRD / playbook / engineering rule). The `enforce-doc-anchor.sh`
   hook BLOCKS edits without a `.doc-anchor` marker.

4. **Task marker** — governance / hook-registry / rule-SSOT edits
   require `.task-current` to name a `governance|docs-update|template-update`
   task. `block-protected-files.sh` enforces.

5. **Complexity Gate** — record before any `.py` edit:
   `bash src/core/hooks/write-state.sh .coding-os/<agent>/.thinking_os-gate "COMPLICATED 3"`.

## Layer-specific rules

### `src/core/thinking_os/**`
- All MCP tools wrapped with `@safe_tool` — return `ok(data) / fail(category, message)` (Rule 13).
- One-line docstring on `@mcp.tool` only (Rule 12). Internal helpers: no docstrings.
- Schema migrations append-only — new tables go to `vN+1`, never edit past (Rule 9).
- Verify: `uv run --extra rag pytest src/core/thinking_os/tests/ -q && python src/core/thinking_os/server.py --test`.

### `src/core/graph_os/**`
- Tool layer stays backend-agnostic — never leak raw SQL into the `cos_graph_*` callers. Single backend today (SQLite); the abstraction stays so a future store can plug in.
- Extractors idempotent on `uid`, short-circuit via `file_index_state` content hash.
- Verify: `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`.

### `src/core/hooks/**`
- Every new hook:
  - sources `cos-env.sh` (Rule 3),
  - registered ONCE in `src/core/hooks/registry.yaml` (SSOT),
  - declares `event/matcher` in registry,
  - never hardcodes `.claude/` — use `$COS_AGENT_DIR` / `$COS_STATE_DIR` (Rule 1, P2).
- After registry edit: `make regen-adapter-templates` then `bash src/adapters/<id>/install.sh`.
- Verify: `make verify-hooks` (passes shellcheck warning level + bash -n).

### `src/cli/**`
- No hardcoded stack/adapter literals (Rule 11). Data-driven via
  `src/templates/<id>/stack.yaml` and `src/adapters/<id>/adapter.yaml`.
- Test invariants: `uv run pytest tests/test_no_hardcoded_anthropic.py tests/test_no_hardcoded_stacks.py tests/test_cli.py -q`.

### `src/adapters/<id>/**`
- Adapter parity is bounded by the agent runtime's actual hook
  capabilities — declare them in `adapter.yaml::hook_capabilities`.
- Never import an adapter SDK from `src/core/**` (P8).
- After edit: `bash src/adapters/<id>/install.sh` (or `make dogfood-full`).

### `src/templates/<id>/**`
- Conform to `src/core/schemas/stack.schema.json`.
- After edits to `dimensions:` or `skill_enforcement:`: `make regen-rules`.
- Hand-editing `src/core/rules/dimension-registry.md` or `skill-enforcement.md` directly is forbidden — both are regen targets.

### `src/core/web/**`
- Routes prefix `/api/` for HTTP, `/api/stream/` for SSE.
- Every endpoint returns the same MCP envelope shape (`{ok, data|error}`).
- UI in `src/core/web/ui/` — Vite + React 18 + Sigma.js.

## Anti-patterns

- **Bypassing graph layer** by loading `clean-code` only and editing
  blindly — `enforce-skill.sh` BLOCKS this for `src/core/**/*.py`.
- **Adding a hook script without registry entry** — won't be rendered to any adapter.
- **Hand-editing regenerated rules** — drift from source-of-truth template.
- **Hardcoding `.claude/` in src/core/** — use `$COS_AGENT_DIR`. Audit
  hook `block-hardcoded-literals.sh` catches most cases.
- **Running `cos init` inside meta-repo** — would scaffold a duplicate.
- **Rename without `cos_graph_rename_plan`** — `enforce-rename-plan.sh` warns; expect missed call-sites.

## Test discipline (matrix-targeted)

Use only the verification matrix command for the layer you changed
(AGENTS.md § Verification Matrix). Never `pytest tests/ -q` mid-task —
that runs ~2K tests in ~6 minutes (full sweep is pre-merge only).

## Propagation matrix

| Edit | Reaches consumer via | Latency |
|---|---|---|
| `src/core/hooks/*.sh` | Live symlink — no rebuild | Immediate |
| `src/core/thinking_os/**` | MCP server restart | One restart |
| `src/core/rules/*.md`, `src/core/skills/**` | Live symlink + `cos update` | `cos update` |
| `src/adapters/<agent>/**` | `bash src/adapters/<agent>/install.sh` | Manual |
| `src/templates/<stack>/**` | `cos update` + `make manifest-regen` | Manual |
| `src/cli/**` | new `cos` invocations pick up changes | Immediate (after `uv tool install --editable .`) |

## When to escalate

Stop and surface to user when:
- A `core/` change breaks backward compatibility.
- An adapter change affects another adapter.
- An MCP tool signature changes without a migration plan.
- You discover a stack-specific assumption inside `core/`.

## See also

- [docs/architecture/meta-project.md](../../../docs/architecture/meta-project.md) — full meta-project architecture.
- [docs/governance/critical-rules.md](../../../docs/governance/critical-rules.md) — all 21 critical rules.
- [docs/engineering/graph-hallucination-cures.md](../../../docs/engineering/graph-hallucination-cures.md) — why and when to call `cos_graph_*`.
- [src/core/skills/graph-explorer/SKILL.md](../../../core/skills/graph-explorer/SKILL.md) — graph decision ladder.
