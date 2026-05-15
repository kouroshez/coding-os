<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-04-29 -->
# Stack Anatomy Contract

> P: Defines the canonical shape of `src/templates/<stack>/skills/<skill>/references/anatomy.md` so every stack and every agent (claude · codex · cursor) emits the same file structure, naming, and entity recipes.
> R: Authoring or auditing a stack's anatomy file; resolving disagreement between agents about where a new file belongs.
> S: Reading code — the actual conventions are in the per-stack `anatomy.md`, not here.
> N: [docs-system.md](docs-system.md), [scaffold-boundary-contract.md](scaffold-boundary-contract.md), [doc-cheat-sheet.md](src/templates/doc-cheat-sheet.md)

> Nav: [Governance Index](./00-index.md)

---

## Why this contract exists

`anatomy.md` is the file every coding-os agent reads BEFORE it Writes any stack-specific source file. It answers four questions in <2 KB:

1. Where does file `X` live?
2. What is it named?
3. What does it depend on?
4. What is the recipe to add a new entity (endpoint / model / component / screen / handler / migration / test)?

If two stacks (or two agents) disagree on these answers, multi-stack projects rot. This contract makes the answer machine-checkable.

## Token budget

Hard cap: **2000 tokens** per anatomy.md. If a stack's anatomy is bigger, split entity recipes into siblings (`anatomy-models.md`, `anatomy-endpoints.md`) and link from the main anatomy.

## File location

```
src/templates/<stack>/skills/<primary_skill>/references/anatomy.md
```

Anatomy lives next to its skill, not in `src/templates/<stack>/scaffold/docs/`. Reason: `cos init` copies scaffold ONCE; references load lazily forever.

## Required frontmatter

```html
<!-- domain:STACK_DOMAIN | layer:reference | ssot:true | updated:YYYY-MM-DD -->
```

`STACK_DOMAIN` is the uppercased stack id with hyphens removed: `nextjs` → `NEXTJS`, `go-fiber` → `GOFIBER`, `react-native` → `REACTNATIVE`.

## Required opening block

Short form (`> P:` / `> R:` / `> S:` / `> N:`) — anatomy is a high-traffic routing file, short form is mandatory to save tokens.

## Required H2 sections (this exact order)

```
## 1. Boundary
## 2. Layout map
## 3. Entity recipes
## 4. Conventions
```

The contract test (`tests/test_anatomy_contract.py`) rejects any anatomy missing one of these or reordering them.

### 1. Boundary

ONE line that links to the machine-readable SSOT — no table, no duplicated fields:

```markdown
SSOT: [`src/templates/<stack>/scaffold-boundary.yaml`](../../../scaffold-boundary.yaml).
```

Rationale: duplication of `roots` / `imports_from` / `forbids_writing_in` in prose creates drift. The yaml is the only canonical source; humans read it directly via the link.

### 2. Layout map

A table — one row per file pattern this stack produces:

| Pattern | Location | Naming | Imports from | Description |

Order rows top-down by frequency: most-edited file first.

### 3. Entity recipes

One H3 per entity type the stack supports. Each H3 carries:

- **Trigger:** the user request that invokes this recipe.
- **Files emitted:** numbered list of paths (use `<name>` for the parameter).
- **Steps:** numbered, terse — each step ≤1 line.
- **Optional generator script:** `src/scripts/<name>.py` if the stack ships one.

Common entity types (use these names verbatim when applicable):

- `Add a new endpoint` (backend stacks)
- `Add a new model` (any data-bearing stack)
- `Add a new component` (frontend stacks)
- `Add a new screen` (mobile stacks)
- `Add a new migration` (db-bearing stacks)
- `Add a new test` (universal — required in every anatomy)

### 4. Conventions

ONE H2 with three terse subsections — each MUST be present even if empty:

#### Naming

Bullet list. Each bullet maps a thing → its rule. Examples: `kebab-case.tsx`, `camelCase` functions, `SCREAMING_SNAKE_CASE` constants.

#### Test colocation

State the rule once. Two patterns are accepted:

- **Colocated:** `users/users.test.ts` next to `users/users.ts`.
- **Mirrored:** `tests/users/test_users.py` mirrors `src/users/users.py`.

Pick one per stack. Mixed = rejected by lint.

#### Dependency rules

Bullet list of allowed / forbidden import directions. MUST agree with `scaffold-boundary.yaml::imports_from`. Drift = test failure.

## Authoring rules

- **Lead with verbs.** `Returns`, not `This will return`.
- **Tables beat prose.** If a section is >5 prose sentences, refactor into a table.
- **No prose ≥10 words explaining what the code does.** Code is the doc.
- **No screenshots.** Diagrams are `.svg` or `.mermaid` siblings.
- **No version markers in body.** Version lives in frontmatter `updated:` only.

## Cross-agent uniformity guarantee

Three guarantees that make every agent emit identical-shape anatomy:

1. **Schema is mechanical.** Required sections + table columns mean diff against the schema is unambiguous.
2. **Lint enforces it.** `tests/test_anatomy_contract.py` runs on every PR.
3. **Token budget is a hard cap.** No agent can pad — every line costs.

Agents (claude, codex, cursor) read the same `anatomy.md` and produce the same scaffold-growth output because the recipe section is the source of truth. The agent does not invent file paths — it follows the recipe.

## Adding a new entity recipe

1. Open `anatomy.md` for the stack.
2. Append H3 under § 3 in alphabetical order (rule: keep `Add a new test` last).
3. Run `make docs-lint` (frontmatter + nav check).
4. If you ship a generator, drop the script under `src/templates/<stack>/skills/<skill>/scripts/<name>.py`.
5. Reference the script from the recipe's "Optional generator script" line.

## When a stack legitimately can't satisfy the schema

Some stacks (e.g. a future `infra-only` template) won't have models or components. They MUST still ship anatomy.md with each H2 present — empty sections carry the literal line:

```
_Not applicable to this stack._
```

This is contract-compliant. The lint accepts it.
