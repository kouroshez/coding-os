---
description: Meta-project engineering rule — applies when editing core/, cli/, adapters/, or hook scripts in coding-os itself.
globs: "src/core/**/*.py,src/cli/**/*.py,src/adapters/**/*.py,src/core/hooks/*.sh,src/core/hooks/_helpers/*.py,src/core/scripts/*.sh"
alwaysApply: false
---

# Meta-Engineering Rule (coding-os DNA)

Closes the dogfood gap: every principle the meta-repo enforces on consumer projects also enforces on itself. The layer-by-layer detail (thinking_os / graph_os / hooks / cli / adapters / templates) lives in `Skill meta-engineering` — load it for any non-trivial meta-repo edit. Non-negotiables:

1. **Pre-edit:** `cos_graph_context(file, depth=1)` (+ `cos_graph_references` / `_impact` / `_rename_plan` as fits) and `Skill graph-explorer` + `Skill clean-code`; COMPLICATED+ adds `Skill thinking_os`.
2. **Doc anchor** (Rule 0) — every code edit traces to a documented spec; governance edits need a `governance` / `docs-update` task marker (Rule 7).
3. **Regen, never hand-edit:** `dimension-registry.md`, `skill-enforcement.md`, `scaffold_manifest.json`, adapter templates, golden tests → `make regen-rules` / `manifest-regen` / `regen-adapter-templates`.
4. **Adapters:** parity bounded by `adapter.yaml::hook_capabilities`; never import an adapter SDK from `src/core/**` (P8). After adapter edit: `bash src/adapters/<id>/install.sh`.
5. **CLI:** no hardcoded stack/adapter literals (Rule 11) — data-driven from yaml.
6. **Tests:** matrix-targeted command only (AGENTS.md § Verification Matrix); never `pytest tests/` mid-task.
7. **Never** run `cos init` inside the meta-repo; prefer extending an existing hook over adding a near-duplicate.
