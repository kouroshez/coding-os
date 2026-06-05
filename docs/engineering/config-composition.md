<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-05 -->

# Config Composition — per-stack `.coding-os/` merge at `cos init`

> P: SSOT for how `cos init` composes the consumer's `.coding-os/` cognitive
> configs (`rag-config.yaml`, `scrumban-config.yaml`, `domain-config.json`) from
> the base defaults + every installed stack's overlay, data-driven and
> multi-stack-correct.
> R: Editing `src/cli/config_composer.py`, the init scaffold flow, or any stack's
> `.coding-os/*` config; debugging why a stack's board/RAG settings are missing.
> S: Authoring CODE-lane boundaries — that's [scaffold-boundary-contract.md](../governance/scaffold-boundary-contract.md).
> N: [scaffold-boundary-contract.md](../governance/scaffold-boundary-contract.md), [meta-project.md](../architecture/meta-project.md), [docs-system.md](../governance/docs-system.md)

> Nav: [Parent Index](00-index.md)

## Why this exists — the bug it replaces

`_overlay_scaffold` copies `_base/scaffold/` first, then each stack's
`scaffold/`, and is **first-writer-wins** (`if dest.exists(): continue`, for
idempotency vs the user's own files). For files that exist at the SAME path in
both base and a stack — the three `.coding-os/*` configs — base always won and
the stack's version was **silently dropped**. A `cos init --template nextjs`
project shipped the BASE Scrumban board (backend swimlanes), not the nextjs one;
react-native's `rag-config.yaml` override never applied. Multi-stack projects
(e.g. nextjs + go-fiber) could never get both stacks' swimlanes.

The fix: the three configs are EXCLUDED from the overlay and instead **composed**
by `src/cli/config_composer.py` — base defaults deep-merged with every installed
stack's overlay, in install order, with per-file merge semantics.

## Composition contract

- **Source of truth:** `_base/scaffold/.coding-os/<file>` provides stack-agnostic
  defaults; each `<stack>/scaffold/.coding-os/<file>` ships only its DELTA.
- **Data-driven:** the composer iterates the installed `templates` list (Rule 11
  — no hardcoded stack literals) and reads each stack's overlay from
  `src/templates/<stack>/scaffold/.coding-os/`.
- **Idempotent:** the composed file is written only when the target does not
  already exist — a re-run of `init`/`update`, or a user-edited config, is never
  clobbered (same contract as `_overlay_scaffold`).
- **Order:** base first, then stacks in the order they appear in `templates`;
  on a key collision the LATER source wins (stack overrides base; a later stack
  overrides an earlier one).

## Per-file merge semantics

The merge is spec-driven — one strategy table per file in `config_composer.py`.

| File | Key | Strategy |
|---|---|---|
| `rag-config.yaml` | `sources` | union by `path` (later wins on collision → tune priority/chunk_size; new paths appended) |
| | `exclude` | list union (order-preserving, deduped) |
| | `graph.enforce_context_on` | list union |
| `scrumban-config.yaml` | `swimlanes` | union by `id` (stack lane overrides a base lane of the same id; new lanes appended) |
| | `wip_limits` | dict override (stack keys override base keys) |
| | `workflow_policy` | dict override |
| | `label_families` | union by `name` |
| `domain-config.json` | `refs_by_tag` | per-tag list union |
| | `domain_map`, `playbook_map` | dict merge (stack adds/overrides keys) |
| | `default_refs`, `default_domain`, `default_playbook` | scalar/list override |

Strategy vocabulary (spec values): `union_by:<key>` · `union_list` · `dict_merge`
(recursive, scalar-override) · `dict_union_lists` (per-key list union) ·
`override` (later wins wholesale).

## Consumers (verify field names against these — Rule: producer is SSOT)

| File | Consumer | Reads |
|---|---|---|
| `scrumban-config.yaml` | `src/core/board_os/config.py::parse_config` | `swimlanes[].{id,label,color,accent,description}`, `wip_limits`, `workflow_policy`, `label_families[].{name,color,emoji}` |
| `rag-config.yaml` | `src/core/thinking_os/doc_indexer.py::load_rag_config` / `walk_sources` | `sources[].{path,type,chunk_size,chunk_overlap,priority,exclude}`, `exclude` |
| `domain-config.json` | Bash scripts + skills (config chain, Rule 4) | `refs_by_tag`, `domain_map`, `playbook_map`, `default_*` |

## Anti-patterns

- Re-adding a `.coding-os/*` config to the overlay copy path — it will silently
  shadow the composed output (first-writer-wins).
- A stack shipping a FULL duplicate of base instead of a delta — it drifts (the
  pre-fix react-native `rag-config.yaml` did exactly this). Ship only additions.
- Hardcoding the stack list in the composer — iterate `templates` (Rule 11).
- Merging a board (`swimlanes`) as wholesale override — a multi-stack project
  then loses one stack's lanes. Union by `id`.
