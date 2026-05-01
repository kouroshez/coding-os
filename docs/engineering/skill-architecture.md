<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# Skill Architecture — Fundamentals + Stack Specialization

Purpose: Canonical explanation of how coding-os organizes skills. Two-layer model: **agent-agnostic fundamentals** in `core/skills/` + **stack-specific specializations** in `templates/<stack>/skills/`. A stack skill declares `depends_on: [fundamentals...]` in its frontmatter so the agent loads both and gets DRY guidance that specializes where it matters.

Read when: adding a new stack · adding a new skill · debugging why `enforce-skill.sh` loaded the wrong skill · asking "is this a shared concern or a stack-specific one?".

**Aligned with:** Claude Certified Architect Foundations (TS 3.2 — skill frontmatter composition; TS 3.3 — path-scoped rules).

## The problem composition solves

Before extraction, `templates/django/skills/python-django/SKILL.md`, `templates/fastapi/skills/python-fastapi/SKILL.md`, and `templates/go-fiber/skills/go-fiber/SKILL.md` each restated the same cross-cutting patterns: service/selector split, error envelopes, idempotency, N+1 avoidance, migration discipline, auth middleware shape. Seven backend concerns × three stacks = 21 copies that must stay in sync when any one pattern evolves.

Composition pulls those concerns into one SSOT (`core/skills/backend-fundamentals/SKILL.md`) and leaves each stack skill to cover **only what's framework-specific**: Django `Meta`, FastAPI `Depends`, Fiber middleware chain, etc.

## The two layers

```
core/skills/                              ← agent-agnostic, stack-agnostic
├── clean-code/SKILL.md                   ← fail-closed errors, no PII in logs, typed exceptions
├── thinking_os/SKILL.md                  ← Complexity Gate, Zoom cycle (always-active via rule)
├── codebase-explorer/SKILL.md            ← trace-flow, dependency-map
├── backend-fundamentals/SKILL.md         ← services, idempotency, envelopes, migrations, N+1
└── frontend-fundamentals/SKILL.md        ← loading/error/empty states, hydration, a11y, SEO

templates/<stack>/skills/                 ← framework-specific extensions
├── django/skills/python-django/          ← Django ORM, DRF, Celery, services+selectors layout
├── fastapi/skills/python-fastapi/        ← Pydantic, Depends, async handlers
├── go/skills/go-patterns/                ← idiomatic Go, error wrapping, table-driven tests
├── go-fiber/skills/go-fiber/             ← Fiber v2 handlers, middleware, validator
└── nextjs/skills/{nextjs-react,frontend-design}/  ← RSC, hydration, design system
```

## How composition works

Each stack SKILL.md declares its dependencies in frontmatter:

```yaml
---
name: python-django
description: Use when creating or modifying Python files in backend/ — Django models, DRF views, services, selectors, Celery tasks, migrations, tests.
globs: "backend/**/*.py"
context: fork
depends_on:
  - clean-code
  - backend-fundamentals
allowed-tools:
  - Read
  - Grep
  - Glob
  - Edit
  - Write
---
```

When [enforce-skill.sh](../../core/hooks/enforce-skill.sh) matches a file to `python-django`, the agent loads `python-django` AND transitively loads every `depends_on` entry. The resulting context is: universal code quality (clean-code) + cross-stack backend patterns (backend-fundamentals) + Django specifics (python-django). No duplication at source; one skill per task at load time.

**Why this beats install-time concatenation:** install-time composition (pre-concatenating `backend-fundamentals` into `python-django`) would save one skill-load round-trip but breaks skill independence. If the agent is reviewing a non-Django backend project and needs `backend-fundamentals` alone, it can still load it standalone.

## Decision rule — shared vs specific

When adding a rule, ask: **does this hold for every <layer> stack, or only for <framework>?**

| Rule class | Goes in |
|---|---|
| Code quality, fail-closed errors, typed exceptions | `core/skills/clean-code` |
| Service/selector split, idempotency, envelopes, N+1 avoidance, migration discipline | `core/skills/backend-fundamentals` |
| Client/server component split, hydration safety, loading-error-empty-state pattern, SEO basics | `core/skills/frontend-fundamentals` |
| Django `Meta.ordering`, DRF serializer `Meta.fields` | `templates/django/skills/python-django` |
| FastAPI `Depends()` chains, Pydantic `model_validator` | `templates/fastapi/skills/python-fastapi` |
| Next.js App Router conventions, `use client` rules | `templates/nextjs/skills/nextjs-react` |

If a rule starts stack-specific and later turns out to hold across stacks, **promote it up** (move to fundamentals, remove from the specific skill, bump the `depends_on` only if it wasn't already there).

## Why not one monolithic skill per stack (status quo before 2026-04-18)

- **Duplication grows linearly** with stack count. 5 backend stacks × 1 monolith each × N shared concerns = 5N copies to update when a concern changes.
- **Cross-stack reviews suffer.** Reviewing a go-fiber codebase while having `python-django` worldview loaded produces noisy suggestions.
- **Testing is weaker.** No way to test "does our shared backend guidance hold" — only per-stack monoliths exist.

## Why not install-time concatenation (Option B from analysis)

- Install-time requires a regen step. Miss the step and stack skills drift from `core/skills/backend-fundamentals`.
- Breaks skill independence — can't invoke `backend-fundamentals` alone.
- `make regen-rules` and `make regen-adapter-templates` already exist; adding a third regen step raises the bar for contributors.

Runtime composition via `depends_on` gives the same DRYness with zero regen step.

## Interaction with `enforce-skill.sh`

The hook reads [core/rules/skill-enforcement.md](../../core/rules/skill-enforcement.md) — a table mapping file globs to primary + secondary skills. That table is **generated** from `templates/*/stack.yaml` by `make regen-rules`. Today the table lists:

| Globs | Primary | Secondary |
|---|---|---|
| `backend/**/*.py` | `python-django` | `clean-code` |
| `backend/**/*.py` | `python-fastapi` | `clean-code`, `api-design` |
| `backend/**/*.go` | `go-patterns` | `clean-code` |
| `backend/**/*.go` | `go-fiber` | `clean-code` |
| `frontend/**/*.{ts,tsx}` | `nextjs-react` | `clean-code`, `frontend-design` |

Once `backend-fundamentals` and `frontend-fundamentals` ship, the `stack.yaml` files should declare them as additional secondaries (or the stack skills declare `depends_on:` and the hook resolves transitively). This keeps [skill-enforcement.md](../../core/rules/skill-enforcement.md) readable while the full dependency graph is computed by the hook.

## Path-scoped rules (distinct from skills)

A skill is invoked on demand (`Skill skill: "python-django"`); a **rule** loads automatically based on file path. For universal policies (e.g., all Python uses `ruff`), prefer a rule in `core/rules/` with `paths: ["**/*.py"]` frontmatter over a skill load. The exam guide's TS 3.3 favors path-scoped rules for "conventions that span multiple directories regardless of stack" — rules < skills in context cost, so pick rules when the policy is tiny and universal.

## Testing a new fundamentals skill

1. Write the skill with a clear `description` that says WHEN to use it.
2. Add `depends_on:` from at least one stack skill so it's actually exercised.
3. Manually trigger: edit a relevant file in this repo via an agent; confirm `enforce-skill.sh` logs `fundamentals skill loaded` in `.coding-os/.hooks.log`.
4. Add a test in `tests/test_skills.py` (or the skills-specific test file) that loads the SKILL.md and asserts required frontmatter keys.

## References

- [core/rules/skill-enforcement.md](../../core/rules/skill-enforcement.md) — generated globs → skills table
- [core/hooks/enforce-skill.sh](../../core/hooks/enforce-skill.sh) — the gating hook
- [core/docs/agent-workflow.md](../../core/docs/agent-workflow.md) § Hook & Skill Enforcement
- [docs/engineering/hooks-reference.md](hooks-reference.md) — all hooks catalog
- Claude Certified Architect Foundations → Task Statement 3.2 and 3.3
