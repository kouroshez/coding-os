# coding-os

[![version](https://img.shields.io/badge/version-0.3.0-blue)](./CHANGELOG.md)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](./pyproject.toml)
[![tests](https://img.shields.io/badge/tests-1195%20passing-green)](./tests/)
[![cli](https://img.shields.io/badge/cli-cos-informational)](./docs/architecture/meta-project.md)

> **Agent-agnostic cognitive operating system for AI coding agents.**
> Teaches AI agents *how to think* (thinking_os) and *how to code*
> (workflow, hooks, skills, rules) — packaged so the same kernel
> serves Claude Code, OpenAI Codex, and Cursor without rewriting.

---

## 60-second quickstart

```bash
# 1. Install
git clone https://github.com/kouroshebra/coding-os.git
cd coding-os
uv tool install --editable .          # installs the `cos` CLI globally

# 2. Verify
cos --version                          # → cos 0.3.0
cos doctor                             # 14-point health check

# 3. Spawn a new project, scaffolded with one agent + one stack
cos init --agent claude --template django --name my-shop --yes
cd my-shop

# 4. Boot the multi-project Web Hub (graph + board + cognition + search)
cos hub start                          # → http://127.0.0.1:9188
```

Open `http://127.0.0.1:9188` in your browser. You will see the
knowledge graph of `my-shop`, the Scrumban board, the cognition
trace timeline, and unified search across all retrieval layers.

For Codex or Cursor, swap `--agent claude` for `--agent codex` or
`--agent cursor` — everything else is identical.

---

## What it is

`coding-os` is a three-layer composition (DNA → mRNA → phenotype):

```
src/core/  ──►  src/adapters/<agent>/  ──►  src/templates/<stack>/  ──►  consumer project
(DNA)         (mRNA)                       (phenotype)                 (organism)
```

| Layer            | What it owns                                                       |
| ---------------- | ------------------------------------------------------------------ |
| `src/core/`      | MCP server, hooks (62), rules, skills — **agent-agnostic, stack-agnostic** |
| `src/adapters/`  | Per-agent translation: `.claude/`, `.codex/`, `.cursor/` rendering |
| `src/templates/` | Per-stack overlays: Django, Next.js, FastAPI, Go, Go+Fiber, React Native, Python, Meta |
| `src/cli/`       | The `cos` factory CLI that composes the three layers               |

Adding a new stack or a new agent is a pure YAML + Markdown change.
No Python edits required.

## What it does

1. **Complexity Gate** — classifies problems before acting (Cynefin:
   CLEAR / COMPLICATED / COMPLEX / CHAOTIC / CONFUSION).
2. **Cognitive Cycle** — CLASSIFY → ORIENT → PLAN → EXECUTE → VERIFY.
   The kernel rule (`src/core/rules/thinking_os.md`) is always
   active; the deep skill loads only when the gate returns COMPLICATED
   or COMPLEX.
3. **Self-learning memory** — SQLite-backed observations, metrics,
   and learned patterns across sessions (`cos_search`, `cos_learn_*`).
4. **Hook enforcement** — 62 hooks gate writes, edits, prompts,
   sessions, and stops. Adapter parity matrix in `docs/engineering/`.
5. **Four-layer retrieval** — agent memory (`cos_search`) · doc RAG
   (`cos_doc_search`) · task graph (`cos_task_*`) · knowledge graph
   (`cos_graph_*`).
6. **Intent enforcement** — when the user uses exhaustive vocabulary
   (FA + EN:  / all / completely / until done), the Stop hook
   refuses premature "done" until an evidence bundle is recorded.
7. **Upgrade path** — `cos update` keeps every consumer project in
   sync with `coding-os` without touching user content.

## Web Hub (`http://127.0.0.1:9188`)

A singleton FastAPI + Vite/React SPA that serves every registered
project via `/api/p/<slug>/*`:

- **Graph** — Sigma.js canvas with three views (Overview, Tree,
  Code) + smart export + dagre layout.
- **Board** — Scrumban (kind × swimlane × epic) with WIP enforcement.
- **Cognition** — JSONL trace timeline + replay with audit-mode
  guardrails.
- **Search** — unified across memory, docs, tasks, graph.

`cos hub start` boots the hub. `cos hub status` reports health.
Source: `src/core/web/`. UI: `src/core/web/ui/` (`npm run dev`).

## Architecture

```
coding-os/
├── src/                # All importable code (Python src-layout)
│   ├── cli/              # Factory entrypoint (`cos` command)
│   ├── core/             # Agent-agnostic brain (DNA)
│   │   ├── thinking_os/    # MCP server: memory, learning, metrics, cognition
│   │   ├── graph_os/       # Polyglot knowledge graph (SQLite backend)
│   │   ├── board_os/       # Scrumban task system
│   │   ├── web/            # Hub UI + FastAPI backbone
│   │   ├── hooks/          # 62 hook scripts (SSOT: registry.yaml)
│   │   ├── rules/          # Always-active rules + auto-generated artifacts
│   │   ├── skills/         # Universal skills
│   │   └── scripts/        # Kernel-internal regen tooling
│   ├── adapters/         # Per-agent translation (mRNA, adapter.yaml manifests)
│   │   ├── claude/         # Claude Code adapter (58/62 hooks fire)
│   │   ├── codex/          # OpenAI Codex CLI adapter (21/62 — Bash-only)
│   │   └── cursor/         # Cursor IDE adapter (59/62 hooks fire)
│   ├── templates/        # Per-stack scaffolds (phenotype, stack.yaml-driven)
│   │   ├── _base/          # Generic base + fragments/
│   │   ├── django/         # Django + DRF + PostgreSQL
│   │   ├── nextjs/         # Next.js + React + TypeScript + Tailwind
│   │   ├── fastapi/        # FastAPI + Pydantic + SQLAlchemy
│   │   ├── go/             # Go stdlib + chi router
│   │   ├── go-fiber/       # Go + Fiber v2
│   │   ├── react-native/   # React Native + Expo
│   │   ├── python/         # Python library / CLI / MCP server
│   │   └── meta/           # Meta-stack (for coding-os contributors)
│   └── scripts/          # Maintenance + regen tooling
├── tests/              # 743 cross-cutting tests
├── docs/               # Governance, engineering, playbooks, architecture
└── .coding-os/         # Per-project runtime state (gitignored)
```

## Command index (22 commands)

```
Project lifecycle    init · setup · add-adapter · add-stack · update · eject · eject-file
Diagnostics          doctor · health · list-stacks · list-adapters · hooks-dir · hooks-log
Brain                docs-index · task-sync · reindex · server-start
Hub                  hub start · hub status · hub stop
Board                board · task-show · task-create · task-start · task-move · task-done · daily · retro · wip
Cognition            cognition trace · cognition trace-replay · cognition trace-summary
Graph                graph-reindex · graph-viz · graph-doctor
```

Full catalogue with flows: [docs/architecture/meta-project.md](./docs/architecture/meta-project.md).

## Slash commands (20 commands)

The `cos` CLI above is the *factory*. Inside an agent session you also get
**slash commands** — packaged workflows invoked by typing `/`. They ship in
`.claude/commands/` (and `.codex/commands/`), are version-controlled, and are
available to every teammate on clone.

```
Scrumban     /board · /daily · /retro · /task
Cognition    /classify · /memory-search
Quality      /verify · /review · /diagnose
Roles (11)   /role-researcher · /role-analyst · /role-architect · /role-documenter
             /role-implementer · /role-reviewer · /role-debugger · /role-security_auditor
             /role-deployer · /role-observer · /role-refactorer
```

The 9 workflow commands are sourced from [src/core/commands/](./src/core/commands/);
the 11 `/role-*` commands from [src/core/thinking_os/agents/](./src/core/thinking_os/agents/)
(the semantic roles of the cognition chain). Day-to-day usage:
[docs/workflow/workflow-guide.md](./docs/workflow/workflow-guide.md).

## MCP tools (79 tools, all `cos_*` prefix, all `ok / fail` envelope)

| Family       | Examples                                                          |
| ------------ | ----------------------------------------------------------------- |
| Health       | `cos_health`                                                      |
| Memory       | `cos_search` · `cos_timeline` · `cos_details` · `cos_promote`     |
| Learning     | `cos_learn_extract` · `cos_learn_suggest` · `cos_learn_validate`  |
| Metrics      | `cos_metric_record` · `cos_metric_query` · `cos_metric_trend`     |
| Routing      | `cos_route_model` · `cos_route_skill`                             |
| Docs         | `cos_doc_search` · `cos_doc_header` · `cos_doc_headers_by`        |
| Tasks        | `cos_task_search` · `cos_task_board` · `cos_task_move` (+ 13 more) |
| Graph        | `cos_graph_query` · `cos_graph_references` · `cos_graph_impact` · `cos_graph_rename_plan` (+ 12 more) |
| Cognition    | `cos_analyze_task` · `cos_compose_chain` · `cos_supervise` · `cos_backtrack_log` |
| Retrieval    | `cos_retrieve` (auto-router across all layers)                    |

Per-tool docs + envelope spec: [docs/governance/mcp-tool-inventory.md](./docs/governance/mcp-tool-inventory.md).

The MCP server is launched by `.mcp.json` → `cos server-start`.

## Supported agents

| Agent           | Hook coverage | Skills              | MCP server | Notes                          |
| --------------- | ------------- | ------------------- | ---------- | ------------------------------ |
| Claude Code     | 58/62 ✅       | Native Skill tool   | ✅          | Most complete enforcement.     |
| Cursor (Agent)  | 59/62 ✅       | Via instructions    | ✅          | Tied with Claude Code.         |
| Codex CLI       | 21/62 ⚠️       | Via instructions    | ✅          | Bash-only PreToolUse matcher.  |
| Codex GUI       | 0/62 ❌        | Via instructions    | ✅          | `.codex/hooks.json` ignored upstream — do NOT use for protected work. |

Audit + reasoning: [docs/engineering/workflow-audit-2026-04-25.md](./docs/engineering/workflow-audit-2026-04-25.md).

## Configuration

`.coding-os.yaml` at every project root:

```yaml
version: "1.0"
agents: [claude, codex]
templates: [django, nextjs]
state_dir: .coding-os
code_extensions: [py, ts, tsx]
verify:
  backend: "make lint-backend && make test-backend"
  frontend: "cd src/frontend && npm run lint && npm test"
protected_files:
  - "*/migrations/*.py"
```

## Adding a new stack (zero Python changes)

Create `src/templates/<id>/stack.yaml` plus any skills, rules,
playbooks, and scaffold docs. The CLI auto-discovers stacks.

Minimum viable stack:

```
src/templates/myrails/
├── stack.yaml                                    # REQUIRED
├── skills/ruby-rails/SKILL.md                    # primary skill
├── rules/backend.md                              # path-scoped rules
└── scaffold/docs/
    ├── playbooks/rails-service.md
    └── engineering/rails-rules.md
```

`stack.yaml` schema example: `src/templates/fastapi/stack.yaml`.

After creating the directory:

```bash
cos list-stacks                       # myrails now appears
make manifest-regen                   # update src/core/scaffold_manifest.json
make regen-rules                      # update auto-generated rule artifacts
cos init --agent claude --template myrails --name proof
cos doctor -d proof                   # health check
```

The same pattern works for new **adapters** — create
`src/adapters/<id>/adapter.yaml` + `install.sh`, and `cos list-adapters`
picks it up.

## Project structure (for contributors)

```bash
make verify-hooks         # shellcheck + bash -n on every hook
make verify               # matrix-targeted tests for what changed
make test-mcp             # MCP self-test (cold start)
make docs-lint            # markdown structure + link integrity
cos health                # cross-project health summary
make manifest-regen       # refresh src/core/scaffold_manifest.json
make regen-rules          # refresh dimension-registry + skill-enforcement
```

CI runs the matrix on every PR. See `.github/workflows/ci.yml`.

## Documentation

| Doc                                                                                 | What's in it                                                |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [AGENTS.md](./AGENTS.md)                                                            | **Agent entry point** — Core Loop, Critical Rules, Verification Matrix |
| [docs/architecture/meta-project.md](./docs/architecture/meta-project.md)            | Hexagonal design, DNA/mRNA/phenotype, propagation matrix    |
| [docs/governance/critical-rules.md](./docs/governance/critical-rules.md)            | 22 critical rules with rationale + repair steps             |
| [docs/governance/mcp-tool-inventory.md](./docs/governance/mcp-tool-inventory.md)    | Per-tool spec + envelope contract                           |
| [docs/governance/agent-workflow.md](./docs/governance/agent-workflow.md)            | Domain routing, task protocol, memory contract              |
| [docs/engineering/intent-vocabulary.md](./docs/engineering/intent-vocabulary.md)    | Exhaustive-intent predicates (FA + EN)                      |
| [docs/engineering/graph_os-queries.md](./docs/engineering/graph_os-queries.md)      | When to query the graph vs grep                             |
| [docs/engineering/hub-architecture.md](./docs/engineering/hub-architecture.md)      | Hub: FastAPI ↔ React SPA contract                           |
| [docs/playbooks/](./docs/playbooks/)                                                | Hook authoring · adapter authoring · template authoring · MCP tool authoring |
| [docs/adapters/](./docs/adapters/)                                                  | Claude SDK · Codex CLI · Cursor IDE integration             |
| [CONTRIBUTING.md](./CONTRIBUTING.md)                                                | Setup, contribution loop, PR checklist                      |
| [SECURITY.md](./SECURITY.md)                                                        | Vulnerability disclosure policy                             |
| [CHANGELOG.md](./CHANGELOG.md)                                                      | Release notes                                               |

## License

Apache License 2.0 — see [LICENSE](./LICENSE). Copyright 2026
Kourosh Ebrahimzadeh and coding-os contributors.

Pre-public development history is archived locally under
`archive/full-history` and the tag `archive/pre-public-2026-05-20`
for auditability; it is not part of the public history that begins
with the 0.3.0 release.
