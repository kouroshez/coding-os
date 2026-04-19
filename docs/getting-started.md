<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-17 -->
# Getting Started with Coding OS

Purpose: Installation, initialization, and day-to-day workflow for using coding-os in a project.
Read when: Setting up a new project or onboarding a new contributor.
Skip when: You already have a working setup — go to [features.md](./features.md) for the system map, [architecture.md](./architecture.md) for internals.
Read next: [features.md](./features.md) for a one-page overview of every command, [development-roadmap.md](./development-roadmap.md) for current status.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- `jq` (for hook JSON parsing)
- git

## Installation

### 1. Clone coding-os

```bash
git clone <repo-url> ~/coding-os
# or wherever you keep tools
```

### 2. Install the `cos` binary (one-time)

As of v0.2.0 the canonical install path is `uv tool install`:

```bash
uv tool install --editable ~/coding-os
cos --version                # coding-os, version 0.2.0
cos --help                   # 16 commands listed
```

After this, `cos` works from any directory — no aliases required.

> Legacy alias fallback (pre-0.2.0) is still supported but no longer needed:
> ```bash
> alias cos='uv run --directory ~/coding-os python -m cli.main'
> ```

### 3. Initialize a new project

Two modes — both work:

**Interactive** (no flags, prompts for everything):

```bash
cd ~/Desktop
cos init
# ? Agent(s) — comma-separated (claude, codex): claude,codex
# ? Select stacks (comma-separated numbers or names): django,nextjs
# ? Use current directory (Desktop)? [Y/n]: n
# ? Project name (subdirectory): my-shop
# ? Initialize git? [Y/n]: y
```

**Flag-based** (reproducible, CI-friendly — pass `--yes` to skip all prompts):

```bash
# Minimal — Claude adapter, no stack
cos init --agent claude --name my-project --yes

# Both agents at once
cos init --agent claude,codex --template django --name my-api --yes

# Full-stack (Django + Next.js) with both agents
cos init --agent claude,codex --template django --template nextjs --name my-shop --yes

# Single agent — Codex only
cos init --agent codex --template django --name api-codex --yes

# Add an agent to an existing project (after init)
cd my-shop
cos add-adapter codex
```

#### Re-running `cos init` on an existing project

From D.2 onward, `cos init` is idempotent. If the current dir already has a `.coding-os.yaml`, the CLI detects it and offers to sync any missing components (newly-added hooks, fresh skill links, etc.) without overwriting your content. Say "no" to abort.

#### Safety net

The CLI refuses to initialize inside the coding-os repo itself (detected by the presence of `core/thinking-os/server.py` + `cli/main.py`). No accidental self-scatter.

The `--template` flag overlays stack-specific `docs/` content on top of the generic `_base/` scaffold. Each template ships real production-grade playbooks, engineering rules, and design-system docs (ported from the NakoDigital reference project). Multi-template installs merge cleanly — AGENTS.md placeholder substitution handles both stacks in one file.

### 3. What gets created

For `--agent claude,codex --template django --template nextjs`:

```text
your-project/
├── .coding-os/              # State directory (gitignored)
│   ├── thinking-os.db       # Self-learning database (schema v6)
│   ├── domain-config.json   # Domain → REF code mapping for task-create
│   ├── Makefile.base        # Universal make targets (copied from template)
│   └── rag-config.yaml      # RAG indexer configuration (Phase B)
├── .coding-os.yaml          # Project configuration
├── AGENTS.md                # Agent routing protocol (placeholders resolved)
├── Makefile                 # Top-level wrapper that includes .coding-os/Makefile.base
├── .mcp.json                # MCP server registration (thinking-os)
├── .claude/                 # Claude adapter
│   ├── settings.json        # Hook wiring (PreToolUse, PostToolUse, Stop, SessionStart)
│   ├── hooks/               # Symlinks → coding-os/core/hooks/ (20 scripts)
│   ├── rules/               # Symlinks → coding-os/core/rules/
│   ├── skills/              # Symlinks → coding-os/core/skills/ + per-template skills
│   └── commands/            # task.md, review.md, diagnose.md
├── docs/                    # Full scaffold (governance + stack overlays)
│   ├── 00-index.md          # Master navigation hub
│   ├── foundation-map.md    # REF shortcodes with stack-specific entries
│   ├── roadmap.md
│   ├── questions.md
│   ├── tasks.md             # Task index (status SSOT)
│   ├── tasks/               # Task detail files (synced to DB via Phase C)
│   ├── governance/          # 9 files: agent-workflow, task-lifecycle, docs-system, ...
│   ├── PRD/                 # Empty index + 17-section template
│   ├── architecture/        # Empty index + adr/ subdirectory with ADR template
│   ├── api-contracts/       # Empty index + error-format.md
│   ├── ops/                 # Empty index for runbooks
│   ├── engineering/         # Django: backend-rules, naming, logging, secrets-rotation, ...
│   │                        # Next.js: frontend-rules, rendering, i18n, a11y, copywriting, ...
│   ├── playbooks/           # Django: backend-api, security-review, research-validation
│   │                        # Next.js: frontend-ui, content-seo, docs-governance
│   ├── design/              # Next.js: colors-tokens, typography, components, motion-a11y
│   ├── pages-content-spec/  # Next.js: empty index + per-page content specs
│   └── workflow-docs/       # thinking-os-final-edition.md, workflow-guide.md
└── changes.log              # Append-only change history
```

For a minimal `--agent claude` install (no template), most of the `docs/` subdirectories still land as empty index files so you can fill them in as the project grows.

### 4. Verify installation

```bash
cd my-shop
cos doctor          # 14 deep checks
cos health          # quick DB/config check
```

### 5. Bootstrap docs (PRD, architecture, …)

Init gives you the scaffold structure — `cos setup` fills in content. Three modes:

```bash
# Interactive — 4 short questions, writes 4 PRD files
cos setup --mode interactive

# Import an existing PRD document (pure-regex parser, no LLM call)
cos setup --mode import-prd --source ~/my-vision.md --yes

# Skip for now; return later when you have more info
cos setup --mode skip
```

The import-prd mode splits your source file by H2 headings and routes each section to a numbered PRD file (`01-snapshot-vision.md`, `02-goals-kpis.md`, …) based on keywords. Unknown sections land in `99-misc.md`. Existing PRD files are never overwritten.

## Adding Stack Templates to an Existing Project

Use `cos add-stack` — a dedicated idempotent command:

```bash
cd my-project
cos add-stack django        # adds Django to a base-only project
cos add-stack nextjs        # adds Next.js alongside
```

`cos add-stack` mirrors the template content into `.coding-os/templates/<stack>/`, wires stack skills into `.claude/skills/`, regenerates `AGENTS.md` (with a backup), and updates `.coding-os.yaml`.

Stack templates currently available:

- `django` — Django + DRF + PostgreSQL backend with 3 playbooks, 6 engineering rules, `python-django` skill
- `fastapi` — FastAPI + Pydantic + PostgreSQL backend with `python-fastapi` skill
- `go` — Go stdlib + chi backend with `go-patterns` skill
- `nextjs` — Next.js + React + TypeScript frontend with 3 playbooks, 6 engineering rules, 4 design-system files, `nextjs-react` + `frontend-design` skills

## Upgrading When Coding-OS Evolves

When you pull a new coding-os version, every existing project can be re-synced in-place:

```bash
# Pull coding-os updates (upstream)
cd ~/coding-os && git pull && uv tool install --force --editable .

# Then in each project — see what changes:
cd ~/projects/my-shop
cos update --dry-run
# [claude] diff:
#   Added hooks: new-hook.sh
#   Removed skills: deprecated-skill
#   DB: schema v6 → v7 pending

cos update                  # apply
cos doctor                  # verify 14/14 PASS
```

`cos update` never touches `docs/`, `AGENTS.md`, or files you've ejected with `cos eject-file`. It only manages symlinks — user content stays intact.

## Configuration

Edit `.coding-os.yaml` to customize:

```yaml
version: "1.0"
agents: [claude]
templates: []
state_dir: .coding-os
code_extensions: [py, ts, tsx]  # Files that trigger gate enforcement
verify:
  backend: "make lint && make test"
  frontend: "npm run lint"
protected_files:
  - "*/migrations/*.py"
```

## How It Works

### The Core Loop

Every task follows: **Classify → Orient → Plan → Execute → Verify**

1. **Classify** — Rate complexity (CLEAR/COMPLICATED/COMPLEX/CHAOTIC) + count dimensions
2. **Orient** — Read only the files you need, check memory for past experience
3. **Plan** — Analyze each dimension: current state → target → gap → risk
4. **Execute** — Implement the smallest correct change
5. **Verify** — Run domain-specific checks, log completion

### Hook Enforcement

Hooks automatically enforce the workflow:
- Can't write code without recording the Complexity Gate
- Can't write code without invoking a domain skill (COMPLICATED+)
- Can't mark task done without running verification

### Self-Learning

The thinking-os MCP server learns from every session:
- Records observations for every file change
- Extracts patterns from task outcomes
- Suggests relevant patterns for new tasks
- Decays stale patterns automatically

## Workflow for a New Task

### Quick path (make targets — recommended)

```bash
# 1. Start a task — marks status [/], loads context, auto-syncs to tasks table
make task-start TASK=043

# 2. Record the Complexity Gate
bash .claude/hooks/write-state.sh .coding-os/.thinking-os-gate "COMPLICATED 3"

# 3. Invoke the domain skill (Claude only)
#    → Skill skill: "python-django"   (or nextjs-react, clean-code, ...)

# 4. For COMPLICATED+, record the plan checkpoint after framing the problem
bash .claude/hooks/write-state.sh .coding-os/.zoom-checkpoint "PROBLEM_FRAMED"

# 5. Write code — hooks enforce every gate automatically
#    (block-secrets, block-bad-patterns, thinking-os-gate, enforce-skill, enforce-zoom, ...)

# 6. Run verification
make verify-backend   # or your stack-specific target
bash .claude/hooks/record-verify.sh test-backend PASS

# 7. Close the task — writes to changes.log + auto-syncs status to tasks table
make task-done TASK=043 TYPE=feat MSG="Add JWT refresh" WHAT="..." FILES="..."
```

### Using the 3-layer retrieval (Phase A + B + C)

Before starting, the agent should query all three layers:

```python
# Layer 1 — "Have I solved this before?"
cos_search(query="JWT token refresh", limit=5)
cos_learn_suggest(domain="BACKEND", task_description="Add JWT refresh endpoint")

# Layer 2 — "What does the spec say?" (requires `make docs-index` to have run)
cos_doc_search(query="JWT authentication refresh", source_types="prd,architecture,api_contract")

# Layer 3 — "Which tasks are related?" (requires `make task-sync` to have run)
cos_task_search(query="JWT authentication", status="done", limit=5)
cos_task_dependencies(task_id="TASK-043")   # What do I need before starting?
```

### Indexing the knowledge base

Phase B and C require a one-time indexing step (and a refresh whenever docs change):

```bash
# Install the RAG extra (one-time)
uv sync --extra rag

# Pre-download the embedding model (optional — avoids 10s cold start on first query)
make cos-download-model

# Phase B: index docs/ for cos_doc_search (mtime-incremental)
make docs-index

# Phase C: sync docs/tasks/*.md into the tasks table (auto-runs on task-start/done)
make task-sync

# Force a full re-index (e.g. after upgrading the embedding model)
make docs-reindex
make task-resync
```

All four commands are safe to run repeatedly — they're mtime-aware and incremental.

## Migrating from NakoDigital

If you have an existing NakoDigital project:

1. Install coding-os adapter alongside existing `.claude/` setup
2. The `cos-env.sh` has legacy fallback — reads `.claude/.session-id` if `.coding-os/session-id` doesn't exist
3. Gradually move state from `.claude/` to `.coding-os/`
4. Replace `.claude/thinking-os/` MCP server path in `.mcp.json` with coding-os path

## Eject (Self-Contained)

To make a project independent of the coding-os repo:

```bash
uv run --directory ~/coding-os python -m cli.main eject --project-dir .
```

This converts all symlinks to real file copies.

## Known Limitations

- **Codex Write/Edit enforcement is soft.** Codex's PreToolUse only intercepts Bash, so gate/skill/zoom checks for Write/Edit come from `.codex/instructions.md` rather than a blocking hook. Claude gets full hard enforcement.
- **Embedding model is optional.** Without `uv sync --extra rag`, `cos_doc_search` and `cos_task_search` fall back to LIKE or return empty. Existing FTS5 search continues to work.
- **Scale ceiling ~50K vectors.** Current implementation uses numpy brute-force cosine similarity. For >50K chunks (e.g. indexing multiple large external library docs), `hnswlib` or `sqlite-vss` becomes worth the complexity. Roadmap item for v0.3.0.
- **No `coding-os update` yet.** To refresh hook symlinks after a coding-os upgrade, re-run `init`. A proper `update` command is planned for v0.2.0.
- **Pre-existing test failures (3).** `test_review.py::test_multiple_reviews_per_task` (upsert logic predating Phase A) and two `test_server.py::TestSelfTest` tests (test-env DB path issue). All unrelated to Phase A/B/C and documented in `docs/development-roadmap.md`.
