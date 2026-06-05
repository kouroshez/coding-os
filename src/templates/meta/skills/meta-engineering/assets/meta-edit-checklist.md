<!-- domain:META | layer:asset | ssot:false | updated:2026-06-04 -->
# Meta-Repo Edit Checklist

Run before editing anything under core/ · cli/ · adapters/ · templates/ · hooks/.

## Before the edit
- [ ] Know the layer + blast radius — `python3 scripts/which_layer.py <path>`.
- [ ] Editing the LOWEST correct layer (more reuse) — not duplicating into a higher one.
- [ ] Graph context loaded (`cos_graph_context`) for `src/core/**`, `src/cli/**`, `src/adapters/**` `.py`.
- [ ] `Skill graph-explorer` + `Skill clean-code` loaded; COMPLICATED+ adds `Skill thinking_os`.
- [ ] Doc anchor recorded (every code edit traces to a spec).
- [ ] Task marker names a governance/docs-update/template-update task for governance/registry/rule-SSOT edits.

## Layer-specific (after the edit)
- [ ] `src/core/hooks/**` → registered in registry.yaml → `make regen-adapter-templates` → `make verify-hooks`.
- [ ] `src/core/thinking_os/**` → `uv run --extra rag pytest src/core/thinking_os/tests/ -q` + server `--test`.
- [ ] `src/templates/**` (dimensions/skill_enforcement) → `make regen-rules`.
- [ ] `src/adapters/<id>/**` → `bash src/adapters/<id>/install.sh`.
- [ ] `src/cli/**` → `uv run pytest tests/test_cli.py tests/test_no_hardcoded_*.py -q`.

## Never
- [ ] Hand-edit a regen target (dimension-registry.md, skill-enforcement.md, golden/, adapter templates).
- [ ] Hardcode `.claude/` in src/core/ — use `$COS_AGENT_DIR`/`$COS_STATE_DIR`.
- [ ] Run `cos init` inside the meta-repo.
- [ ] Full `pytest tests/ -q` mid-task — matrix-targeted only.

## Propagation confirmed
- [ ] Dogfood: `make dogfood` (or `make dogfood-full`) re-rendered + still green.
