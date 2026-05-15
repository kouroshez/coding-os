# Skill Loading Enforcement

> **This file was the legacy hand-edited skill-enforcement table** with hardcoded per-project skills.
> **It is no longer the source of truth.** Skill enforcement is now generated
> from `src/templates/<stack>/stack.yaml::skill_enforcement` by `src/scripts/regen_rules.py`.
> Generated output: [src/core/rules/skill-enforcement.md](../../core/rules/skill-enforcement.md).
>
> To change skill routing for a stack: edit that stack's `stack.yaml` and run
> `make regen-rules`.
>
> This stub is retained because `src/templates/_base/skill-enforcement.template.md`
> is referenced by `src/cli/_data_types.py::SkillEnforcementRow`; emptying the
> file would break the import path. It deliberately contains no enforcement
> rules — they live in the regenerated artifact.
