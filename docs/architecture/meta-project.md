<!-- domain:ALL | layer:architecture | ssot:true | updated:2026-05-06 -->
# coding-os — Meta-Project Architecture

> P: Definitive description of what coding-os is (a meta-project / factory),
>    its three concentric layers, the consumer model, and the dogfood
>    contract that makes the meta-repo a first-class instance of itself.
> R: Anyone editing `src/core/`, `src/cli/`, `src/adapters/`, or `src/templates/`. Anyone
>    onboarding to the codebase. Anyone deciding whether a change is
>    DNA, mRNA, or phenotype.
> S: Stack-specific docs (`docs/adapters/<id>.md`, per-stack rules in
>    `src/templates/<stack>/rules/`) which describe ONE layer at a time.
> N: [AGENTS.md](../../AGENTS.md), [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md),
>    [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md),
>    [docs/governance/critical-rules.md](../governance/critical-rules.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## TL;DR

- coding-os is **not a library** an application imports.
- coding-os is **a factory** that emits projects shaped like itself —
  identical scaffold (`.coding-os/`, hooks, MCP server, AGENTS.md),
  swap the *stack* (django, nextjs, …) and the *agent* (claude, codex,
  cursor) per consumer.
- The repo is **also an instance of what it produces** — `CLAUDE.md` is
  a symlink to `AGENTS.md`, `.claude/hooks/*` symlinks back into
  `src/core/hooks/`. This is "P5 Dogfood" in the principles list.
- The first-class **meta-stack** (`src/templates/meta/`) is what binds the
  meta-repo to the same skill / dimension / enforcement contract every
  consumer project gets. Without it, the meta-repo is the only
  un-instrumented consumer.

## Project layout (Python src-layout)

Top-level shape — Python src-layout, industry standard (matches pip,
black, flask, requests, pydantic):

```
coding-os/
├── src/              ← importable code (P5 Dogfood: scaffold convention)
│   ├── cli/          Factory entrypoint
│   ├── core/         DNA (thinking_os, graph_os, board_os, web, scheduled, hooks, skills, rules, docs, schemas, commands)
│   ├── adapters/     mRNA (claude, codex, cursor)
│   ├── templates/    Phenotype scaffolds (django, fastapi, go, go-fiber, nextjs, react-native, meta, python)
│   └── scripts/      Maintenance tooling (regen, capture-golden, audit)
├── tests/            Test suite at root — NOT shipped in wheel (Python convention)
├── docs/             Meta-repo development docs
│   └── _meta/        Navigation + open questions (foundation-map.md, questions.md)
├── .coding-os/       Runtime state (gitignored — session, DB, presence, logs)
├── pyproject.toml    package-dir maps every importable top-level package into src/
├── Makefile
├── AGENTS.md (+ CLAUDE.md symlink)
└── README.md
```

**Why `tests/` is at root, not under `src/`:**

Python src-layout convention. Tests are not shipped in the wheel
(`pip install coding-os` only fetches `src/`). Keeping them at root
also matches every major Python project (pip, black, flask, requests,
pydantic) and lets pytest discover them without sys.path tweaks.

The scaffold (what consumer projects from `cos init` receive) does
*not* have a top-level `tests/` directory — consumer test files live
co-located inside their stack root (e.g. `src/backend/tests/`). The
meta-repo's top-level `tests/` is the factory's own test suite, not a
deviation from scaffold convention.

## Three concentric layers

```
Layer 1  ── core/                ─ DNA          (agent-agnostic, stack-agnostic)
Layer 2  ── src/adapters/<agent>/    ─ mRNA         (per-agent translation)
Layer 3  ── src/templates/<stack>/   ─ phenotype    (per-stack overlay)
              │
              ▼  cli/  (the factory — `cos init`, `cos update`, `cos sync-all`)
Layer 4  ── consumer project     ─ organism     (e.g. acme-shop using django + claude)
```

### Layer 1 — `src/core/` (DNA)

Agent-agnostic, stack-agnostic kernel. Anything here propagates to
every consumer project the moment a `make regen-*` is run (or
immediately, via live symlinks for hooks/skills/rules).

| Module | Purpose |
|---|---|
| `src/core/thinking_os/` | MCP server (FastMCP). Hippocampus — memory + learning + metrics. Roles, formula composer, dispatcher. |
| `src/core/graph_os/` | Knowledge graph. Corpus callosum — SQLite backend, 21 `cos_graph_*` tools, per-language extractors (py · ts/tsx · go · sh · php · yaml · json · toml) + framework contracts (fastapi/django/fiber/gin/next.js/laravel/wordpress/whmcs). |
| `src/core/board_os/` | Scrumban planner. Prefrontal cortex — task lifecycle, swimlane sync, `TASK-NNN-*.md` ↔ DB. |
| `src/core/hooks/` | 60+ shell hooks. Single registry (`registry.yaml`). |
| `src/core/skills/` | Markdown skill contracts (graph-explorer, codebase-explorer, thinking_os, …). |
| `src/core/rules/` | Always-active rules (memory.md, thinking_os.md, test-discipline.md). |
| `src/core/web/` | FastAPI Hub (port 9188) + React SPA. |
| `src/core/scripts/` | Make-time helpers; never run from hooks. |
| `src/core/schemas/` | JSON-schema definitions for stack.yaml / doctor-config / etc. |

### Layer 2 — `src/adapters/<agent>/` (mRNA)

Per-agent translation: how the kernel surfaces inside one specific AI
coding agent's runtime.

| Adapter | What it ships |
|---|---|
| `src/adapters/claude/` | `settings.template.json` rendered from `src/core/hooks/registry.yaml`, `sdk_dispatcher.py` for real Claude-Code-Sub-Agent dispatch, `install.sh` to wire `.claude/`, `.mcp.json`. |
| `src/adapters/codex/` | `hooks.template.json` (smaller — Codex CLI fires fewer matchers), `ensure_codex_mcp.py`, `enable_codex_hooks.py`. |
| `src/adapters/cursor/` | Minimal — only the events Cursor's hook spec actually fires. |

Each `src/adapters/<id>/adapter.yaml` declares `hook_capabilities` — the
renderer skips registry entries whose `{event, matcher}` pair isn't in
the list. **Adapter parity is bounded by the runtime, not by adapter
design.**

### Layer 3 — `src/templates/<stack>/` (phenotype)

Per-stack overlay: skills + rules + dimension-map + scaffold for one
language/framework.

| Template | Stack |
|---|---|
| `src/templates/_base/` | Base scaffold (Makefile, fragments, `.coding-os.yaml.template`). Always installed. |
| `src/templates/django/` | Django + DRF + PostgreSQL backend. |
| `src/templates/nextjs/` | Next.js + React + Tailwind frontend. |
| `src/templates/fastapi/` | FastAPI + Pydantic backend. |
| `src/templates/go/` + `src/templates/go-fiber/` | Go backends. |
| `src/templates/react-native/` | RN mobile. |
| **`src/templates/meta/`** ⭐ | **The meta-stack itself** — auto-loads `graph-explorer + clean-code + thinking_os` for `src/core/**`, `src/cli/**`, `src/adapters/**` edits. Closes the dogfood loop. |

A consumer project picks one or more of these via `cos init <stack>`.
The aggregator merges all listed stacks into the AGENTS.md / `.coding-os.yaml`.

## The meta-stack — closing the dogfood loop

For a long time the meta-repo was the **only consumer with no stack**:

- `src/templates/django/` → fires `python-django + clean-code` skill on
  `src/backend/**/*.py`.
- `src/templates/nextjs/` → fires `nextjs-react + clean-code + frontend-design`
  on `src/frontend/**/*.tsx`.
- meta-repo edits to `src/core/**/*.py`, `src/cli/**/*.py` → **NOTHING** —
  no skill auto-load, no dimension routing, no graph-explorer nudge.

`src/templates/meta/` fixes that. It declares:

- `dimensions:` for MCP-tool authoring, graph extractors, hook
  authoring, adapter authoring, template authoring, CLI commands, hub
  routes, board, cognition, rule SSOT regen.
- `skill_enforcement:` mapping the meta-repo file globs to
  `graph-explorer + clean-code + thinking_os`.
- `rules/meta-engineering.md` — pre-edit moves (graph context,
  rename plan, dim doctor, doc anchor, task marker).

The aggregator picks `src/templates/meta/stack.yaml` up automatically (no
filter — `regen_rules.py` walks every `src/templates/<id>/stack.yaml`).
After `make regen-rules` lands, `src/core/rules/dimension-registry.md` and
`src/core/rules/skill-enforcement.md` carry meta entries, and
`enforce-skill.sh` fires `Skill graph-explorer` whenever the agent
edits `src/core/**/*.py`.

## Propagation matrix — when a meta-repo edit reaches consumer

| Edit | Reaches consumer via | Latency |
|---|---|---|
| `src/core/hooks/*.sh` | Live symlink — no rebuild | Immediate |
| `src/core/thinking_os/**` | MCP server restart on consumer | One restart |
| `src/core/rules/*.md`, `src/core/skills/**` | Live symlink + `cos update` to refresh adapter glue | `cos update` |
| `src/adapters/<agent>/**` | `bash src/adapters/<agent>/install.sh` re-renders | Manual |
| `src/templates/<stack>/**` | `cos update` + `make manifest-regen` | Manual |
| `src/cli/**` | New `cos` invocations pick up changes | Immediate after `uv tool install --editable .` |

## Layer routing — where to put a change

Decision table:

| Change | Layer | Path |
|---|---|---|
| New MCP tool | core | `src/core/thinking_os/tools/*.py` |
| New `cos_graph_*` capability | core | `src/core/graph_os/tools/graph.py` + extractor |
| New hook | core | `src/core/hooks/<name>.sh` + register in `registry.yaml` |
| New skill | core | `src/core/skills/<name>/SKILL.md` |
| Always-active rule | core | `src/core/rules/<name>.md` (or template + regen) |
| Agent-only behaviour | adapter | `src/adapters/<id>/...` |
| Stack-only behaviour | template | `src/templates/<stack>/...` |
| Meta-repo behaviour | meta-template | `src/templates/meta/...` |
| Web UI / Hub change | src/core/web | `src/core/web/{routes,ui}/...` |

When ambiguous: ask "would a consumer using a different agent / stack
benefit?" — if yes, it's `src/core/`. If only one agent, it's `src/adapters/`.
If only one stack, it's `src/templates/<stack>/`.

## P-principles (one-liner index)

| # | Principle |
|---|---|
| P1 | SSOT-first |
| P2 | Agent-agnostic — never hardcode `.claude/` in `src/core/` |
| P3 | Minimal-context (3–10 files/task) |
| P4 | Diff-first |
| P5 | Dogfood — the meta-repo is also an instance |
| P6 | Log-everything via `make` |
| P7 | No-guessing — log unknowns to `docs/_meta/questions.md` |
| P8 | Adapter-SDK autonomy — never import an adapter SDK from `src/core/**` |

## Anti-patterns to avoid

- **Editing `src/core/rules/dimension-registry.md` or `skill-enforcement.md` directly.**
  Both are regen targets — edit `src/templates/<stack>/stack.yaml` and run
  `make regen-rules` instead.
- **Running `cos init` inside the meta-repo.** Would scaffold a
  duplicate. The meta-repo is bootstrapped, not initialised.
- **Adding a hardcoded `.claude/` path to `src/core/`.** P2 violation.
  Use `$COS_AGENT_DIR`. The audit hook `block-hardcoded-literals.sh`
  catches most cases, but not every shell file.
- **Bypassing `src/core/hooks/registry.yaml`.** A hook script with no
  registry entry won't be rendered into any adapter.

## Where to read next

| Question | Doc |
|---|---|
| What's the agent loop? | [AGENTS.md](../../AGENTS.md) § Core Loop |
| All Critical Rules? | [docs/governance/critical-rules.md](../governance/critical-rules.md) |
| MCP error envelope? | [docs/engineering/mcp-error-envelope.md](../engineering/mcp-error-envelope.md) |
| Graph layer how-to? | [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md) |
| Graph hallucinations cured? | [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md) |
| Hub UI internals? | [docs/engineering/hub-architecture.md](../engineering/hub-architecture.md) |
| Adapter parity contract? | [docs/engineering/adapter-parity.md](../engineering/adapter-parity.md) |
| Claude Code adapter? | [docs/adapters/claude-sdk.md](../adapters/claude-sdk.md) |
