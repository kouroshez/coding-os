# AGENTS — Coding OS Development Protocol (META PROJECT)

Root entry point for agents working **ON** coding-os itself. Read first; re-read after context loss. Hard limit: keep this file under 120 lines — overflow goes to [docs/](docs/). Architecture deep-dive: [docs/architecture/meta-project.md](docs/architecture/meta-project.md).

## Nature — Meta-Project

**This repo IS the mother.** Its output is projects shaped like itself: `cos init` composes three concentric layers (DNA → mRNA → phenotype) into a consumer project, and this repo is itself an instance of what it produces (P5 Dogfood; root `CLAUDE.md` symlinks to `AGENTS.md`).

- **`src/core/`** — agent-agnostic, stack-agnostic kernel: hooks, MCP server, rules, skills. Cognitive layers on one MCP server ([server.py](src/core/thinking_os/server.py)): **thinking_os** (memory/learning/metrics) · **graph_os** (knowledge graph) · **board_os** (Scrumban).
- **`src/adapters/<agent>/`** — per-agent translation: how the kernel surfaces as `.claude/` / `.codex/`.
- **`src/templates/<stack>/`** — per-stack overlay: skills + scaffold for one language/framework.

## Modularity Map — Blast Radius

| Edit | Propagates to | Rebuild |
|---|---|---|
| `src/core/hooks/*.sh` | ALL consumer projects (live symlinks) | none |
| `src/core/thinking_os/**` | ALL projects pointing to this MCP | restart MCP client |
| `src/core/rules/*.md`, `src/core/skills/**` | ALL projects | `cos update` in consumer |
| `src/adapters/<agent>/**` | Only projects with that agent | `cos update` or re-run `install.sh` |
| `src/templates/<stack>/**` | Only projects using that stack | `cos update` + `make manifest-regen` |
| `src/cli/**` | ALL future `cos` invocations | `uv tool install --editable .` |

**Derived artifacts — never hand-edit:** `src/core/rules/{dimension-registry,skill-enforcement}.md`, `src/core/scaffold_manifest.json`, `src/adapters/*/*.template.*`, `tests/golden/**` — regenerate via `make regen-rules` / `manifest-regen` / `regen-adapter-templates`.

## Identity & Principles

Agent-agnostic cognitive OS giving AI agents memory, structure, discipline. Python + Shell + Markdown; hexagonal (core → adapters → templates).
P1 SSOT-first · P2 Agent-agnostic (`$COS_STATE_DIR`/`$COS_AGENT_DIR`/`$COS_PANEL_DIR`/`$COS_DB_PATH`, never `.claude/` in core — [state-files.md](docs/engineering/state-files.md)) · P3 Minimal-context (3-10 files/task) · P4 Diff-first · P5 Dogfood · P6 Log-everything via `make` · P7 No-guessing (log unknowns to `docs/_meta/questions.md`) · P8 Adapter-SDK autonomy (never import an adapter SDK from `src/core/**`).

## Critical Rules (index — full text + rationale in [critical-rules.md](docs/governance/critical-rules.md))

| # | Rule |
|---|---|
| 0 | Docs-first — every code Write/Edit traces to `.doc-anchor` (hook BLOCK). |
| 1 | Never hardcode `.claude/` in `src/core/` — use `$COS_*` env vars. |
| 2 | MCP tool names use `cos_*` prefix ([inventory](docs/governance/mcp-tool-inventory.md)). |
| 3 | Hooks source `cos-env.sh`. |
| 4 | Scripts search config chain `$COS_STATE_DIR/domain-config.json` → `infrastructure/scripts/domain-config.json`. |
| 5 | `.resolve()` before `.relative_to()` (macOS /tmp ↔ /private/tmp). |
| 6 | Fire-and-forget = `_*_safe()` helper with `except Exception as exc: logger.debug(...)`. |
| 7 | Governance edits require active task marker `docs-update` / `governance`. |
| 8 | Multi-step verification = Python helper, never `uv run` + bash heredoc. |
| 9 | Schema migrations append-only — new tables → vN+1, never edit past. |
| 10 | Regenerate derived artifacts (`make regen-rules` / `manifest-regen` / `regen-adapter-templates`). |
| 11 | No hardcoded stack/adapter literals in `src/cli/*.py` — data-driven from yaml. |
| 12 | Comments by exception. NO internal-helper docstrings; ONE-line docstring on `@mcp.tool` only. |
| 13 | Every `cos_*` returns `ok(data)` / `fail(category, message)` via `@safe_tool` ([envelope](docs/engineering/mcp-error-envelope.md)). |
| 14 | Tasks are pointers — never inline doc content; axes: swimlane · kind · epic · labels. |
| 15 | COMPLICATED+ → `cos_compose_chain` (11 roles; auto-fired by `auto-compose-roles.sh`; [claude-sdk.md](docs/adapters/claude-sdk.md)). |
| 16 | Formula dispatch → typed EvidenceBundle via `cos_supervise_record_output` / `cos_dispatch_formula_run`. |
| 17 | Situational Paths override role chain when `.situation` set. |
| 18 | Task reconciliation mandatory — `cos_task_board` first; reuse or create with Outcome/Read First/Acceptance. |
| 19 | Docs are the contract — edit doc before extending code. |
| 20 | Test discipline — matrix command only mid-task ([test-discipline.md](src/core/rules/test-discipline.md)). |
| 21 | Never `isolation: "worktree"` — Agent tool read-only research only. |
| 22 | Anti-overengineering — reuse-first · no speculation · diff-minimal · rule-of-three · defer-by-default ([rule](src/core/rules/anti-overengineering.md)). |
| 23 | Trunk-based git — commit direct to `main`, never branch ([git-workflow.md](src/core/rules/git-workflow.md)). |
| 24 | Commit msg: title ≤100 chars · body ≤3 lines · no agent attribution / Co-Authored-By / quoted prompts. |
| 25 | Cognitive-state mutations via semantic ops only — `cos_task_move`/`cos task-done`/`cos_classify_prompt`; lookup via `cos task-show`/`cos_task_search`, never raw ls/grep/Edit. |

## Core Loop — Classify · Orient · Plan · Execute · Verify

**Classify (dry):** `cos_classify_prompt` records the Cynefin × dimensions gate (fallback: `write-state.sh .thinking_os-gate "<LEVEL> <dims>"`) → reconcile task (Rule 18) → Read List. **Orient:** targeted reads · `cos_search` · graph. **Plan:** per dimension current/target/gap/risk; create the task before coding; COMPLICATED+ loads `Skill thinking_os`. **Execute:** smallest correct change [P1, P4]; **commit each logical unit autonomously** (`git commit <paths>` — don't wait to be asked; [git-workflow.md](src/core/rules/git-workflow.md) § When to commit). **Verify & Close:** `cos task-move --to testing` → matrix command → work-log note → commit → `cos task-done` (push to `main` at close / on ask). Never close on assumed pass.

## Verification Matrix

| Changed | Command |
|---|---|
| `src/core/thinking_os/**.py` | `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'` + `python src/core/thinking_os/server.py --test` (pre-merge: `make test-slow`) |
| `src/core/thinking_os/database.py` | `uv run --extra rag pytest src/core/thinking_os/tests/test_db.py -q` |
| `src/core/graph_os/**` | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| `src/core/board_os/**` | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` |
| `src/core/hooks/*.sh`, `src/core/scripts/*.sh` | `make verify-hooks` |
| `src/adapters/**` | `uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q` |
| `src/cli/*.py` | `uv run pytest tests/test_cli.py -q` |
| `src/templates/**/scaffold/**` | `uv run pytest tests/test_template_scaffold.py -q` |
| `docs/**/*.md` | `make docs-lint` |

## Tool Routing

- **Task/board state (Rule 25, the ONLY mutation path):** `cos task-create --title … --swimlane … --kind … [--ready]` · `cos task-ready` · `cos task-start` · `cos task-move --to testing` · `cos task-done` · `cos task-reclaim` · `cos board` · `cos daily` · `cos retro` · `cos wip`. MCP equivalents: `cos_task_*` (+ `cos_work_log_append` — Codex must call it). NEVER hand-Edit `docs/tasks/**` status (BLOCKed).
- **Slash commands:** `/board` `/daily` `/retro` `/task` `/classify` `/verify` `/review` `/diagnose` `/memory-search` `/compose` + 11× `/role-*` — from [src/core/commands/](src/core/commands/) + [agents/](src/core/thinking_os/agents/).
- **Deferred tool schemas (Claude):** every `cos_*` needs `ToolSearch("select:<tool>")` before first use each session ([schema traps](docs/engineering/mcp-schema-traps.md)).
- **Retrieval precedence (structural → memory):** Knowledge Graph/code (`cos_graph_*`) → Doc KB (`cos_doc_search`) → Tasks (`cos_task_*`) → Agent Memory (`cos_search`, only for "have I solved this before"). Routing + freshness: [graph_os-queries.md](docs/engineering/graph_os-queries.md).
- **Graph-first (mandatory for `src/core/**`/`src/cli/**`/`src/adapters/**`):** structural questions (callers, blast radius, rename, contracts, trace) hit `cos_graph_*` BEFORE Read/grep — one envelope (~300 tok) replaces 5-10 reads. Trigger table: [meta-graph-first.md](.claude/rules/meta-graph-first.md); ladder + coverage contract: `Skill graph-explorer`; hallucination matrix: [graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md). Polyglot coverage (py/ts/go/sh/php/yaml/md/json/toml): [roadmap](docs/playbooks/polyglot-extractor-roadmap.md).
- **Verify/log/health:** `make verify` · `make verify-hooks` · `make test-mcp` · `cos health` · `cos doctor` (`--tokens` = token-burn audit) · `make log-{latest,write,search}` · hooks: `cos hooks-log [--follow]`, SSOT [registry.yaml](src/core/hooks/registry.yaml); cognition traces: `cos cognition trace <session_id>`.
- **Web UI:** `cos hub start` → FastAPI + React SPA at `http://127.0.0.1:9188`, serves every registered project; `make ui-dev` HMR. Contract: [hub-architecture.md](docs/engineering/hub-architecture.md). Propagation: core dirs reach consumers via live symlinks; templates re-render via `cos sync-all`; dangling symlinks → `cos sync-doctor --repair`.

## Adapter Parity & Hook Coverage

Parity is bounded by runtime capability declared in `src/adapters/<agent>/adapter.yaml::hook_capabilities` — the renderer skips unsupported `{event, matcher}` pairs (Codex Bash-only = correct, not a gap). Protected work (gates/skills/doc-anchor) requires a runtime where hooks fire: Claude Code ✅ · Codex CLI ⚠️ Bash-only · Codex.app ❌ · human ❌ (install `bash src/scripts/install-git-hooks.sh`). Audit: [workflow-audit-2026-04-25.md](docs/engineering/workflow-audit-2026-04-25.md).

## Key Files

MCP server [server.py](src/core/thinking_os/server.py) · DB/migrations [database.py](src/core/thinking_os/database.py) · MCP tools [tools/](src/core/thinking_os/tools/) · graph_os [src/core/graph_os/](src/core/graph_os/) · board_os [src/core/board_os/](src/core/board_os/) · web [src/core/web/](src/core/web/) (+ [ui/](src/core/web/ui/)) · roles [roles/](src/core/thinking_os/roles/) + [agents/](src/core/thinking_os/agents/) + [presets](src/core/thinking_os/presets/registry.yaml)/[situations](src/core/thinking_os/situations/registry.yaml) · hooks [src/core/hooks/](src/core/hooks/) · skills [src/core/skills/](src/core/skills/) (routing → [skill-enforcement.md](src/core/rules/skill-enforcement.md)) · CLI [src/cli/](src/cli/) · adapters [src/adapters/](src/adapters/) · templates [src/templates/](src/templates/) (8 stacks).

## Stop Conditions

Stop and surface to user when: (a) a `src/core/` change breaks backward compatibility, (b) an adapter change affects another adapter, (c) an MCP tool signature changes without a migration plan.
