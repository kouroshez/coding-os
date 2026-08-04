# coding-os

[![release](https://img.shields.io/badge/release-v0.3.2)](https://github.com/kouroshez/coding-os/releases) <!-- x-release-please-version -->
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](./LICENSE)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](./pyproject.toml)
[![tests](https://img.shields.io/badge/tests-passing-green)](./tests/)
[![cli](https://img.shields.io/badge/cli-cos-informational)](./docs/architecture/meta-project.md)

> **Coding OS — the cognitive operating system that gives AI agents memory, structure, and discipline.**
> Teaches AI agents *how to think* (thinking_os) and *how to code*
> (workflow, hooks, skills, rules) — agent-agnostic so the same kernel
> serves Claude Code and OpenAI Codex without rewriting.
>
> Website: <https://coding-os.dev> · Community: <https://community.coding-os.dev>

---

## Prerequisites

| Tool | Min version | Why | macOS install |
|---|---|---|---|
| Python | 3.10 | CLI, MCP server, extractors | `brew install python@3.12` |
| [uv](https://docs.astral.sh/uv/) | 0.5 | Fast Python installer + tool runner | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Bash | 4 | Hook scripts use 4.x features (macOS ships 3.2) | `brew install bash` |
| Node.js | 20 | **Only** if rebuilding the Hub UI under `src/core/web/ui/` | `brew install node@20` |
| Docker | 24 | **Only** for the Docker quickstart below | `brew install --cask docker` |

Linux: replace `brew install …` with your distro's package manager
(`apt`, `dnf`, `pacman`). Windows: WSL 2 + the same Linux steps.

## Quickstart — panel first (one command)

If you would rather click than type, this is the whole install. It preflights
prerequisites, installs the `cos` CLI, and boots the Hub:

```bash
curl -fsSL https://raw.githubusercontent.com/kouroshez/coding-os/main/install.sh | bash
# …or, from a checkout:  bash install.sh
```

Open the Hub at `http://127.0.0.1:9188` and press **New project**. The Composer picks a
preset (or your own stack mix), asks one sentence about the project, and
scaffolds it — docs, board, knowledge graph, and agent setup included. There is
no CLI step in between; everything below is the same flow with flags instead of
clicks. ([ADR-0007](docs/architecture/adr/0007-gui-first-install-path.md))

## 60-second quickstart (native `uv`)

```bash
# 1. Install the `cos` CLI globally
git clone https://github.com/kouroshez/coding-os.git
cd coding-os
uv tool install --editable .

# 2. Verify
cos --version                          # → coding-os, version X.Y.Z
cos doctor --bootstrap                 # preflight: python/bash/git/uv/sed prerequisites
cos doctor                             # full health sweep (must be all-green)

# 3. Spawn a new project, scaffolded with an agent + a stack
#    (--agent takes several: --agent claude,codex)
cos init --agent claude --template django --name my-shop --yes
cd my-shop                             # adapter installer ran for you and wrote
                                       # .claude/, .mcp.json, .coding-os/

# 4. Boot the multi-project Web Hub (graph + board + cognition + search)
cos hub start                          # → http://127.0.0.1:9188
```

Open `http://127.0.0.1:9188` in your browser. You will see the
knowledge graph of `my-shop`, the Scrumban board, the cognition
trace timeline, and unified search across all retrieval layers.

For Codex, swap `--agent claude` for `--agent codex` (or pass
both — `--agent claude,codex`) — everything else is identical. Each agent's
installer is `src/adapters/<agent>/install.sh`; `cos init` runs it
for you and re-runs it on `cos update`.

### Choosing how much coding-os you install

The kernel ships as **subsystem modules** — docs, tasks (Scrumban), knowledge
graph, agent memory, cognition, observability, hub extras, CI/CD — and you pick
the set at create time. Prefer a small MCP surface, or don't want the web panel
at all? Start lean:

```bash
cos init --agent claude --name my-app --profile lite --yes   # kernel only: discipline + safety
cos init --agent claude --name my-app --profile full --yes   # every subsystem
cos init --agent claude --name my-app --disable-module memory --yes
```

`cos init --help` lists the live profiles and module ids (both are read from
`src/core/subsystems.yaml`, so the help never drifts). Omitting `--profile`
applies the registry default — today `standard`, which leaves `cognition` and
`cicd` off. The two flags are **unioned**: a profile can only remove more, so to
re-enable something start from a wider profile. Everything stays adjustable
later with `cos module enable|disable` or Hub **Config → Modules**, and the same
chips appear in the Composer's *Advanced* section. Full model:
[meta-project.md § subsystem modules](docs/architecture/meta-project.md).

## Run with Docker (Hub layer; native for projects)

**Architecture split** — adopted because each layer wants a different
deploy shape:

| Layer | Runs where | Why |
|---|---|---|
| **Hub** (web panel: graph · board · cognition · search) | **Docker** (production-shaped) | Reproducible build · isolated runtime · same image dev → CI → prod |
| **Consumer projects** (each project's `.coding-os/`, MCP server, skills, adapters) | **Host (native)** | Agent runtimes (Claude Code / Codex CLI) live on the host filesystem · `cos init` factory writes alongside your source · IDE/editor needs direct paths |

The Hub container **reads** the host's projects via a read-only bind
mount and the host's registry file, so every absolute path stays
valid inside the container — no path translation.

### Quickstart

```bash
docker compose up
# → http://127.0.0.1:9188
```

By default, `docker-compose.yml` bind-mounts `$HOME` read-only at
the same path inside the container so `cos registry scan ~` finds
every `.coding-os/` directory below it. Hub state (SQLite, traces)
lives in the `cos-state` named volume and survives `down` / `up`.

Project auto-discovery, narrowing the mount for production, and manual
`docker run` (no compose): [docs/engineering/hub-architecture.md § Docker
deployment](./docs/engineering/hub-architecture.md#docker-deployment-hub-layer).

## MCP server wire-up (Claude / Codex)

`cos init` writes `.mcp.json` at the project root automatically. If
you ever need to register the MCP server manually (e.g. another tool
that reads MCP configs), this is the shape every adapter installs:

```json
{
  "mcpServers": {
    "coding-os": { "command": "cos", "args": ["server-start"] }
  }
}
```

Verify the wire is live in your agent runtime:

- **Claude Code:** `cos doctor` shows `mcp.coding-os = ok`; the CLI
  exposes `cos_*` tools via `ToolSearch("select:<tool>")`.
- **Codex CLI:** `codex --mcp-list` lists `coding-os`.

If the server isn't found, re-run `bash src/adapters/<agent>/install.sh`
from the project root, then restart the agent.

---

## What it is

`coding-os` is a three-layer composition (DNA → mRNA → phenotype):

```
src/core/  ──►  src/adapters/<agent>/  ──►  src/templates/<stack>/  ──►  consumer project
(DNA)         (mRNA)                       (phenotype)                 (organism)
```

| Layer            | What it owns                                                       |
| ---------------- | ------------------------------------------------------------------ |
| `src/core/`      | MCP server, hooks, rules, skills — **agent-agnostic, stack-agnostic** |
| `src/adapters/`  | Per-agent translation: `.claude/`, `.codex/` rendering             |
| `src/templates/` | Per-stack overlays: 27 stacks — Django, Next.js, FastAPI, Laravel, Rails, Flutter, Go, Rust, … (`cos list-stacks`) |
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
4. **Hook enforcement** — hooks gate writes, edits, prompts,
   sessions, and stops (exact count in `src/core/hooks/registry.yaml`).
   Adapter parity matrix in `docs/engineering/`.
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

- **Workspace** — project overview, Scrumban board (kind × swimlane ×
  epic, WIP enforcement), memory, cognition traces, unified search.
- **Graph** — Sigma.js canvas with deliberate view modes + smart
  export + dagre layout.
- **Config** — modules, git settings, hub settings, per-project chips.
- **Marketplace** — community skills/stacks (rolling out).
- **Diagnostics** — health, hooks log, token-burn audit.

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
│   │   ├── hooks/          # Hook scripts (SSOT: registry.yaml)
│   │   ├── rules/          # Always-active rules + auto-generated artifacts
│   │   ├── skills/         # Universal skills
│   │   └── scripts/        # Kernel-internal regen tooling
│   ├── adapters/         # Per-agent translation (mRNA, adapter.yaml manifests)
│   │   ├── claude/         # Claude Code adapter
│   │   └── codex/          # OpenAI Codex CLI/Desktop adapter
│   ├── templates/        # Per-stack scaffolds (phenotype, stack.yaml-driven)
│   │   ├── _base/          # Generic base + fragments/
│   │   ├── django/         # Django + DRF + PostgreSQL
│   │   ├── nextjs/         # Next.js + React + TypeScript + Tailwind
│   │   ├── fastapi/        # FastAPI + Pydantic + SQLAlchemy
│   │   ├── go/             # Go stdlib + chi router
│   │   ├── go-fiber/       # Go + Fiber v3
│   │   ├── react-native/   # React Native + Expo
│   │   ├── python/         # Python library / CLI / MCP server
│   │   ├── meta/           # Meta-stack (for coding-os contributors)
│   │   └── …               # 27 stacks total — `cos list-stacks`
│   └── scripts/          # Maintenance + regen tooling
├── tests/              # cross-cutting tests
├── docs/               # Governance, engineering, playbooks, architecture
└── .coding-os/         # Per-project runtime state (gitignored)
```

## Command index (highlights · 98 `cos` subcommands total)

```
Project lifecycle    init · adopt · setup · add-adapter · add-stack · update · materialize · eject
Diagnostics          doctor · health · list-stacks · list-adapters · hooks-dir · hooks-log
Hub                  hub start · hub status · hub stop
Board                board · task-create · task-start · task-move · task-done · daily · retro · wip
Cognition            cognition trace · trace-replay · trace-summary
Graph                29 graph-* subcommands (build · find · deps · analysis · review);
                     22 mirror a cos_graph_* MCP tool one-for-one, enforced by a parity test
```

Full catalogue with flows: [docs/architecture/meta-project.md](./docs/architecture/meta-project.md).

## Slash commands (25 commands)

The `cos` CLI above is the *factory*. Inside an agent session you also get
**slash commands** — packaged workflows invoked by typing `/`: 11 workflow
commands (`/board`, `/daily`, `/retro`, `/task`, `/classify`, `/compose`,
`/memory-search`, `/verify`, `/review`, `/diagnose`, `/new-project`) and 14
`/role-*` commands (the semantic roles of the cognition chain). They ship in
`.claude/commands/` (and `.codex/commands/`) and are version-controlled, so
every teammate gets them on clone. Day-to-day usage:
[docs/workflow/workflow-guide.md](./docs/workflow/workflow-guide.md).

## MCP tools (`cos_*` family, all `ok / fail` envelope)

One MCP server (launched by `.mcp.json` → `cos server-start`) exposes every
`cos_*` tool across ten families: health, memory (`cos_search`), learning,
metrics, routing, docs (`cos_doc_search`), tasks (`cos_task_*`), graph
(`cos_graph_*`, 22 tools), cognition (`cos_compose_chain`), and retrieval.
Per-tool docs + envelope spec:
[docs/governance/mcp-tool-inventory.md](./docs/governance/mcp-tool-inventory.md).

## The knowledge graph — why it changes the economics

Most "AI coding" tools answer structural questions ("who calls this?",
"what breaks if I rename it?", "where does this data flow?") by *reading
files* until the agent guesses an answer. That burns tokens, slows the
loop, and produces hallucinations the moment a caller lives in a file
the agent didn't open.

coding-os ships a precomputed knowledge graph as the **third retrieval
layer** alongside memory and docs. Every commit refreshes 23 node kinds
(functions, methods, classes, modules, routes, MCP tools, docs,
headings, frontmatter, hooks, rules, skills, tasks, …) and 18 edge
types (`contains`, `calls`, `imports`, `inherits_from`,
`handles_route`, `has_param_type`, `references_doc`, `is_decorated_by`,
`links_to`, …). The agent then asks the graph — `cos_graph_references`,
`cos_graph_impact`, `cos_graph_rename_plan` — and gets a small,
high-confidence JSON envelope back.

### Benchmark — graph vs read-the-file (live repo · 33,548 nodes · 72,797 edges)

"What breaks if I change X?" answered two ways — read **every caller
file** to be *sure* you caught them all (the safe manual path), vs one
`cos_graph_*` envelope. Token counts are **measured** on this codebase
(file bytes ÷ 4; tool `tokens_estimated` from the live envelope):

| Question | Graph tool (result) | Manual: read all callers | Graph envelope | **Savings** |
|---|---|---:|---:|---:|
| What breaks if `init_db` changes? | `cos_graph_impact` — 508 impacted | 100 files ≈ 456,000 tok | **7,962 tok** | **98.3%** |
| Who must a `GraphNode` rename touch? | `cos_graph_rename_plan` — 118 sites, risk=high | 26 files ≈ 170,000 tok | **7,519 tok** | **95.6%** |
| Who sources `cos-env.sh`? | `cos_graph_references` — 79 refs | grep + open each hook | **579 tok** | ~99% |

The exact numbers shift per machine and per tokenizer — the **ratio**
(roughly 20–100× less context) is what holds. The leanest queries
(`cos_graph_references(limit=20)`) answer in 140–600 tokens vs 2K–24K
for even a *single* file Read. Every envelope carries `total_count` +
`truncated`, so the agent knows when it has the whole answer — no silent
truncation.

The savings compound: an agent asking 50 structural questions over a
feature spends ~50–400 KB of context, not the multiple MB an exhaustive
file sweep would cost — leaving the budget for actual reasoning.

### Coverage, budgets, health — the anti-hallucination contract

Every coverage-sensitive tool reports its own incompleteness
(`total_count` · `result_truncated` · `walk_truncated` — never silent),
all 23 node kinds answer end-to-end in 0–23 ms, `cos_graph_doctor`
sweeps stale nodes, and every Write/Edit re-indexes just the touched
file. The full contract — budget knobs, per-kind latency, Hub view
modes, and the probe-then-widen workflow — lives in
[graph_os-queries.md § Coverage, budgets, and benchmarks](./docs/engineering/graph_os-queries.md#coverage-budgets-and-benchmarks-readme-deep-dive).

Deep dive: [docs/engineering/graph_os-queries.md](./docs/engineering/graph_os-queries.md)
· [docs/engineering/graph-hallucination-cures.md](./docs/engineering/graph-hallucination-cures.md)
· [docs/governance/mcp-tool-inventory.md](./docs/governance/mcp-tool-inventory.md).

## Supported agents

| Agent | Hook coverage | Skills | MCP server | Notes |
| --- | --- | --- | --- | --- |
| Claude Code | Full for its native events ✅ | Native skills | ✅ | No native `SessionEnd`. |
| Codex CLI | Full for supported Codex events ✅ | Native agent skills | ✅ | Includes Bash, Read, `apply_patch`, MCP, prompt, compact, subagent, permission, Stop, and SessionEnd hooks. |
| Codex Desktop | Same project hook/config contract as Codex CLI ✅ | Native agent skills | ✅ | Project hooks require trust/review; Hub observability is native, while Hub interactive chat is still Claude-only. |

Parity matrix + reasoning: [docs/engineering/adapter-parity.md](./docs/engineering/adapter-parity.md)
(the 2026-04-25 workflow audit is a historical snapshot predating Codex parity).

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

Create `src/templates/<id>/stack.yaml` plus skills, rules, and scaffold
docs — the CLI auto-discovers it (`cos list-stacks`), then
`make manifest-regen && make regen-rules` refreshes the derived
artifacts. The same pattern works for new **adapters**
(`src/adapters/<id>/adapter.yaml` + `install.sh`). Step-by-step:
[docs/playbooks/template-authoring.md](./docs/playbooks/template-authoring.md)
· [docs/playbooks/adapter-authoring.md](./docs/playbooks/adapter-authoring.md).

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
| [docs/governance/critical-rules.md](./docs/governance/critical-rules.md)            | 27 critical rules with rationale + repair steps             |
| [docs/governance/mcp-tool-inventory.md](./docs/governance/mcp-tool-inventory.md)    | Per-tool spec + envelope contract                           |
| [docs/governance/agent-workflow.md](./docs/governance/agent-workflow.md)            | Domain routing, task protocol, memory contract              |
| [docs/engineering/graph_os-queries.md](./docs/engineering/graph_os-queries.md)      | When to query the graph vs grep                             |
| [docs/engineering/hub-architecture.md](./docs/engineering/hub-architecture.md)      | Hub: FastAPI ↔ React SPA contract                           |
| [docs/playbooks/](./docs/playbooks/)                                                | Hook authoring · adapter authoring · template authoring · MCP tool authoring |
| [docs/adapters/](./docs/adapters/)                                                  | Claude SDK · Codex CLI integration                          |
| [CONTRIBUTING.md](./CONTRIBUTING.md)                                                | Setup, contribution loop, PR checklist                      |
| [SECURITY.md](./SECURITY.md)                                                        | Vulnerability disclosure policy                             |
| [CHANGELOG.md](./CHANGELOG.md)                                                      | Release notes                                               |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `cos: command not found` after `uv tool install` | `~/.local/bin` (or uv's tool dir) not on `PATH` | `uv tool update-shell` then open a new shell |
| `cos doctor` reports `mcp.coding-os = absent` | Adapter installer hasn't run for this project | `bash src/adapters/<agent>/install.sh` from project root, then restart the agent runtime |
| `cos hub start` fails with `Address already in use :9188` | Port 9188 busy (likely an old Hub still running) | `lsof -ti:9188 \| xargs kill` then re-run; or `cos hub start --port 9999` |
| `make verify` complains `bash: declare -A …` | macOS default bash 3.2 doesn't have associative arrays | `brew install bash` (Makefile picks up `/opt/homebrew/bin/bash` automatically) |
| `cos init` fails on `npm ci` step | Node.js missing or below 20 | Install Node ≥20 (`brew install node@20`); only required if your template touches `src/core/web/ui/` |
| Docker build OOM on `npm ci` | Default Docker memory < 4 GB | Docker Desktop → Settings → Resources → bump memory to 4 GB+ |
| `ToolSearch` returns `InputValidationError` for a `cos_*` tool | First-call schema not loaded (Claude defers MCP schemas) | `ToolSearch("select:cos_<name>")` first, then call the tool |
| Codex hook is skipped | Project/hash trust is missing, the hooks feature is disabled, or the event/matcher is unsupported | Run `/hooks`, confirm `[features] hooks = true`, then inspect `cos hooks-list --agent codex` |
| Hub rejects the meta-repo checkout with `sits inside … already a coding-os project` | A stray `.coding-os/` exists higher up (e.g. `~/.coding-os/` from a test run) — fixed 2026-05-23: only **registered** ancestors block | Update + restart Hub: `git pull && cos hub stop && cos hub start`. If still blocking, the ancestor is genuinely registered: `cos registry remove <ancestor-path>` |

Still stuck? Run `cos doctor --verbose` and open a
[discussion](https://github.com/kouroshez/coding-os/discussions)
with the output attached.

## Support / Community

If coding-os saves you time, a star helps others find it. These links also
live in the Hub footer (never inside the new-project Composer).

- ★ Star / follow on GitHub: <https://github.com/kouroshez/coding-os>
- Sponsor the project: <https://github.com/sponsors/kouroshez> · <https://coding-os.dev/donate>
- Questions / ideas: <https://github.com/kouroshez/coding-os/discussions>
- Community forum: <https://community.coding-os.dev>

## License

Apache License 2.0 — see [LICENSE](./LICENSE). Copyright 2026
Kourosh Ebrahimzadeh and coding-os contributors.

Development began in April 2026; the full history is preserved in this
repository. Release automation (release-please) starts at the 0.3.0
baseline (2026-05-20) — see [CHANGELOG.md](./CHANGELOG.md).
