<!-- domain:META | layer:playbook | ssot:true | updated:2026-06-19 -->
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
| 13 | Runtime manifest | a buildable manifest (`go.mod` / `package.json` / `pyproject.toml` / `composer.json` / …) under `scaffold/` for code categories | soft |
| 14 | Lint config | a config for any linter named in a `VERIFY_<CATEGORY>` command — per-stack under `scaffold/`, or shared per-language under `_base/lang/<language>/` (`ruff.toml`/`eslint.config.*`/`.golangci.yml`/…) | soft |
| 15 | Sample test | ≥1 runnable test in `scaffold/` so `cos init` output has a green starting point | soft |
| 16 | Reference integrity | every `rules:` file and `DOMAIN_ROUTES` doc path resolves on disk (stack `scaffold/`, `_base`, or the repo) | soft |
| 17 | CI/CD workflow | a generated workflow that runs `make verify` (rendered by `render_ci_workflow`, init-strip, `modules.cicd`-gated) | soft |
| 18 | Containerization | a backend-only multi-stage `Dockerfile` skeleton + security-scan stub (rendered by `render_dockerfile`) | soft |

Hard rows fail `cos stack-lint` (exit 1) and CI; soft rows are reported as
GAP lines so a stack's completeness is visible without blocking iteration.
Rows 13–14 and 16 are auto-checked today (soft); rows 15, 17, 18 are the
documented bar the backfill + render generators fill, then become checkable.
Plain-language stacks (`<lang>-plain`) and `category: library` are exempt
from rows 5–8 and 13–15 by design — they ship skeletons, not work surfaces.

### Language config bundle (`_base/lang/<language>/`)

Toolchain config that is the same for every stack of a language lives **once**
here, not copied into each stack's `scaffold/`. `_overlay_scaffold` selects the
bundle by each active stack's `language:` and overlays it **last**, so a stack's
own `scaffold/` config still wins. Shipped today: `python/pyproject.toml`
(`[tool.ruff]` + `[tool.pytest.ini_options]`) and `typescript/` (`eslint.config.js`
flat v9, `.prettierrc.json`, `vitest.config.ts`, `tsconfig.json`). This is the
SSOT for ruff/eslint/prettier defaults — tune rules here, never per-stack. A
stack-specific dependency manifest (row 13, with deps) stays per-stack; the
bundle's `pyproject.toml` carries tool config only, so a python stack still
ships its own `requirements.txt`/deps without colliding.

Shipped bundles: `python/` (pyproject `[tool.ruff]`+`[tool.pytest.ini_options]`),
`typescript/` (eslint flat v9, `.prettierrc.json`, `vitest.config.ts`,
`tsconfig.json`), `go/.golangci.yml` (v2 schema), `rust/` (`clippy.toml` +
`rustfmt.toml`), `ruby/.rubocop.yml`, `php/phpcs.xml.dist`,
`dart/analysis_options.yaml` (flutter_lints). The linters walk up from
`src/<root>/` to find these at the project root. Two languages have no bundle by
design: **C#** is configured by the shared `_base` `.editorconfig` (`dotnet
format` reads it), and **Java** keeps its Spotless config in `pom.xml` (the
per-stack build manifest, row 13).

### Bootable scaffold (work-surface stacks)

A code-category stack is **bootable** when `cos init` produces a tree whose
`verify:` command is green after only a dependency install — no hand-authoring.
That means shipping, under the stack's `structure.root`, four things that line
up with the factory rows above: a runtime manifest with real deps (row 13), an
entrypoint, a sample test (row 15), and a `verify:` per-glob block (row 2). The
manifest lives at the stack root, not the project root, so the linter/test
runner discover it from the same directory the `verify:` cmd `cd`s into —
e.g. `fastapi`/`django` put `pyproject.toml` + `app/`|`config/` + `tests/` under
`src/backend/`, and `verify:` runs `cd src/backend && ruff check . && pytest -q`.
This mirrors the nestjs reference (`src/backend/package.json` + `src/backend/src/`).
Dep version pins stay conservative floors (exact pins are a separate per-stack
firecrawl pass) so a fresh install resolves without a stale ceiling.

`category: library` and `<lang>-plain` stacks are **exempt** (rows 13–15, per the
line above): they ship a documented skeleton, not a runnable app — a consumer
adds its own manifest. `_is_exempt_from_work_surfaces` ([stack_lint.py](../../src/cli/stack_lint.py))
encodes the decision, so `cos stack-lint` never flags a library stack for a
missing seed.

## Modularity gating — which mechanism, when

There is **no single** toggle mechanism, and that is intentional: the three
below run at different *lifecycles*, so pick by *what you are gating and when*.

| I want to… | Mechanism | Authored in | Fires at |
|---|---|---|---|
| Drop a **prose section** from the rendered `AGENTS.md` when a module is off | inline `{% if modules.X %}…{% endif %}` | `src/templates/_base/fragments/*.md.tmpl` | render (init + every `cos module` toggle) |
| Drop a **whole scaffold doc** (or a block inside it) when a module is off | `<!-- if-module:X -->…<!-- end-if -->` block, or a `<!-- … \| module:X -->` whole-file header tag | `src/templates/**/scaffold/docs/**.md` | init copy (⚠️ a mid-project re-toggle does **not** re-run this — RGC-A) |
| Gate an **MCP tool's capability** when a module is off | runtime `_gated_module` (reads `subsystems-state.json` live, fail-open) | `src/core/thinking_os/tools/_shared.py::safe_tool(name=…)` | every tool call |
| Filter **per-consumer rule rows** to the installed stacks | runtime skill-primer scoping | `src/core/hooks/_helpers/skill_primer.py` | SessionStart |

Rule of thumb: **render-strip** for always-on prose, **init-strip** for whole
files, **runtime-gate** for behaviour. Runtime-gate beats render-strip whenever
the state can change after init — it reads the SSOT live, so it can never drift.

## Fragment structure contract (`_base/fragments/*.md.tmpl`)

The rendered `AGENTS.md` is assembled from ordered fragments by
`cli.renderer.render_agents_md`. A fragment MUST:

- open with a single `## Section` heading (no YAML frontmatter, no `> Nav:` footer — those are for `docs/**`, not the assembled file);
- be joined to its neighbours with a blank line (`"\n\n".join`), so it needs no leading/trailing blank lines of its own;
- render **empty when its whole content is module-gated off** — the renderer drops empty parts, so a fully-gated fragment leaves no blank section;
- take its order from `src/templates/_base/base.yaml` (`agents_md_sections`), not its filename.

When gating *within* a fragment, use the whitespace-control idiom the existing
fragments use — put `{% endif %}` and the next `{% if %}` **adjacent on one
line** (`{% endif %}{% if modules.Y %}`) so a disabled module leaves no blank
line in a list or table. `render_dimension_registry` / `render_skill_enforcement`
are the **derived-artifact** exception (regenerated by `make regen-rules`, never
hand-edited).

## Out-of-tree community plugins (no fork required)

A third party adds a stack or adapter **without forking** the repo by dropping it
in an overlay dir the registries also scan:

- stack → `$COS_USER_TEMPLATES_DIR/<id>/stack.yaml` (default `~/.coding-os/templates`)
- adapter → `$COS_USER_ADAPTERS_DIR/<id>/adapter.yaml` (default `~/.coding-os/adapters`)

`load_stack_registry` / `load_adapter_registry` merge these after the bundled
tree. A community id **may not shadow** a bundled one (the bundled profile is
kept + a warning recorded), and a malformed community **adapter fails soft**
(skipped, never crashing the CLI) — a malformed bundled adapter still fails hard.
This mirrors the community-skill model (`$COS_USER_SKILLS_DIR`); the trust-tier /
consent / security-scan layer that skills carry is the planned hardening, not yet
wired for stacks/adapters.

**Which commands surface the overlay (TASK-471):** the overlay is **opt-in per
call site**. The *consumer-discovery* commands pass `overlay_template_dirs()` /
`overlay_adapter_dirs()` and so see community plugins — `cos list-stacks`,
`cos list-adapters`, `cos init --template <id>`, `cos add-stack <id>`,
`cos remove-stack <id>` (and any command via `main._get_stack_registry()` /
`_get_adapter_registry()`). The meta-repo **SSOT regen/lint/scaffold** loaders
(`src/scripts/generate_manifest.py`, `src/scripts/regen_rules.py`,
`stack_lint.py`) stay **bundled-only** (default `overlay_dirs=()`), so a
community stack never leaks into `scaffold_manifest.json` /
`dimension-registry.md` (the TASK-458 leak fix).

**File application (TASK-479):** discovery alone is not enough — `cos init` /
`cos add-stack` resolve a community stack's `scaffold/`, `.coding-os/` config
overlay, and `skills/` from its **`StackProfile.source_dir`** (the overlay dir),
not the bundled tree, so an out-of-tree stack is usable end-to-end. Bundled
stacks resolve byte-identically (the resolvers are bundled-first).

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
