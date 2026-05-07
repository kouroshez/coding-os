<!-- domain:ALL | layer:architecture | ssot:true | updated:2026-05-06 -->
# coding-os — Meta-Project Architecture

> P: Definitive description of what coding-os is (a meta-project / factory),
>    its three concentric layers, the consumer model, and the dogfood
>    contract that makes the meta-repo a first-class instance of itself.
> R: Anyone editing `core/`, `cli/`, `adapters/`, or `templates/`. Anyone
>    onboarding to the codebase. Anyone deciding whether a change is
>    DNA, mRNA, or phenotype.
> S: Stack-specific docs (`docs/adapters/<id>.md`, per-stack rules in
>    `templates/<stack>/rules/`) which describe ONE layer at a time.
> N: [AGENTS.md](../../AGENTS.md), [docs/engineering/graph_os-queries.md](../engineering/graph_os-queries.md),
>    [docs/engineering/graph-hallucination-cures.md](../engineering/graph-hallucination-cures.md),
>    [docs/governance/critical-rules.md](../governance/critical-rules.md)

## TL;DR

- coding-os is **not a library** an application imports.
- coding-os is **a factory** that emits projects shaped like itself —
  identical scaffold (`.coding-os/`, hooks, MCP server, AGENTS.md),
  swap the *stack* (django, nextjs, …) and the *agent* (claude, codex,
  cursor) per consumer.
- The repo is **also an instance of what it produces** — `CLAUDE.md` is
  a symlink to `AGENTS.md`, `.claude/hooks/*` symlinks back into
  `core/hooks/`. This is "P5 Dogfood" in the principles list.
- The first-class **meta-stack** (`templates/meta/`) is what binds the
  meta-repo to the same skill / dimension / enforcement contract every
  consumer project gets. Without it, the meta-repo is the only
  un-instrumented consumer.

## Three concentric layers

```
Layer 1  ── core/                ─ DNA          (agent-agnostic, stack-agnostic)
Layer 2  ── adapters/<agent>/    ─ mRNA         (per-agent translation)
Layer 3  ── templates/<stack>/   ─ phenotype    (per-stack overlay)
              │
              ▼  cli/  (the factory — `cos init`, `cos update`, `cos sync-all`)
Layer 4  ── consumer project     ─ organism     (e.g. acme-shop using django + claude)
```

### Layer 1 — `core/` (DNA)

Agent-agnostic, stack-agnostic kernel. Anything here propagates to
every consumer project the moment a `make regen-*` is run (or
immediately, via live symlinks for hooks/skills/rules).

| Module | Purpose |
|---|---|
| `core/thinking_os/` | MCP server (FastMCP). Hippocampus — memory + learning + metrics. Roles, formula composer, dispatcher. |
| `core/graph_os/` | Knowledge graph. Corpus callosum — Kùzu / SQLite backends, 16 `cos_graph_*` tools, extractors per language. |
| `core/board_os/` | Scrumban planner. Prefrontal cortex — task lifecycle, swimlane sync, `TASK-NNN-*.md` ↔ DB. |
| `core/hooks/` | 60+ shell hooks. Single registry (`registry.yaml`). |
| `core/skills/` | Markdown skill contracts (graph-explorer, codebase-explorer, thinking_os, …). |
| `core/rules/` | Always-active rules (memory.md, thinking_os.md, test-discipline.md). |
| `core/web/` | FastAPI Hub (port 9188) + React SPA. |
| `core/scripts/` | Make-time helpers; never run from hooks. |
| `core/schemas/` | JSON-schema definitions for stack.yaml / doctor-config / etc. |

### Layer 2 — `adapters/<agent>/` (mRNA)

Per-agent translation: how the kernel surfaces inside one specific AI
coding agent's runtime.

| Adapter | What it ships |
|---|---|
| `adapters/claude/` | `settings.template.json` rendered from `core/hooks/registry.yaml`, `sdk_dispatcher.py` for real Claude-Code-Sub-Agent dispatch, `install.sh` to wire `.claude/`, `.mcp.json`. |
| `adapters/codex/` | `hooks.template.json` (smaller — Codex CLI fires fewer matchers), `ensure_codex_mcp.py`, `enable_codex_hooks.py`. |
| `adapters/cursor/` | Minimal — only the events Cursor's hook spec actually fires. |

Each `adapters/<id>/adapter.yaml` declares `hook_capabilities` — the
renderer skips registry entries whose `{event, matcher}` pair isn't in
the list. **Adapter parity is bounded by the runtime, not by adapter
design.**

### Layer 3 — `templates/<stack>/` (phenotype)

Per-stack overlay: skills + rules + dimension-map + scaffold for one
language/framework.

| Template | Stack |
|---|---|
| `templates/_base/` | Base scaffold (Makefile, fragments, `.coding-os.yaml.template`). Always installed. |
| `templates/django/` | Django + DRF + PostgreSQL backend. |
| `templates/nextjs/` | Next.js + React + Tailwind frontend. |
| `templates/fastapi/` | FastAPI + Pydantic backend. |
| `templates/go/` + `templates/go-fiber/` | Go backends. |
| `templates/react-native/` | RN mobile. |
| **`templates/meta/`** ⭐ | **The meta-stack itself** — auto-loads `graph-explorer + clean-code + thinking_os` for `core/**`, `cli/**`, `adapters/**` edits. Closes the dogfood loop. |

A consumer project picks one or more of these via `cos init <stack>`.
The aggregator merges all listed stacks into the AGENTS.md / `.coding-os.yaml`.

## The meta-stack — closing the dogfood loop

For a long time the meta-repo was the **only consumer with no stack**:

- `templates/django/` → fires `python-django + clean-code` skill on
  `backend/**/*.py`.
- `templates/nextjs/` → fires `nextjs-react + clean-code + frontend-design`
  on `frontend/**/*.tsx`.
- meta-repo edits to `core/**/*.py`, `cli/**/*.py` → **NOTHING** —
  no skill auto-load, no dimension routing, no graph-explorer nudge.

`templates/meta/` fixes that. It declares:

- `dimensions:` for MCP-tool authoring, graph extractors, hook
  authoring, adapter authoring, template authoring, CLI commands, hub
  routes, board, cognition, rule SSOT regen.
- `skill_enforcement:` mapping the meta-repo file globs to
  `graph-explorer + clean-code + thinking_os`.
- `rules/meta-engineering.md` — pre-edit moves (graph context,
  rename plan, dim doctor, doc anchor, task marker).

The aggregator picks `templates/meta/stack.yaml` up automatically (no
filter — `regen_rules.py` walks every `templates/<id>/stack.yaml`).
After `make regen-rules` lands, `core/rules/dimension-registry.md` and
`core/rules/skill-enforcement.md` carry meta entries, and
`enforce-skill.sh` fires `Skill graph-explorer` whenever the agent
edits `core/**/*.py`.

## Propagation matrix — when a meta-repo edit reaches consumer

| Edit | Reaches consumer via | Latency |
|---|---|---|
| `core/hooks/*.sh` | Live symlink — no rebuild | Immediate |
| `core/thinking_os/**` | MCP server restart on consumer | One restart |
| `core/rules/*.md`, `core/skills/**` | Live symlink + `cos update` to refresh adapter glue | `cos update` |
| `adapters/<agent>/**` | `bash adapters/<agent>/install.sh` re-renders | Manual |
| `templates/<stack>/**` | `cos update` + `make manifest-regen` | Manual |
| `cli/**` | New `cos` invocations pick up changes | Immediate after `uv tool install --editable .` |

## Layer routing — where to put a change

Decision table:

| Change | Layer | Path |
|---|---|---|
| New MCP tool | core | `core/thinking_os/tools/*.py` |
| New `cos_graph_*` capability | core | `core/graph_os/tools/graph.py` + extractor |
| New hook | core | `core/hooks/<name>.sh` + register in `registry.yaml` |
| New skill | core | `core/skills/<name>/SKILL.md` |
| Always-active rule | core | `core/rules/<name>.md` (or template + regen) |
| Agent-only behaviour | adapter | `adapters/<id>/...` |
| Stack-only behaviour | template | `templates/<stack>/...` |
| Meta-repo behaviour | meta-template | `templates/meta/...` |
| Web UI / Hub change | core/web | `core/web/{routes,ui}/...` |

When ambiguous: ask "would a consumer using a different agent / stack
benefit?" — if yes, it's `core/`. If only one agent, it's `adapters/`.
If only one stack, it's `templates/<stack>/`.

## P-principles (one-liner index)

| # | Principle |
|---|---|
| P1 | SSOT-first |
| P2 | Agent-agnostic — never hardcode `.claude/` in `core/` |
| P3 | Minimal-context (3–10 files/task) |
| P4 | Diff-first |
| P5 | Dogfood — the meta-repo is also an instance |
| P6 | Log-everything via `make` |
| P7 | No-guessing — log unknowns to `docs/questions.md` |
| P8 | Adapter-SDK autonomy — never import an adapter SDK from `core/**` |

## Anti-patterns to avoid

- **Editing `core/rules/dimension-registry.md` or `skill-enforcement.md` directly.**
  Both are regen targets — edit `templates/<stack>/stack.yaml` and run
  `make regen-rules` instead.
- **Running `cos init` inside the meta-repo.** Would scaffold a
  duplicate. The meta-repo is bootstrapped, not initialised.
- **Adding a hardcoded `.claude/` path to `core/`.** P2 violation.
  Use `$COS_AGENT_DIR`. The audit hook `block-hardcoded-literals.sh`
  catches most cases, but not every shell file.
- **Bypassing `core/hooks/registry.yaml`.** A hook script with no
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
