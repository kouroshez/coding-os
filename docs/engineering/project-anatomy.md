<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-11-25 -->
# Project Anatomy — Polyglot Coexistence Contract

> SSOT for the top-level directory anatomy every consumer project follows,
> and for how multiple stacks coexist without breaking each other's tree.
> Per-stack inner trees live in each `stack.yaml::structure`. TASK-351.

## The top-level anatomy

```
<project>/
├── src/
│   ├── backend/             # THE backend — single-backend projects only
│   ├── services/<name>/     # multi-backend projects: one subtree per service
│   ├── frontend/            # web frontend (nextjs, vue-nuxt, …)
│   ├── mobile/              # mobile app (react-native, flutter, …)
│   └── shared/
│       ├── contracts/       # OpenAPI / proto / json-schema — the ONLY
│       │                    # cross-language boundary
│       └── <lang>/          # same-language shared code (go/, ts/, py/)
├── docs/ · .coding-os/ · AGENTS.md
└── .agents/memory/MEMORY.md # memory index, seeded empty by `cos init`
```

`cos init` seeds `.agents/memory/MEMORY.md` with only its heading, so the
memory every agent shares exists from the first session: Codex's
`prime-memory-codex` hook delivers it and `cos memory-lint` checks it. A project scaffolded before this has no index until someone writes the first memory or creates the file. Claude
Code reaches the same directory through `ensure-agent-memory-link`, which names
the machine-local dir the way Claude Code does — every character other than an
ASCII letter or digit becomes `-` — and skips a path whose name would exceed
Claude Code's 200-character limit (it then hashes the name, which the hook
cannot reproduce).

Rules:

1. **One owner per subtree.** A stack writes only inside its declared
   `structure.root` (enforced by scaffold-boundary; see
   `enforce-scaffold-boundary.sh`).
2. **Languages never share a subtree.** Cross-language communication goes
   through `src/shared/contracts/` artifacts only — never direct imports.
3. **Same-language reuse** lives in `src/shared/<lang>/`; promote code there
   when a second service needs it (reuse-first; nudge ships with TASK-366).

## Stack commands: `cos run`, no Makefile

A consumer project ships no Makefile; every command its agent is told to run starts with `cos`. Each stack declares named shell commands in `stack.yaml::commands` (`{name, cmd, help}`, e.g. `lint-backend`). `cos init`, `cos add-stack`, `cos remove-stack` and `cos update` write the aggregated map to `.coding-os.yaml::commands`; `cos run <name>` runs one from the project root and `cos run` lists them. Like `make`, it runs shell strings stored in the repo, so it stays off the agents' permission allowlist and `.coding-os.yaml` is a governance-protected file. A verify suite counts a `cos` command only when the command matches exactly, so `cos doc-lint docs/one.md` never passes the whole-tree docs-lint suite; in the coding-os checkout `cos` itself runs from, `cos doc-lint` runs `make docs-lint`. That test is the checkout's identity, never marker files, because `cos doc-lint` is on the allowlist and must not run a Makefile a project can write. The generated CI workflow runs the same `cmd` strings directly, so CI needs neither make nor cos.

In a clone-ready project (one with `.coding-os/managed-files.json`), `cos doc-lint` also checks the pages agents read under `.agents/`, `.claude/` and `.codex/`: a skill reference that links a file the project never got misleads the agent as surely as a broken doc. Localization already turns such a link into its plain text when it copies a page, including a link whose text is a code span (`` [`path`](target) ``), and the scaffold overlay does the same for the pages it has just written (never the project's own), so no stack ships a link to a file it never ships. This repo's own adapter dirs are install output and stay out of its lint; coding-os's slow scaffold suite lints a fresh render of every stack instead.

`cos update` migrates a project scaffolded before this: it deletes `.coding-os/Makefile.base` and `.coding-os/Makefile.stacks` unless the root `Makefile` still includes them (a symlinked Makefile, or an `include` form cos did not write, keeps the file and gets a warning, since `make` fails on a missing include), removes the lines cos wrote into a root `Makefile` that still has cos's `include` lines (its header, the two `include` lines, the "add your targets below" comment), keeps every line the user added, and deletes the root `Makefile` only when nothing else is left in it. Because `cos update` never regenerates `AGENTS.md`, the same step rewrites the `make` commands cos itself wrote there and in `.coding-os.yaml::verify` (`make docs-lint` → `cos doc-lint`, `make lint-backend` → `cos run lint-backend`, `make task-next` → `cos task-pick`, …; each old task target maps to the cos command its recipe called) and drops the `make verify-hooks` row; every other line stays as the user left it. An old `.github/workflows/ci.yml` whose verify step runs `make ${{ matrix.targets }}` is rewritten in place to run each leg's stack commands, as a fresh scaffold's does; if a target in it has no stack command, a leg is not the `targets: "..."` line cos wrote, or the file is a symlink, nothing is retired and a warning names the reason. Anything from the old Makefile it cannot map is named in a warning, with the fix: move `AGENTS.md` aside and let `cos update` regenerate it. The warning covers only names the old Makefile defined, so the user's own `make` targets are never reported.

## Multi-backend relocation rule

When a project composes **two or more stacks that declare the same
`structure.root`** (e.g. go-fiber + fastapi, both `src/backend/`), `cos init`
relocates each colliding stack's scaffold subtree to
`src/services/<stack-id>/`. Single-owner roots stay exactly where they are —
existing single-backend projects are untouched.

The relocation is path-prefix rewriting; the stack's inner tree (declared
in `structure.tree`) is preserved beneath the new root. It applies in two
places: scaffold copy + boundary aggregation (TASK-351), and profile
aggregation for every derived artifact (TASK-355, next section).

## Glob/verify propagation for relocated services (regen chain)

`cli.stack_registry.relocate_profile(profile, new_root)` is the single
remap primitive. Both world builders (`cli.main._build_world` for `cos init`,
`cli.update._aggregate_world` for `cos update`) compute
`cli.stack_registry.service_relocations(registry, templates)` and swap each
colliding profile for its relocated copy **before** `aggregate()` — so every
derived artifact downstream is service-scoped with no per-artifact special
cases:

| Profile field | Remap |
|---|---|
| `skill_enforcement[].globs`, `rules[].globs`, `dimensions[].read_files` | path-prefix: `src/backend/**` → `src/services/<id>/**` |
| `verify[].glob/cmd`, `substitutions` values, `structure.root/tree` | boundary-aware text swap of the declared root |
| `commands[].name` | suffixed `-<stack-id>` (two relocated stacks both declare `lint-backend`; aggregate dedupes by name, so unsuffixed names silently drop one stack's suite) |
| `verify[].suites` + suite names inside substitutions | same `-<stack-id>` rename so the Verification Matrix points at real commands |
| `VERIFY_{BACKEND,FRONTEND,MOBILE}{,_GLOB,_SUITES}` joined | aggregator joins distinct per-stack values with " \| " (plain merge was last-wins — one relocated stack's suite silently vanished from AGENTS.md) |

Invariants:

- **Single-owner stays byte-identical.** No collision → `service_relocations`
  is empty → profiles pass through untouched (golden parity guards this).
- **Meta-repo regen never relocates.** `src/scripts/regen_rules.py` aggregates
  ALL stacks for the global registry tables and intentionally skips
  relocation — collisions across the whole catalog are expected there.
- **Cross-service walls are generated.** Boundary aggregation appends each
  relocated root to every *other* stack's `forbids_writing_in`, so
  `enforce-scaffold-boundary.sh` flags an unowned write that crosses into a
  sibling service — no stack ever hand-lists a sibling's subtree.
- **Session primer follows the boundary file.** `skill_primer.py` derives
  `declared root → relocated root` per stack from the aggregated
  `$COS_STATE_DIR/scaffold-boundary.yaml` (no new state file) and remaps the
  per-glob card; enforcement hooks (`enforce-skill.sh` generic branches,
  `enforce-scaffold-boundary.sh`) are path-agnostic / boundary-driven and
  need no change.

## Per-stack `structure` declaration

Each `stack.yaml` declares:

```yaml
structure:
  root: src/backend            # the subtree this stack owns
  tree: |                      # canonical inner layout (reference for agents)
    src/backend/
    ├── cmd/<binary>/
    └── internal/{domain,ports,adapters}
  notes: "hexagonal: domain/ports/adapters; internal/-centric per Go community convention"
```

Canonical inner trees (research-grounded, 2025/2026 community conventions):

| Language / stack | Inner convention |
|---|---|
| Go (plain, chi, fiber) | `internal/`-centric; hexagonal `internal/{domain,ports,adapters}` + `cmd/<binary>`; avoid pkg-maximalism |
| Python (fastapi) | `app/{api,services,db,schemas}` — thin routes, logic in services |
| Python (django) | apps-per-domain under the project package |
| TypeScript (nextjs) | `app/` router + `components/ lib/` |
| TypeScript (plain) | `src/index.ts` entry, strict tsconfig |
| React Native | `src/mobile/{screens,components,navigation,hooks}` |

## See also

- [scaffold-boundary contract](../../src/templates/_base/scaffold/docs/governance/scaffold-boundary-contract.md) — per-stack write boundaries
- [template-authoring.md § Language layer](../playbooks/template-authoring.md) — language/extends composition
- [hub-architecture.md § Symlink health](hub-architecture.md) — propagation
