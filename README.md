# coding-os

[![version](https://img.shields.io/badge/version-0.2.0-blue)](./docs/architecture/meta-project.md) [![tests](https://img.shields.io/badge/tests-passing-green)](./tests/) [![cli](https://img.shields.io/badge/cli-cos-informational)](./docs/architecture/meta-project.md)

Agent-agnostic cognitive operating system for AI coding agents.

Teaches AI agents **how to think** (thinking_os) and **how to code** (workflow, hooks, skills, rules).

→ For the canonical system description read **[docs/architecture/meta-project.md](./docs/architecture/meta-project.md)**.

## Architecture

```
coding-os/
├── src/                # All importable code (Python src-layout)
│   ├── cli/              # Factory entrypoint (`cos` command)
│   ├── core/             # Agent-agnostic brain (DNA)
│   │   ├── thinking_os/    # MCP server (self-learning, memory, metrics)
│   │   ├── graph_os/       # Knowledge graph subsystem
│   │   ├── board_os/       # Scrumban task system
│   │   ├── web/            # Hub UI + FastAPI backbone
│   │   ├── hooks/          # Universal hook scripts
│   │   ├── rules/          # Universal rules (dimension-registry + skill-enforcement generated)
│   │   ├── skills/         # Universal skills
│   │   └── scripts/        # Kernel-internal scripts (install-adapter.sh, link-stack-skills.sh)
│   ├── adapters/         # Per-agent translation (mRNA, adapter.yaml manifests)
│   │   ├── claude/         # Claude Code adapter
│   │   ├── codex/          # OpenAI Codex adapter
│   │   └── cursor/         # Cursor IDE adapter
│   ├── templates/        # Per-stack data (phenotype, each stack = one stack.yaml)
│   │   ├── _base/          # Generic project base + fragments/
│   │   ├── django/         # Django + DRF + PostgreSQL
│   │   ├── nextjs/         # Next.js + React + TypeScript
│   │   ├── fastapi/        # FastAPI + Pydantic
│   │   ├── go/             # Go stdlib + chi
│   │   ├── go-fiber/       # Go + Fiber (gofiber/fiber v2)
│   │   ├── react-native/   # React Native + Expo
│   │   ├── python/         # Python library / CLI / MCP server
│   │   └── meta/           # Meta-stack (coding-os contributors)
│   └── scripts/          # Maintenance + regen tooling
├── tests/              # Test suite (Python convention: root, not shipped in wheel)
├── docs/               # Meta-repo development docs
└── .coding-os/         # Runtime state (gitignored)
```

**Zero-hardcoding contract**: adding a new stack or a new agent is a pure
YAML + Markdown change. No Python edits required. See *Adding a new stack*
below.

## Install

```bash
# One-time, globally (editable mode)
uv tool install --editable ~/coding-os
cos --version                # coding-os, version 0.2.0
```

## Quick Start

```bash
# 1a. Interactive — no flags, prompts for everything
cos init

# 1b. Flag-based — reproducible, CI-friendly
cos init --agent claude,codex --template django --template nextjs --name my-shop --yes

cd my-shop

# 2. Bootstrap docs (PRD) — three modes: interactive / import-prd / skip
cos setup                                # prompts for mode
cos setup --mode import-prd --source ~/my-vision.md --yes

# 3. Deep health check (14 checks)
cos doctor
cos doctor --format json --strict

# 4. After pulling a new coding-os version, sync every project
cos update --dry-run         # see what will change
cos update                   # apply

# 5. Grow the project
cos add-stack fastapi        # add a second backend stack
cos add-adapter codex        # add an agent later

# 6. Fine-grained customization
cos eject-file docs/workflow/workflow-guide.md   # one file → real copy
cos eject                                              # all symlinks → real copies
```

## Command Index (16 commands)

**Project lifecycle**: `init` · `setup` · `add-adapter` · `add-stack` · `update` · `eject` · `eject-file`
**Diagnostics**: `doctor` · `health` · `list-stacks` · `list-adapters` · `hooks-dir`
**Brain**: `docs-index` · `task-sync` · `reindex` · `server-start`

Full catalogue with flows and use-case guide: [docs/architecture/meta-project.md](./docs/architecture/meta-project.md).

## What It Does

1. **Complexity Gate** — Classifies problems before acting (Cynefin: CLEAR/COMPLICATED/COMPLEX/CHAOTIC)
2. **Cognitive Cycle** — CLASSIFY → ORIENT → PLAN → EXECUTE → VERIFY
3. **Self-Learning** — SQLite v6 DB tracks patterns, metrics, outcomes, and breakthroughs across sessions
4. **Hook Enforcement** — 9 pre-tool-use gates block unsafe code changes (secrets, missing gates, missing skill, stale verify)
5. **Three-Layer Retrieval** — agent memory (`cos_search`) · doc RAG (`cos_doc_search`) · task graph (`cos_task_*`)
6. **Upgrade Path** — `cos update` keeps every project in sync with coding-os without touching user content

## Supported Agents

| Agent | Hook Enforcement | Skills | MCP Server |
|-------|-----------------|--------|------------|
| Claude Code | Full (PreToolUse Write/Edit) | Native Skill tool | Yes |
| Codex | Partial (PreToolUse Bash only) | Via instructions.md | Yes |

## MCP Tools (21 tools, `cos_*` prefix)

- **Health**: `cos_health`
- **Memory**: `cos_search` · `cos_timeline` · `cos_details` · `cos_promote`
- **Metrics**: `cos_metric_record` / `query` / `trend`
- **Learning**: `cos_learn_extract` / `suggest` / `validate` / `feedback` / `narrative`
- **Routing**: `cos_route_model` · `cos_route_skill`
- **Graph**: `cos_graph`
- **Docs RAG** (Phase B): `cos_doc_search`
- **Task Registry** (Phase C): `cos_task_search` · `cos_task_dependencies` · `cos_task_dependents` · `cos_task_by_filter`

The server is started automatically via `.mcp.json` → `cos server-start`.

## Configuration

`.coding-os.yaml` at project root:

```yaml
version: "1.0"
agents: [claude, codex]
templates: []
state_dir: .coding-os
code_extensions: [py, ts, tsx]
verify:
  backend: "make lint-backend && make test-backend"
  frontend: "cd frontend && npm run lint"
protected_files:
  - "*/migrations/*.py"
```

## Adding a new stack (zero Python changes)

A stack is a directory under `src/templates/<id>/` containing a `stack.yaml`
manifest plus any skills, rules, playbooks, and scaffold docs it contributes.
The CLI auto-discovers stacks — no code edits are needed.

**Minimum viable stack**:

```
src/templates/myrails/
├── stack.yaml                                    # REQUIRED
├── skills/ruby-rails/SKILL.md                    # primary skill
├── rules/backend.md                              # path-scoped rules (YAML frontmatter)
└── scaffold/docs/
    ├── playbooks/rails-service.md
    └── engineering/rails-rules.md
```

**`stack.yaml` schema** (see `src/templates/fastapi/stack.yaml` for the full example):

```yaml
version: 1
id: myrails
label: "Ruby on Rails"
category: backend
primary_skill: ruby-rails
skills: [ruby-rails]

substitutions:
  DOMAIN_ROUTES: "Backend→`docs/playbooks/rails-service.md`"
  SKILL_ROUTES: "Backend→`ruby-rails`"
  VERIFY_BACKEND: "`bundle exec rake test`"
  # …

rules:
  - {file: rules/backend.md, globs: ["app/**/*.rb"]}

dimensions:
  - {name: "ActiveRecord model", read_files: ["docs/engineering/rails-rules.md"]}

skill_enforcement:
  - {globs: ["app/**/*.rb"], primary: ruby-rails, secondary: [clean-code]}

makefile_targets:
  - {name: test-backend, cmd: "bundle exec rake test"}
```

After creating the directory, run:

```bash
cos list-stacks                       # myrails now appears
make manifest-regen                   # update src/core/scaffold_manifest.json
make regen-rules                      # update src/core/rules/{dimension-registry,skill-enforcement}.md
cos init --agent claude,codex --template myrails --name proof
cos doctor -d proof                   # 12 checks, all green
```

The same pattern works for new **adapters** — create
`src/adapters/<id>/adapter.yaml` + an `install.sh`, and `cos list-adapters`
picks it up.

## Development commands

```bash
make eval-operational         # full end-to-end evaluation in .build/
make debug-init               # named debug sandbox under .build/debug/
make debug-doctor             # run doctor on the debug sandbox
make manifest-regen           # refresh src/core/scaffold_manifest.json
make regen-rules              # refresh auto-generated rule docs
make regen-doctor-schema      # refresh expected_tables snapshot in doctor-config.yaml
```

## Documentation

| Doc | What's in it |
|---|---|
| [AGENTS.md](./AGENTS.md) | **Agent entry point** — Core Loop, Critical Rules, Verification Matrix, Tool Routing |
| [docs/architecture/meta-project.md](./docs/architecture/meta-project.md) | Hexagonal design, DNA/mRNA/phenotype layers, propagation matrix |
| [docs/governance/critical-rules.md](./docs/governance/critical-rules.md) | 22 critical rules with rationale + repair steps |
| [docs/governance/docs-system.md](./docs/governance/docs-system.md) | Doc taxonomy, naming, header contract |
| [docs/governance/agent-workflow.md](./docs/governance/agent-workflow.md) | Domain routing, task protocol, memory contract |
| [docs/workflow/workflow-guide.md](./docs/workflow/workflow-guide.md) | Daily workflow quick-start |
| [docs/playbooks/](./docs/playbooks/) | Hook authoring · Adapter authoring · Template authoring · MCP tool authoring |
| [docs/engineering/](./docs/engineering/) | graph_os queries · hook reference · template enforcement |
| [docs/adapters/](./docs/adapters/) | Claude SDK · Codex CLI · Cursor IDE integration |
