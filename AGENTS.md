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

> **Values SSOT:** [docs/governance/constitution.md](docs/governance/constitution.md) — the 8 values these principles + the rules below derive from (the *teach-why* layer; surfaced each session). Lead with the *why*; a rule understood generalizes where a rule merely imposed cracks.
> **Vision + operator contract:** [docs/governance/vision.md](docs/governance/vision.md) — where the product is going, plus standing norms: challenge the operator with evidence (never rubber-stamp) and adversarially self-review non-trivial designs via the [Raptor lens](docs/architecture/raptor-consolidation.md).

## Critical Rules (index — full text + rationale in [critical-rules.md](docs/governance/critical-rules.md))

| # | Rule |
|---|---|
| 0 | Docs-first — every code Write/Edit traces to `.doc-anchor` (hook BLOCK); *why:* intent must survive the author, so the spec is edited before the code. |
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
| 12 | Comments by exception. NO internal-helper docstrings; ONE-line docstring on `@mcp.tool` only; **no provenance in a comment** — strip `TASK-NNN`/`Phase-N`/`P5:`/`(G9)` refs (`git blame` already records who/what); *why:* comments rot while names don't, and the runtime's "match surrounding density" makes comment-heavy legacy teach the opposite — thin it, never imitate it. ([clean-code §4](src/core/skills/clean-code/SKILL.md)) |
| 13 | Every `cos_*` returns `ok(data)` / `fail(category, message)` via `@safe_tool` ([envelope](docs/engineering/mcp-error-envelope.md)). |
| 14 | Tasks are pointers — never inline doc content; axes: swimlane · kind · epic · labels. |
| 15 | COMPLICATED+ → `cos_compose_chain` (11 roles; auto-fired by `auto-compose-roles.sh`; [claude-sdk.md](docs/adapters/claude-sdk.md)). |
| 16 | Formula dispatch → typed EvidenceBundle via `cos_supervise_record_output` / `cos_dispatch_formula_run`. |
| 17 | Situational Paths override role chain when `.situation` set. |
| 18 | Task reconciliation mandatory — `cos_task_board` first; reuse or create with Outcome/Read First/Acceptance. |
| 19 | Docs are the contract — edit doc before extending code. |
| 20 | Test discipline — matrix command only mid-task ([test-discipline.md](src/core/rules/test-discipline.md)). |
| 21 | Never `isolation: "worktree"` — Agent tool read-only research only. |
| 22 | Anti-overengineering — reuse-first · no speculation · diff-minimal · rule-of-three · defer-by-default ([rule](src/core/rules/anti-overengineering.md)); *why:* every line is a liability a future maintainer carries forever. |
| 23 | Trunk-based git — commit direct to `main`, never branch ([git-workflow.md](src/core/rules/git-workflow.md)); *why:* branches sprawl and `src/core/` reaches every consumer via live symlinks, so history stays linear and reviewable. |
| 24 | Commit msg: title ≤100 chars · body ≤3 lines · no agent attribution / Co-Authored-By / quoted prompts; *why:* git log is permanent and release-please parses the title into the changelog. |
| 25 | Cognitive-state mutations via semantic ops only — `cos_task_move`/`cos task-done`/`cos_classify_prompt`; lookup via `cos task-show`/`cos_task_search`, never raw ls/grep/Edit; *why:* the board DB and docs/tasks/ files desync if edited by hand. |
| 26 | Verify by executing, not reading — never claim done / hand the user a command you did not run **this session**; a green proxy suite (`pytest`) ≠ the delivered executable runs — smoke-run entrypoints (`--help`/`--dry-run`) before `task-move --to testing` ([test-discipline.md](src/core/rules/test-discipline.md)); *why:* reading code isn't verification, and shipping a broken deliverable under a "done" claim is autonomy's highest-damage failure. |
| 27 | Runtime cost is correctness — name `n` (p99 in production, not the fixture) before any loop/query and hold the complexity budget; no I/O or list-membership scan inside a loop; a "faster" claim needs a measured number for the delivered path ([clean-code §8](src/core/skills/clean-code/SKILL.md)); *why:* the same requirement ships at 900 ms or 20 s and the tests never notice — at scale a slow-enough answer fails the user exactly as a wrong one does, and the fix is free while writing but an incident afterwards. |

## Core Loop — Classify · Orient · Plan · Execute · Verify

**Classify (dry):** `cos_classify_prompt` records the Cynefin × dimensions gate (fallback: `write-state.sh .thinking_os-gate "<LEVEL> <dims>"`) → reconcile task (Rule 18) → Read List. **Orient:** targeted reads · `cos_search` · graph. **Plan:** per dimension current/target/gap/risk; create the task before coding; COMPLICATED+ loads `Skill thinking_os`. **Execute:** smallest correct change [P1, P4]; **commit each logical unit autonomously** (`git commit <paths>` — don't wait to be asked; [git-workflow.md](src/core/rules/git-workflow.md) § When to commit). **Verify & Close:** `cos task-move --to testing` → matrix command → work-log note → commit → `cos task-done` (push to `main` at close / on ask). Never close on assumed pass.

## Verification Matrix

| Changed | Command |
|---|---|
| `src/core/thinking_os/**.py` | `uv run --extra rag pytest src/core/thinking_os/tests/ -q -m 'not slow'` + `uv run python src/core/thinking_os/server.py --test` (pre-merge: `make test-slow`) |
| `src/core/thinking_os/database.py` | `uv run --extra rag pytest src/core/thinking_os/tests/test_db_*.py -q` |
| `src/core/graph_os/**` | `uv run --extra graph_os pytest src/core/graph_os/tests/ -q` |
| `src/core/board_os/**` | `uv run --extra rag --with aiohttp --with pytest-asyncio pytest src/core/board_os/tests/ -q` |
| `src/core/hooks/*.sh`, `src/core/scripts/*.sh` | `make verify-hooks` |
| `src/adapters/**` | `uv run pytest tests/test_adapters_*.py tests/test_adapter_parity.py -q` |
| `src/cli/*.py` | `uv run pytest tests/test_cli.py -q` |
| `src/templates/**/scaffold/**` | `uv run pytest tests/test_template_scaffold_*.py -q` |
| `docs/**/*.md` | `make docs-lint` |

> Suite paths are **globs on purpose**: `test_adapters.py`, `test_db.py` and `test_template_scaffold.py` were each split into siblings while the matrix kept naming the old file, so three rows exited "no tests ran" — a silent no-op that reads exactly like a pass. `tests/test_verification_matrix.py` fails if any row stops collecting.

## Tool Routing

- **Task/board state (Rule 25, the ONLY mutation path):** `cos task-create --title … --swimlane … --kind … [--ready]` · `cos task-ready` · `cos task-start` · `cos task-move --to testing` · `cos task-done` · `cos task-reclaim` · `cos board` · `cos daily` · `cos retro` · `cos wip`. MCP equivalents: `cos_task_*` (+ `cos_work_log_append` — Codex must call it). NEVER hand-Edit `docs/tasks/**` status (BLOCKed).
- **Slash commands:** `/board` `/daily` `/retro` `/task` `/classify` `/verify` `/review` `/diagnose` `/memory-search` `/compose` + 11× `/role-*` — from [src/core/commands/](src/core/commands/) + [agents/](src/core/thinking_os/agents/).
- **Deferred tool schemas (Claude):** every `cos_*` needs `ToolSearch("select:<tool>")` before first use each session ([schema traps](docs/engineering/mcp-schema-traps.md)).
- **Retrieval precedence (structural → memory):** Knowledge Graph/code (`cos_graph_*`) → Doc KB (`cos_doc_search`) → Tasks (`cos_task_*`) → Agent Memory (`cos_search`, only for "have I solved this before"). Routing + freshness: [graph_os-queries.md](docs/engineering/graph_os-queries.md).
- **Graph-first (mandatory for `src/core/**`/`src/cli/**`/`src/adapters/**`):** structural questions (callers, blast radius, rename, contracts, trace) hit `cos_graph_*` BEFORE Read/grep — a targeted envelope (few hundred to few thousand tokens, heuristic; measured by `make bench` → `token_cost`) replaces grepping + reading every matching file, and the saving scales with repo size (whole-graph `export`/`communities` cost far more — use deliberately). Trigger table: [meta-graph-first.md](src/templates/meta/rules/graph-first.md); ladder + coverage contract: `Skill graph-explorer`; hallucination matrix: [graph-hallucination-cures.md](docs/engineering/graph-hallucination-cures.md). Polyglot coverage (py/ts/go/sh/php/yaml/md/json/toml): [roadmap](docs/playbooks/polyglot-extractor-roadmap.md).
- **Verify/log/health:** `make verify` · `make verify-hooks` · `make test-mcp` · `cos health` · `cos doctor` (`--tokens` = token-burn audit) · `make log-{latest,write,search}` · hooks: `cos hooks-log [--follow]`, SSOT [registry.yaml](src/core/hooks/registry.yaml); cognition traces: `cos cognition trace <session_id>`.
- **Web UI:** `cos hub start` → FastAPI + React SPA at `http://127.0.0.1:9188`, serves every registered project; `make ui-dev` HMR. Contract: [hub-architecture.md](docs/engineering/hub-architecture.md). Propagation: core dirs reach consumers via live symlinks; templates re-render via `cos sync-all`; dangling symlinks → `cos sync-doctor --repair`.
- **pr-mode git (consumer-only, default OFF — coding-os stays trunk):** `cos pr open [--task|--adhoc]` · `cos pr submit` · `cos pr status` · `cos pr cleanup` · `cos pr reap` · `cos pr heal` · `cos pr preflight`. Enable per-project via Hub **Config → Git** (`git_settings.enabled`). Spec: [pr-workflow.md](docs/playbooks/pr-workflow.md) · [ADR-0013](docs/architecture/adr/0013-pr-mode-multi-agent-git-workflow-consumer-only.md). Verify: `uv run pytest tests/test_cli.py::TestCosPr -q`.

## Adapter Parity & Hook Coverage

Parity is bounded by runtime capability declared in `src/adapters/<agent>/adapter.yaml::hook_capabilities` — the renderer skips unsupported `{event, matcher}` pairs (a skipped pair is correct, not a gap). Protected work (gates/skills/doc-anchor) requires a runtime where hooks fire: Claude Code ✅ · Codex CLI/Desktop ✅ full parity via dispatchers (honest deficits: no `PostToolUseFailure`, no `Skill` matcher) · human ❌ (install `bash src/scripts/install-git-hooks.sh`). Parity SSOT: [adapter-parity.md](docs/engineering/adapter-parity.md).

## Key Files

MCP server [server.py](src/core/thinking_os/server.py) · DB/migrations [database.py](src/core/thinking_os/database.py) · MCP tools [tools/](src/core/thinking_os/tools/) · graph_os [src/core/graph_os/](src/core/graph_os/) · board_os [src/core/board_os/](src/core/board_os/) · web [src/core/web/](src/core/web/) (+ [ui/](src/core/web/ui/)) · roles [roles/](src/core/thinking_os/roles/) + [agents/](src/core/thinking_os/agents/) + [presets](src/core/thinking_os/presets/registry.yaml)/[situations](src/core/thinking_os/situations/registry.yaml) · hooks [src/core/hooks/](src/core/hooks/) · skills [src/core/skills/](src/core/skills/) (routing → [skill-enforcement.md](src/core/rules/skill-enforcement.md)) · CLI [src/cli/](src/cli/) · adapters [src/adapters/](src/adapters/) · templates [src/templates/](src/templates/).

## Stop Conditions

Stop and surface to user when: (a) a `src/core/` change breaks backward compatibility, (b) an adapter change affects another adapter, (c) an MCP tool signature changes without a migration plan.
