---
description: Meta-project engineering rule — applies when editing core/, cli/, adapters/, or hook scripts in coding-os itself.
globs: "src/core/**/*.py,src/cli/**/*.py,src/adapters/**/*.py,src/core/hooks/*.sh,src/core/hooks/_helpers/*.py,src/core/scripts/*.sh"
alwaysApply: false
---

# Meta-Engineering Rule (coding-os DNA)

This rule fires when editing files inside the meta-repo's three core
layers (DNA → mRNA → phenotype): `core/`, `cli/`, `adapters/`. It
exists to close the dogfood gap — every principle the meta-repo
enforces on consumer projects must also enforce on itself.

## Mandatory pre-edit moves

1. **Graph context first.** Before any non-trivial edit:
   - `cos_graph_context(file_or_uid, depth=1)` — surrounding subgraph.
   - `cos_graph_references(uid)` — who depends on the symbol.
   - For a rename: `cos_graph_rename_plan(uid, new_name)` (mandatory).
   - For a refactor: `cos_graph_impact(uid, depth=3)`.
2. **Skill load.** `Skill graph-explorer` (primary) + `Skill clean-code`.
   COMPLICATED+ also loads `Skill thinking_os`.
3. **Doc anchor.** Every code edit must trace to a documented spec —
   the `enforce-doc-anchor.sh` hook blocks edits that don't.
4. **Task marker.** Governance / hook-registry / rule-SSOT edits
   require the `.task-current` marker to name a `governance` /
   `docs-update` / `template-update` task (block-protected-files.sh).

## Layer-by-layer rules

### `src/core/thinking_os/**`
- MCP tools must use `@safe_tool` and return `ok(data) / fail(category, message)` (Rule 13).
- Schema migrations are append-only — new tables go to `vN+1`, never edit past migrations (Rule 9).
- One-line docstring on `@mcp.tool` functions only (Rule 12). No internal-helper docstrings.
- Verification: `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + `python src/core/thinking_os/server.py --test`.

### `src/core/graph_os/**`
- Tool layer stays backend-agnostic — never leak raw SQL into the `cos_graph_*` callers. Single backend today (SQLite); the abstraction stays so a future store can plug in.
- Extractors are idempotent on `uid` and short-circuit via `file_index_state` content hash.
- Verification: `uv run --extra graph_os pytest src/core/graph_os/tests/ -q`.

### `src/core/hooks/**`
- Every new hook script:
  - sources `cos-env.sh` (Rule 3),
  - is registered ONCE in `src/core/hooks/registry.yaml` (the SSOT),
  - has its `event/matcher` declared in the registry,
  - never hardcodes `.claude/` — uses `$COS_AGENT_DIR` / `$COS_STATE_DIR` (Rule 1).
- After registry edit: `make regen-adapter-templates` then `make dogfood`.
- Verification: `make verify-hooks`.

### `src/cli/**`
- No hardcoded stack/adapter literals (Rule 11). Data-driven via
  `src/templates/<id>/stack.yaml` and `src/adapters/<id>/adapter.yaml`.
- Test invariants: `uv run pytest tests/test_no_hardcoded_anthropic.py tests/test_no_hardcoded_stacks.py -q`.

### `src/adapters/<id>/**`
- Adapter parity is bounded by the agent runtime's actual hook
  capabilities — declare them in `src/adapters/<id>/adapter.yaml::hook_capabilities`.
- Never import an adapter SDK from `src/core/**` (P8 Adapter-SDK autonomy).
- After adapter edit: `bash src/adapters/<id>/install.sh`.

### `src/templates/<id>/**`
- Conform to `src/core/schemas/stack.schema.json`.
- Re-run `make regen-rules` after edits to `dimensions:` or
  `skill_enforcement:` so `src/core/rules/{dimension-registry,skill-enforcement}.md` stay fresh.

## Test discipline

Use the matrix-targeted command for the layer you changed (see
AGENTS.md § Verification Matrix). Never run `pytest tests/ -q`
mid-task — that's a 6-minute full-sweep reserved for pre-merge.

## Anti-patterns

- Hand-editing `src/core/rules/dimension-registry.md` or
  `src/core/rules/skill-enforcement.md` — these are regen targets, not source.
- Running `cos init` inside the meta-repo — would scaffold a duplicate.
- Adding a hook with a unique-suffix name when an existing hook already
  covers the case — prefer extending the existing hook.
