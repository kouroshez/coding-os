<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# Template Location — In-Repo Files vs In-CLI vs Hybrid

Purpose: Answer "should coding-os ship template files into every consumer project, or should templates live inside the `cos` CLI and be materialized on demand?" with explicit personas, scenarios, and a recommendation grounded in how modern scaffolders handle the same tradeoff (Rails, Next.js CLI, Nx, Cookiecutter, Yeoman).

Read when: considering a change to how templates (task-detail, ADR, PRD, skill skeleton, runbook, …) are distributed · deciding where to add a new template class · debating whether consumer projects should have `docs/governance/_templates/` at all.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

**Status:** analysis only — no implementation change. The user explicitly asked for analysis of scenarios before committing to a direction.

## Current state (as of 2026-04-18)

Consumer projects created by `cos init` receive a copy of every template under `docs/governance/_templates/` in the repo root. This includes `task-detail.md`, `task-list.md`, ADR template (if defined), PRD classifier outputs, etc. Templates are:

- Physical files, inspectable with `cat`, `grep`, and an IDE file tree
- Version-controlled with the consumer project
- Free to customize per-project
- Synced on `cos update` **unless** the consumer modified them (collision detection via `installed-manifest.json`)

The four enforced markdown classes ([enforce-template.sh](../../core/hooks/enforce-template.sh)) reach into these files via relative paths.

## The three candidate architectures

### A. Files-in-repo (status quo)

Every template is a real file under `docs/governance/_templates/`.

### B. Templates-in-CLI (user's hypothesis)

Templates live only inside the `cos` package (`src/cli/templates/*.md`). Consumer repos are clean — no `docs/governance/_templates/` folder. When a template is needed:

```bash
cos template show task-detail            # print to stdout
cos template write docs/tasks/TASK-042-x.md --from task-detail
```

### C. Hybrid (lazy materialization + ejection)

CLI is the canonical source (as in B). On first use of a template in a project, CLI materializes it into `docs/governance/_templates/` (as in A) and records the materialization in `installed-manifest.json`. Future `cos update` syncs unmodified templates and respects overrides.

## Personas

- **P1 — Junior dev, week one.** Just cloned the repo. Wants to understand how tasks are structured by reading files.
- **P2 — AI agent writing an ADR.** Invoked by a human; needs the template to follow the team's house style.
- **P3 — Tech lead customizing templates.** Company-specific sections (e.g., "Security Review" required on every ADR).
- **P4 — coding-os maintainer.** Improves a template; wants the change to reach every consumer without manual work.
- **P5 — Enterprise user with clean-repo policy.** Legal or compliance requires minimal boilerplate — every extra folder is a maintenance surface.
- **P6 — Air-gapped / offline developer.** No network; package already installed on the machine.
- **P7 — Template author extending coding-os.** Wants to add a new template class (e.g., incident post-mortem).

## Scenario matrix

| # | Scenario | A: Files | B: CLI-only | C: Hybrid |
|---|---|---|---|---|
| **S1** | P1 explores repo to learn tasks structure | ✅ reads `docs/governance/_templates/task-detail.md` directly | ❌ has to know `cos template show` exists | ✅ same as A on first use |
| **S2** | P2 agent writes an ADR | ✅ reads template, copies into target | ⚠️ needs to know CLI command; more plumbing | ✅ template already materialized after any prior use |
| **S3** | P3 customizes ADR template for their team | ✅ edits file directly; git tracks | ❌ must fork coding-os or use an override mechanism that doesn't exist yet | ✅ edits file; CLI detects divergence and skips overwrite on `cos update` |
| **S4** | P4 improves a template upstream | ⚠️ consumers need `cos update`; merge conflict if they modified | ✅ bump CLI version; every project gets it | ⚠️ same as A for already-materialized; ✅ for first-time users |
| **S5** | P5 wants repo clean of meta-boilerplate | ❌ `docs/governance/_templates/` is extra noise | ✅ repo stays minimal | ⚠️ folder appears after first template use |
| **S6** | P6 uses template offline | ✅ file is already there | ✅ CLI is locally installed | ✅ after materialization |
| **S7** | P7 authors a new template class | ⚠️ needs PR to coding-os AND per-project update | ✅ CLI update propagates everywhere | ✅ CLI update; existing projects don't auto-adopt new class until they use it |
| **S8** | Running `enforce-template.sh` hook | ✅ hook reads file from repo path | ❌ hook must call CLI or subshell `cos template path <name>` | ✅ read file from repo path (after materialization) |
| **S9** | `cos_doc_search` MCP tool indexes templates (via `make docs-index`) | ✅ crawls `docs/` and finds them | ❌ templates not in `docs/`; invisible to doc RAG | ✅ crawls materialized copies; unmaterialized classes are not yet discoverable |
| **S10** | Two different projects, one team, different template customizations | ✅ per-project divergence trivial | ❌ no project-level override surface | ✅ each project overrides independently; CLI upgrade respects both |
| **S11** | Onboarding docs say "your ADR template is at …" | ✅ file path — stable, diffable link in a PR | ❌ command — doesn't URL-link on GitHub, harder to diff | ✅ file path after materialization |

## Cross-reference: how similar tools solved this

| Tool | Choice | Rationale |
|---|---|---|
| **Rails** (`rails new`) | A — files generated at init | Ruby community expects full visibility; generators run once, files are yours |
| **Next.js CLI** (`create-next-app`) | A — files generated | Ship a working starter; subsequent `next` CLI doesn't regenerate templates |
| **Nx** | C — generators ship in plugins; generated files live in workspace | Plugin updates don't clobber workspace; `nx g` materializes on demand |
| **Cookiecutter** | A — everything generated at `cookiecutter` time | No post-generation sync; accept the drift |
| **Yeoman** | A — subgenerators run on demand; generated files stay | Same as Cookiecutter with per-component generators |
| **ESLint/Prettier** | B — config preset is in the npm package | The preset itself isn't customized per-project; users override via their config file |
| **create-t3-app** | A — full scaffold, no sync thereafter | "Your project, your changes" |
| **Ruby on Rails engines** | C — engine ships views; apps can override by shadowing paths | Override-by-convention (shadowing files) avoids explicit eject |

**Pattern:** large scaffolders (Rails, Next.js, create-t3) pick A. Multi-project orchestrators with ongoing upgrades (Nx, Rails engines) pick C. Pure preset tools (ESLint) pick B.

coding-os is closer to Nx / Rails engines than to Rails itself — because we ship updates (`cos update`) to existing projects. That argues for C.

## Second-order effects

### SSOT hygiene

- **A** — every project has its own copy of the truth. Drift is normal; surgery on `cos update` is required.
- **B** — one copy, in the CLI. No drift, no surgery.
- **C** — one copy source + opt-in materialization with override tracking. No drift until the user chooses to diverge.

### Performance

- **A** — read from disk, zero-ms overhead.
- **B** — read from CLI process (still disk, but one layer of indirection). Meaningfully slower only for hooks that fire on every Write (thousands per day). Profile before assuming.
- **C** — same as A after first use.

### Enforcement-hook complexity

[enforce-template.sh](../../core/hooks/enforce-template.sh) reads file paths today:

```bash
TEMPLATE="$DOCS_ROOT/governance/_templates/adr-template.md"
if [[ -f "$TEMPLATE" ]]; then ... fi
```

Under B, hook must call `cos template path adr-template` — adds an extra process per PreToolUse. Not huge, but every hook in coding-os minimizes its subprocess count for latency reasons (PreToolUse budget is ~100ms). This is a non-trivial regression.

### Doc RAG (`cos_doc_search`)

Templates under `docs/governance/_templates/` are indexed by `make docs-index` → `cos_doc_search` can retrieve them semantically. Under B, templates live in the CLI package and are invisible to the RAG layer. A consumer asking `cos_doc_search "how to write an ADR"` gets **nothing**.

This is a concrete loss. Templates are reference material; burying them in the CLI hides them from the very semantic retrieval that coding-os's thinking_os brain relies on.

## Recommendation

**Adopt C (hybrid), but LATER — not now.**

### Why C wins on the merits

1. Addresses P5's "clean repo" concern (no folder until needed).
2. Preserves A's visibility once a template is materialized (P1, P2).
3. Keeps customization by consumer projects simple (P3).
4. CLI as canonical source lets P4 ship upstream updates cleanly.
5. Matches Nx / Rails engines pattern (closest neighbors).

### Why not now

1. **enforce-template.sh stays simple** under A. Migrating to C requires every hook that reads a template path to become CLI-aware.
2. **Doc RAG continues to work** under A. Migrating to C requires extending the doc indexer to crawl CLI package templates or materializing on `cos init`.
3. **installed-manifest.json needs extension** to track per-template materialization + override state. That's a new schema field, new invariants, new tests.
4. **No user pain driving the change today.** `docs/governance/_templates/` in consumer repos isn't a real problem — it's a few template files, not a scaffolded framework with hundreds of files.

### Concrete path forward

- **Short term (status quo, A):** document that templates live in `docs/governance/_templates/` and are safe to edit per-project. Note this in [docs/engineering/template-enforcement.md](template-enforcement.md). ✅ done.
- **Medium term (migrate to C):** when we ship the 10th template class (runbook, RFD, incident post-mortem, …), folder noise becomes visible. Then:
    1. Add `cos template list` / `cos template show <name>` commands (read-only first).
    2. Build a `materialize_on_use` field in `installed-manifest.json`.
    3. Update `enforce-template.sh` to call `cos template path <name>` and cache the result per-session.
    4. Add doc indexer branch that walks CLI package templates for classes that haven't been materialized yet.
    5. Ship as a feature flag for one release cycle; promote to default.
- **Long term (future consideration, NOT B):** never go full B. The doc RAG integration is too valuable to give up; making templates invisible to semantic search undoes a core capability.

### What to decide now

Nothing in the architecture. Status quo A is correct for the current scale. Revisit when:

- Consumer count > 50 projects, OR
- Template class count > 10, OR
- A user files a real complaint about `docs/governance/_templates/` clutter.

Until then, the work is to:

1. **Document A explicitly** — this file.
2. **Add new template classes as files** (the runbook template discussed in [template-enforcement.md](template-enforcement.md) § Extending).
3. **Watch for drift signals** — e.g., `cos update` merge conflicts logged in telemetry.

## References

- [docs/engineering/template-enforcement.md](template-enforcement.md) — the hook that reads these templates
- [docs/engineering/hooks-reference.md](hooks-reference.md) — catalog of all hooks
- `src/cli/main.py` — where `cos template` subcommands would land if we migrate to C
- Nx generators documentation (<https://nx.dev/features/generate-code>) — the closest-neighbor pattern we'd borrow from
