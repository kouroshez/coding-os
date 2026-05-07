---
description: Meta-project engineering rule — applies when editing core/, cli/, adapters/, or hook scripts in coding-os itself.
globs: "core/**/*.py,cli/**/*.py,adapters/**/*.py,core/hooks/*.sh,core/hooks/_helpers/*.py,core/scripts/*.sh"
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

### `core/thinking_os/**`
- MCP tools must use `@safe_tool` and return `ok(data) / fail(category, message)` (Rule 13).
- Schema migrations are append-only — new tables go to `vN+1`, never edit past migrations (Rule 9).
- One-line docstring on `@mcp.tool` functions only (Rule 12). No internal-helper docstrings.
- Verification: `uv run --extra rag pytest core/thinking_os/tests/ -q` + `python core/thinking_os/server.py --test`.

### `core/graph_os/**`
- Backends (`kuzu`, `sqlite`) must remain interchangeable — never leak SQL/Cypher into tool layer.
- Extractors are idempotent on `uid` and short-circuit via `file_index_state` content hash.
- Verification: `uv run --extra graph_os pytest core/graph_os/tests/ -q`.

### `core/hooks/**`
- Every new hook script:
  - sources `cos-env.sh` (Rule 3),
  - is registered ONCE in `core/hooks/registry.yaml` (the SSOT),
  - has its `event/matcher` declared in the registry,
  - never hardcodes `.claude/` — uses `$COS_AGENT_DIR` / `$COS_STATE_DIR` (Rule 1).
- After registry edit: `make regen-adapter-templates` then `make dogfood`.
- Verification: `make verify-hooks`.

### `cli/**`
- No hardcoded stack/adapter literals (Rule 11). Data-driven via
  `templates/<id>/stack.yaml` and `adapters/<id>/adapter.yaml`.
- Test invariants: `uv run pytest tests/test_no_hardcoded_anthropic.py tests/test_no_hardcoded_stacks.py -q`.

### `adapters/<id>/**`
- Adapter parity is bounded by the agent runtime's actual hook
  capabilities — declare them in `adapters/<id>/adapter.yaml::hook_capabilities`.
- Never import an adapter SDK from `core/**` (P8 Adapter-SDK autonomy).
- After adapter edit: `bash adapters/<id>/install.sh`.

### `templates/<id>/**`
- Conform to `core/schemas/stack.schema.json`.
- Re-run `make regen-rules` after edits to `dimensions:` or
  `skill_enforcement:` so `core/rules/{dimension-registry,skill-enforcement}.md` stay fresh.

## Test discipline

Use the matrix-targeted command for the layer you changed (see
AGENTS.md § Verification Matrix). Never run `pytest tests/ -q`
mid-task — that's a 6-minute full-sweep reserved for pre-merge.

## Anti-patterns

- Hand-editing `core/rules/dimension-registry.md` or
  `core/rules/skill-enforcement.md` — these are regen targets, not source.
- Running `cos init` inside the meta-repo — would scaffold a duplicate.
- Adding a hook with a unique-suffix name when an existing hook already
  covers the case — prefer extending the existing hook.
