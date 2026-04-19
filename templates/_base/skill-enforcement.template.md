# Skill Loading Enforcement

> This rule ensures domain skills are loaded via the `Skill` tool before writing code.

## Mandatory Skill Invocations

Before writing or editing code files, invoke the matching domain skill:

- `backend/**/*.py` → `Skill skill: "python-django"`
- `frontend/**/*.{ts,tsx}` → `Skill skill: "nextjs-react"`
- Any code file (`.py`, `.ts`, `.tsx`) → `Skill skill: "clean-code"`

## Task Workflow Skills

During the Core Loop (AGENTS.md), load skills based on Complexity Gate result:

- **CLEAR** → domain skill only (e.g., `python-django`). No `thinking-os`, no `clean-code`.
- **COMPLICATED** → `thinking-os` + domain skill + `clean-code`
- **COMPLEX** → `thinking-os` + domain skill + `clean-code` + risk-relevant secondary skills
- **CHAOTIC** → act first to stabilize, then same as COMPLICATED

## Domain Routing (32 skills)

When multiple skills cover the same domain, use the **Primary** skill first.

Skills are either **project** (custom SKILL.md with NakoDigital SSOT references) or **global** (generic best-practices via symlink from `.agents/skills/`). Project skills are preferred when available.

**Backend (Django/Python)**

| Task | Skill | Type | Min Gate | Role |
| --- | --- | --- | --- | --- |
| Models, views, serializers, services | `python-django` | project | CLEAR | Primary |
| Auth, CSRF, XSS, payments security | `django-security` | project | COMPLICATED | Security tasks |
| Testing, TDD, factory_boy | `django-tdd` | project | COMPLICATED | Test writing |
| Architecture, ORM patterns, caching | `django-patterns` | global | COMPLICATED | Secondary |
| Celery tasks, workers, Beat | `django-celery-expert` | global | COMPLICATED | Async tasks |
| Type hints, mypy, protocols | `python-type-safety` | global | COMPLEX | Type annotations |
| Style, linting, formatting | `python-code-style` | global | COMPLEX | Code style review |
| Validation, exceptions, error handling | `python-error-handling` | global | COMPLICATED | Error patterns |
| Architecture decisions, KISS, SRP | `python-design-patterns` | global | COMPLEX | Refactoring |
| cProfile, memory profiling | `python-performance-optimization` | global | COMPLEX | Perf tuning |
| pytest, fixtures, mocking | `python-testing-patterns` | global | COMPLEX | Test patterns |

**Frontend (Next.js/React)**

| Task | Skill | Type | Min Gate | Role |
| --- | --- | --- | --- | --- |
| Components, pages, hooks, hydration | `nextjs-react` | project | CLEAR | Primary |
| Design tokens, Tailwind, responsive | `tailwind-design-system` | project | COMPLICATED | Design system |
| Building UI, distinctive interfaces | `frontend-design` | project | COMPLICATED | UI building |
| File conventions, metadata, bundling | `next-best-practices` | global | COMPLICATED | Config/routing |
| Styles, palettes, font pairings, UX | `ui-ux-pro-max` | global | COMPLEX | Reference |
| Accessibility, Web Interface Guidelines | `web-design-guidelines` | global | COMPLEX | A11y review |
| Microcopy, error messages, CTAs | `ux-copy` | global | COMPLEX | UX writing |
| Playwright, browser screenshots | `webapp-testing` | global | COMPLICATED | E2E testing |

**Database (PostgreSQL + SQLite)**

| Task | Skill | Type | Min Gate | Role |
| --- | --- | --- | --- | --- |
| Schema, queries, indexing, migrations | `postgres-patterns` | project | CLEAR | Primary (PostgreSQL) |
| EXPLAIN, JSONB, replication, VACUUM | `postgres-pro` | global | COMPLICATED | Performance |
| New table design, constraints | `postgresql-table-design` | global | COMPLICATED | New schemas |
| SQL query tuning, EXPLAIN plans, indexing | `sql-optimization` | global | COMPLICATED | Universal SQL perf |
| SQLite DB, FTS5, migrations, thinking-os.db | `sqlite-database-expert` | global | COMPLICATED | SQLite/embedded DB |

**Payments (Stripe + Payment Core)**

| Task | Skill | Type | Min Gate | Role |
| --- | --- | --- | --- | --- |
| Payment integration, checkout, webhooks, refunds | `stripe-best-practices` | global | COMPLICATED | Primary — Stripe integration |
| Stripe SDK upgrade, API version migration | `upgrade-stripe` | global | COMPLICATED | SDK/API upgrades |
| Stripe Projects CLI, provisioning | `stripe-projects` | global | COMPLICATED | Project setup |

**Cross-Cutting**

| Task | Skill | Type | Min Gate | Role |
| --- | --- | --- | --- | --- |
| Complexity Gate, Zoom cycle, 10 tools | `thinking-os` | project | COMPLICATED | Classify + Plan |
| Error handling, edge cases | `clean-code` | project | COMPLICATED | Any code |
| Explore unfamiliar code | `codebase-explorer` | project | COMPLICATED | Before modifying |
| Parallel agent dispatch | `worktree-orchestration` | project | COMPLEX | Multi-domain tasks |
| API design, REST patterns | `api-design-principles` | global | COMPLICATED | API work |
| Naming conventions | `naming-analyzer` | global | COMPLEX | Naming review |
| Shell scripts, terminal | `bash-linux` | global | CLEAR | Infra/scripts |
| CI/CD, Docker, deployment | `senior-devops` | global | COMPLICATED | DevOps work |
| Content planning, topics | `content-strategy` | global | COMPLICATED | Content work |
| Template SEO pages | `programmatic-seo` | global | COMPLICATED | SEO at scale |

## Never Skip

- Do NOT rely on "mental review" of skill content — invoke the `Skill` tool explicitly.
- Skills with `globs` auto-load when matching files are edited, but explicit invocation is still required for skills without `globs`.
