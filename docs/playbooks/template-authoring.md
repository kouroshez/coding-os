<!-- domain:META | layer:playbook | ssot:true | updated:2026-05-08 -->
# Playbook — Authoring a Stack Template

> P: Procedure for adding a new stack under `src/templates/<id>/` (e.g. a new framework like django / nextjs / go-fiber) or extending an existing one.
> R: Adding a stack the meta-repo doesn't yet support, or evolving an existing stack's scaffold / skills / dimensions.
> S: Modifying a single project's `<project>/templates/`-derived files — that's a consumer-side concern.
> N: [meta-project.md](../architecture/meta-project.md), [scaffold-boundary-contract.md](../governance/scaffold-boundary-contract.md), [anatomy-contract.md](../governance/anatomy-contract.md), [stack.schema.json](../../src/core/schemas/stack.schema.json)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## The mental model

A stack template is the **phenotype layer**: it overlays one language / framework's conventions on top of the kernel + adapter foundation. `cos init` composes (DNA in `src/core/`) + (mRNA in `src/adapters/<agent>/`) + (phenotype in `src/templates/<stack>/`) → a consumer project. The stack carries everything that is language-specific: skills, scaffold files, dimensions, naming, anatomy.

Three contracts every stack template must satisfy:

1. **`stack.yaml`** is the schema-validated SSOT for the stack — id, label, category, primary skill, dimensions, skill enforcement, substitutions. Validated by `src/core/schemas/stack.schema.json`.
2. **`scaffold/`** is the file tree the consumer gets after `cos init`. Anything here is copied once at project creation; it never re-syncs. Use it for files the consumer is expected to edit.
3. **`skills/<skill_id>/`** ships agent-loadable skill packages — `SKILL.md`, `references/anatomy.md`, optional `src/scripts/`. Lazy-loaded forever; safe to evolve without reinstalling consumers.

## Language layer & composition (TASK-348)

Every stack declares its base **`language`** (`python`, `typescript`, `go`,
…) in `stack.yaml` — required by the schema. The init discovery (CLI prompt
and hub catalog) groups stacks by language so a user can pick **a language
OR a framework**: choosing a bare language selects its plain stack.

- **Plain-language stacks** are named `<language>-plain` (`go-plain`,
  `typescript-plain`), `category: library`, minimal scaffold (a runnable
  module / tsconfig skeleton), no framework skill. `python` predates the
  convention and acts as python's plain stack.
- **`extends: <stack-id>`** (optional) composes a stack on top of another:
  scalars are child-wins, dict fields (`substitutions`) merge parent-first
  then child, list fields concatenate parent + child with order-preserving
  dedup. Cycles and unknown parents fail the load with a WARN (the stack is
  skipped, never a crash). One level of nesting is supported; deeper chains
  resolve recursively but keep them shallow.

## Steps to add a new stack

1. **Pick the id.** Lowercase, kebab-case, no version suffix. `nextjs`, `go-fiber`, `react-native`. Match the framework's most-used display name.
2. **Author `stack.yaml`.** Required fields per [stack.schema.json](../../src/core/schemas/stack.schema.json): `version`, `id`, `label`, `category`, `primary_skill`, `skills`, `substitutions`, `rules`, `dimensions`, `skill_enforcement`. Validate with `python -m jsonschema -i src/templates/<id>/stack.yaml src/core/schemas/stack.schema.json`.
3. **Author `scaffold-boundary.yaml`.** Lists `roots` (where this stack writes), `imports_from` (other roots it may read), `forbids_writing_in` (out-of-bounds paths). Used by the boundary linter.
4. **Author `scaffold/`.** Files written into the consumer at init time — base-level config, skeleton entry points, README sections specific to the stack. Keep this minimal — anything that must stay in sync forever belongs in `src/core/` or in a skill, not in scaffold.
5. **Author the primary skill.** `skills/<primary_skill>/SKILL.md` plus `references/anatomy.md`. Anatomy must satisfy the [anatomy-contract.md](../governance/anatomy-contract.md) shape — boundary, layout map, entity recipes, conventions.
6. **Wire dimensions.** List the stack's distinct work surfaces under `stack.yaml::dimensions`, each with the `read_files` an agent should load before editing. These get aggregated into `src/core/rules/dimension-registry.md` by `make regen-rules`.
7. **Wire skill enforcement.** List the file globs that should auto-load the stack's skills. Aggregated into `src/core/rules/skill-enforcement.md`.
8. **Regenerate manifest.** `make manifest-regen` updates `src/core/scaffold_manifest.json` so `cos init` picks up the new stack.
9. **Run the cross-stack tests.** `uv run pytest tests/test_template_scaffold.py tests/test_adapter_parity.py -q`. Both must be green.

## Stack bundle standard — the factory contract (TASK-361)

A stack is COMPLETE only when every row below exists. `cos stack-lint <id>`
(all stacks: `cos stack-lint`) checks the machine-checkable rows; the CI test
`tests/test_template_scaffold.py::TestStackBundleLint` fails the suite when a
shipped stack violates a hard rule.

| # | Artifact | Path convention | Lint |
|---|---|---|---|
| 1 | Manifest, schema-valid | `src/templates/<id>/stack.yaml` (version, id=dirname, label, category, **language**, **structure.root/tree**) | hard |
| 2 | Verify wiring | `VERIFY_<CATEGORY>_GLOB` substitution for backend/frontend/mobile (the matrix fragment's source); `verify:` per-glob rows are the newer mechanism — their absence is a GAP | hard / soft |
| 3 | Primary skill resolvable | `primary_skill` found under `src/templates/<id>/skills/` or `src/core/skills/` (plain stacks may declare `null`) | hard |
| 4 | Routing surface | non-empty `substitutions.DOMAIN_ROUTES` + `QUICK_ROUTING` | hard |
| 5 | Dimensions | `dimensions:` rows with read_files (plain/library stacks exempt) | soft |
| 6 | Skill enforcement | `skill_enforcement:` globs (plain/library stacks exempt) | soft |
| 7 | Scaffold boundary | `scaffold-boundary.yaml` for code-writing categories | soft |
| 8 | Scrumban delta | `scaffold/.coding-os/scrumban-config.yaml` (board lanes for the stack's work) | soft |
| 9 | Docs | ≥1 playbook/engineering doc under `scaffold/docs/` or routed via `_base` docs | soft |
| 10 | Golden coverage | a `tests/golden/<agent>_<id>` section (capture with `make golden-capture SECTION=…`) | soft |
| 11 | Regen chain run | `make regen-rules` + `make manifest-regen` + `make regen-adapter-templates` after edits (Rule 10) | manual |
| 12 | Adapter capability note | hooks needing non-Bash matchers documented against `adapter.yaml::hook_capabilities` | manual |

Hard rows fail `cos stack-lint` (exit 1) and CI; soft rows are reported as
GAP lines so a stack's completeness is visible without blocking iteration.
Plain-language stacks (`<lang>-plain`) and `category: library` are exempt
from rows 5–8 by design — they ship skeletons, not work surfaces.

## Steps to modify an existing stack

1. **Locate the SSOT.** Behavior change → `stack.yaml`. New scaffold file → `scaffold/`. New entity recipe → `skills/<skill>/references/anatomy.md`.
2. **Edit the SSOT.** Run `make regen-rules` and `make manifest-regen`.
3. **Verify.** Re-run the scaffold + parity tests above. For an existing consumer to benefit from skill changes, run `cos update` in that consumer (skills follow live symlinks; scaffold does not re-copy by design).

## Acceptance

- `python -m jsonschema -i src/templates/<id>/stack.yaml src/core/schemas/stack.schema.json` passes.
- `make manifest-regen` produces a clean diff.
- `tests/test_template_scaffold.py::test_<stack>_renders_cleanly` passes.
- A `cos init --stack <id>` against a temp directory produces a working consumer project (verified by `cos doctor` post-init).
- The anatomy file fits the contract and is under the 2 KB token cap.

## Rollback

Stack templates are inert in the meta-repo until a consumer pulls them. Revert the commit; existing consumers that already initialized off the old version are unaffected. Consumers that ran `cos update` after the bad commit can re-run it from a reverted meta-repo to roll back skills (scaffold is not re-copied, so any scaffold-only change is permanent on their side).

## Anti-patterns

- Putting language-specific imports in `src/core/`. The kernel must stay agent- and stack-agnostic.
- Bloating `scaffold/` with files the consumer should never touch. Those belong in skills (lazy-loaded reference) or in `src/core/` (live symlink).
- A stack that writes outside its declared roots. The boundary linter will flag it; ignoring the warning becomes a multi-stack collision later.
- Hand-editing `src/core/rules/dimension-registry.md` or `src/core/rules/skill-enforcement.md`. They are generated; the next `make regen-rules` overwrites your edit.
