<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-17 -->
# Features & System Map

Purpose: Single-page mental model of coding-os — what exists, how it fits together, and what each CLI command does. Optimized for a human reading it cold *and* for an agent needing to orient quickly.
Read when: Onboarding to the project, picking the right command for a task, deciding whether a capability already exists before building new.
Skip when: You need deep implementation detail — go to [architecture.md](./architecture.md) or a phase plan.
Read next: [getting-started.md](./getting-started.md) for install steps, [development-roadmap.md](./development-roadmap.md) for what's planned.

> Nav: [Docs Index](./tasks.md) · [Architecture](./architecture.md) · [Roadmap](./development-roadmap.md)

---

## 1. The Big Picture

```
                    ┌──────────────────────────┐
                    │     AI Agent             │
                    │ (Claude / Codex / Cursor)│
                    └─────────────┬────────────┘
                                  │
                    ┌─────────────▼────────────┐
                    │      ADAPTER             │   ← Translates agent-specific format
                    │  .claude/   .codex/      │
                    └─────────────┬────────────┘
                                  │
         ┌────────────────────────▼────────────────────────┐
         │                   CORE                           │
         │   hooks ─ skills ─ rules ─ commands ─ thinking-os│
         └────────────────────────┬────────────────────────┘
                                  │
                    ┌─────────────▼────────────┐
                    │    TEMPLATES             │   ← Per-stack content
                    │  django · nextjs ·       │
                    │  fastapi · go            │
                    └──────────────────────────┘
```

**Guiding principle** (SSOT — Single Source of Truth): every asset lives in exactly one location. Projects receive symlinks. When coding-os upgrades, `cos update` re-syncs them.

---

## 2. Command Catalog (32+ commands)

Think of these as three clusters:

### 🏗️ Project Lifecycle
| Command | Purpose | New in |
|---|---|---|
| `cos init` | Bootstrap a new project (interactive or flag-based, multi-agent) | D.2 enhanced |
| `cos setup` | Fill in PRD/docs after init (interactive / import-prd / skip) | **D.4** |
| `cos add-adapter <name>` | Add a second agent adapter | — |
| `cos add-stack <name>` | Add a stack template to an existing project | — |
| `cos update` | Re-sync assets with current coding-os (manifest-diff) | **D.3** |
| `cos eject` | Convert every symlink to real file (self-contained) | — |
| `cos eject-file <path>` | Convert one symlink to real file (fine-grained) | **D.5** |

### 🔍 Diagnostics
| Command | Purpose |
|---|---|
| `cos doctor` | 14 deep checks (adapter, manifest, MCP selftest, stack skills, MCP portability, …) |
| `cos health` | Minimal DB/config check |
| `cos list-stacks` | Show available stacks (data-driven from `templates/*/stack.yaml`) |
| `cos list-adapters` | Show available adapters |
| `cos hooks-dir` | Print absolute path to `core/hooks/` |

### 🧠 Brain (MCP + RAG + Tasks)
| Command | Purpose |
|---|---|
| `cos docs-index` | Chunk `docs/` → embeddings (Phase B RAG) |
| `cos task-sync` | Sync `docs/tasks/*.md` → `tasks` table (Phase C) |
| `cos reindex` | Re-embed all observations/patterns/outcomes |
| `cos server-start` | Start the thinking-os MCP server (wrapper used by `.mcp.json`) | **D.1** |

### 📋 Scrumban Board (Phase L — board-os)
| Command | Purpose |
|---|---|
| `cos board [--web] [--swimlane X] [--kind Y] [--epic Z]` | ASCII or browser Scrumban board |
| `cos task-create --title ... --swimlane ... --kind ...` | Create new lean task file |
| `cos task-start TASK-NNN` | icebox/ready → in_progress (WIP enforced) |
| `cos task-move TASK-NNN --to <status>` | Explicit state transition |
| `cos task-done TASK-NNN` | → complete |
| `cos task-block TASK-NNN --reason ...` | → blocked |
| `cos task-cancel TASK-NNN` | → icebox + `cancelled` label |
| `cos task-pick` | Top N candidates by priority + emergency |
| `cos daily [--since 24h]` | Morning standup |
| `cos retro [--since 7d]` | Weekly retro — throughput + cycle time |
| `cos wip` | Current WIP counts vs caps |
| `cos task-show TASK-NNN` | Full task content + status |
| `cos task-log TASK-NNN [--full]` | Work Log (last 5 or full) |
| `cos task-history TASK-NNN` | Status transition log |
| `cos task-validate` | Lint every `docs/tasks/*.md` against the lean schema |
| `cos board-config --init [--stack <stack>]` | Scaffold `.coding-os/scrumban-config.yaml` |

---

## 3. End-to-End Flow

Two flows matter: **first-time setup** (the user arc) and **daily use** (the agent arc).

### A. First-Time Setup

```
Install cos globally
   │
   │   uv tool install --editable /path/to/coding-os
   ▼
[any project dir]
   │
   │   cos init            (interactive: prompts for agents, templates, name)
   ▼                       or cos init -a claude,codex -t django -y   (flag-based)
my-shop/
├── .claude/ or .codex/    ← symlinks into coding-os core
├── .coding-os/            ← state (DB, rag-config, installed-manifest)
├── docs/                  ← scaffold (PRD, engineering, playbooks, …)
├── .mcp.json              ← wired to `cos server-start`
├── AGENTS.md              ← generated once, now editable
└── Makefile

   │
   │   cos setup           (bootstrap docs — interactive or import-prd mode)
   ▼
docs/PRD/01-snapshot-vision.md ← populated
docs/PRD/02-goals-kpis.md       ← populated
docs/PRD/… etc                  ← populated

   │
   │   cos doctor          (14 checks)
   ▼
[14 PASS] — ready to start work
```

### B. Daily Use (inside Claude Code / Codex)

```
 SessionStart hook  →  session-context.sh  →  inject workflow + memory stats
       │
       │  Agent reads task
       ▼
 [Gate 1: Complexity Gate]
   "CLEAR 1"  /  "COMPLICATED 3"  /  "COMPLEX 5"  /  "CHAOTIC"
       │
       │  write-state.sh .coding-os/.thinking-os-gate
       ▼
 [Gate 2: Request Type]  →  Question / Task / Ad-hoc
       │
       ▼
 Core Loop:   CLASSIFY → ORIENT → PLAN → EXECUTE → VERIFY
   (dry)       (dry)    (read)   (think)  (do)    (commands)

 Before any Write/Edit: 7 PreToolUse hooks fire in order (fail-closed):
   1. block-protected-files        2. block-secrets         3. block-bad-patterns
   4. thinking-os-gate             5. enforce-task-start   6. enforce-skill
   7. enforce-zoom

 After Write/Edit: 2 PostToolUse hooks
   1. verify-changed-file          2. capture-observation (auto-embeds)

 Session end → session-end.sh → summary + enrichment
```

### C. Upgrade Flow (`cos update`)

```
coding-os repo pulled / upgraded
       │
cd into any existing project
       │
cos update --dry-run        → shows diff
       │
       │  Added: hooks/new-hook.sh
       │  Removed: skills/deprecated-skill
       │  DB schema: v6 → v7 pending
       ▼
cos update                  → applies the diff
       │
       │  • Links new assets
       │  • Removes orphan symlinks
       │  • Runs DB migrations
       │  • Writes installed-manifest.json snapshot
       │  • NEVER touches docs/, AGENTS.md, user content
       ▼
cos doctor                  → verify 14/14 PASS
```

---

## 4. Three-Layer Retrieval (what the agent actually queries)

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 1 — AGENT MEMORY                                           │
│   observations · learned_patterns · outcome_history              │
│   Question: "Have I solved this before?"                         │
│   Tools: cos_search · cos_timeline · cos_details · cos_promote   │
│          cos_learn_suggest · cos_learn_narrative                 │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2 — DOCUMENT KNOWLEDGE BASE (Phase B RAG)                  │
│   document_chunks populated by `cos docs-index`                  │
│   Question: "What does the spec say?"                            │
│   Tool: cos_doc_search (filter by 9 source types)                │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3 — TASK REGISTRY (Phase C)                                │
│   tasks table populated by `cos task-sync`                       │
│   Question: "What depends on what?"                              │
│   Tools: cos_task_search · cos_task_dependencies ·               │
│          cos_task_dependents · cos_task_by_filter                │
└─────────────────────────────────────────────────────────────────┘

Always-active (no retrieval — full-read at session start):
   AGENTS.md · CLAUDE.md · core/rules/* · docs/governance/* · current task
```

RAG source types (`docs/breakthroughs/` is new from session D work):
`prd` · `architecture` · `adr` · `api_contract` · `page_spec` · `engineering` · `ops` · `design` · `breakthrough`

---

## 5. MCP Tools (29 tools, `cos_*` prefix)

| Category | Count | Tools |
|---|---|---|
| Health | 1 | `cos_health` |
| Memory | 4 | `cos_search` · `cos_timeline` · `cos_details` · `cos_promote` |
| Metrics | 3 | `cos_metric_record` · `cos_metric_query` · `cos_metric_trend` |
| Learning | 5 | `cos_learn_extract` · `cos_learn_suggest` · `cos_learn_validate` · `cos_learn_feedback` · `cos_learn_narrative` |
| Routing | 2 | `cos_route_model` · `cos_route_skill` |
| Graph | 1 | `cos_graph` |
| Docs RAG | 1 | `cos_doc_search` |
| Task Store (Phase C) | 4 | `cos_task_search` · `cos_task_dependencies` · `cos_task_dependents` · `cos_task_by_filter` |
| **Board (Phase L)** | 8 | `cos_task_create` · `cos_task_board` · `cos_task_move` · `cos_task_pick` · `cos_task_daily` · `cos_task_retro` · `cos_task_wip_check` · `cos_work_log_append` |
| Retrieval feedback | 1 | `cos_retrieval_cite` |
| **Wrapper** | 1 | `cos server-start` (CLI command, not MCP tool — starts the server) |

---

## 6. Hook System (45 shell scripts)

Hooks live in `core/hooks/` — symlinked into every project.

### Bash Pre-Enforcement (ordered, fail-closed)

| Hook | What it blocks |
|---|---|
| `block-secrets.sh` | API keys, credentials in command args |
| `block-dangerous-commands.sh` | `rm -rf`, force-push, `reset --hard`, `branch -D` |
| `block-uv-heredoc.sh` ★ | `uv run ... <<` pattern (CLAUDE.md rule #9 — hangs silently) |
| `enforce-verify.sh` | `make task-done` without passed verification suites |

### Write/Edit Pre-Enforcement (ordered, fail-closed)

| # | Hook | What it blocks |
|---|---|---|
| 1 | `block-protected-files.sh` | CLAUDE.md · AGENTS.md · `core/rules/` · `core/hooks/` unless task marker contains governance tag |
| 2 | `enforce-template.sh` ★ | Raw Write on structured `.md` (task · ADR · PRD · breakthrough) — redirects to `make task-create` / `cos setup` / `cos_learn_narrative` |
| 3 | `block-migration-conflict.sh` ★ | Duplicate migration version in `db.py` (CLAUDE.md rule #10 — append-only) |
| 4 | `block-hardcoded-literals.sh` ★ | Quoted stack/adapter IDs in `cli/*.py` (SSOT violation) |
| 5 | `block-secrets.sh` | API keys, credentials in file content |
| 6 | `block-bad-patterns.sh` | Anti-patterns (bare `except: pass`, etc.) |
| 7 | `thinking-os-gate.sh` | Code write without recorded Complexity Gate |
| 8 | `enforce-task-start.sh` | Code write without active task (unless CLEAR 1) |
| 9 | `enforce-doc-anchor.sh` ★ | **Code write without a doc anchor** — see §6a below |
| 10 | `enforce-skill.sh` | Code write without domain skill invoked |
| 11 | `enforce-zoom.sh` | COMPLICATED+ without Plan checkpoint |

### Post-Action Hooks (never block, report only)

| Hook | Triggers on | What it does |
|---|---|---|
| `verify-changed-file.sh` | Write/Edit | Quality + cross-file impact analysis |
| `capture-observation.sh` | Write/Edit | Record observation + embed text (Phase B). Failures now append to `$COS_STATE_DIR/.capture-errors.log` instead of disappearing silently. |
| `regen-reminder.sh` ★ | Write/Edit | Prints `make manifest-regen` / `regen-rules` / `capture_golden` when source-of-truth files change |
| `test-first-reminder.sh` ★ | Write/Edit | Lists the related test file (or suggests one) when code changes |
| `doc-sync-reminder.sh` ★ | Write/Edit | Lists companion docs to update (README, features.md, architecture.md) |
| `remind-learn-validate.sh` ✱ | Bash (`make task-done`) | After task close, nudges to call `cos_learn_validate` for each pattern `cos_learn_suggest` surfaced during Orient |
| `track-skill.sh` | Skill | Log skill invocation |
| `check-capture-worked.sh` ✱ | Stop | End-of-session recap — prints observations count + capture errors; "zero observations after edits" warning surfaces silent MCP/DB failures |
| `session-end.sh` | Stop | Session summary + enrichment |
| `warn-mcp-down.sh` ✱ | SessionStart | Probes `.mcp.json` or Codex's `.codex/config.toml` MCP entry with a real initialize handshake (falling back to `~/.codex/config.toml` only if the project has no local Codex config). Banners loudly if MCP is unreachable so memory/learning being disabled is visible from turn one. |
| `session-context.sh` | SessionStart + UserPromptSubmit | Workflow + memory digest; Codex `UserPromptSubmit` path refreshes context without rotating session-id |

★ = added in Phase D/E. ✱ = added in Phase F (MCP visibility + workflow integrity). All are SSOT (live in `core/hooks/`) so every project — Claude or Codex — gets them on `cos init` / `cos update`.

### Why the Phase F hooks exist

The session that shipped Phase D/E ran for hours with MCP silently dead — the capture hook kept writing to a broken DB path, zero observations were persisted, and no human/agent surface signalled it. Phase F closes that blind spot:

- **`warn-mcp-down.sh`** — runs at every session start, launches the real MCP command from `.mcp.json` or Codex's `.codex/config.toml` (falling back to `~/.codex/config.toml` only when no project-local Codex config exists), and banner-prints a loud warning if the initialize handshake fails. Human and agent both know within the first second that memory is offline.
- **`check-capture-worked.sh`** — at session end, counts observations written in this session_id. Zero-with-edits → warn. Reads `$COS_STATE_DIR/.capture-errors.log` (populated by the hardened capture-observation hook) and surfaces the actual traceback.
- **`enforce-memory-check.sh`** — the thinking-os skill mandates a Memory Check in Orient. This hook blocks code writes until the agent records `$COS_STATE_DIR/.memory-check` (via `cos_search` + a state-file marker), exempt for CLEAR 1 / exploratory / spike / tests / docs.
- **`remind-learn-validate.sh`** — closes the learning loop. `cos_learn_suggest` output lives in `$COS_STATE_DIR/.learn-suggestions`; after `make task-done`, the hook prints a reminder to call `cos_learn_validate` for each pattern so confidence formulas (LTP / LTD) actually update.

### 6a. The docs-first principle (`enforce-doc-anchor.sh`)

**Rule:** *"Docs are always the source of truth. Code that can't trace to a doc is either a trivial ad-hoc fix, an exploratory spike, or something the user needs to approve."*

```
make task-start TASK=N
  │
  │ task-start.sh parses docs/tasks/TASK-N-*.md
  │ extracts Source of Truth + Read First paths
  │ writes $COS_STATE_DIR/.doc-anchor
  │
  │ if those sections are empty/placeholder → WARN (doesn't block task-start,
  │ but next code Write will be blocked)
  ▼
Agent tries to Write/Edit *.py / *.ts …
  │
  ▼
enforce-doc-anchor.sh reads .doc-anchor
  │
  ├── anchor exists, non-placeholder → ALLOW
  ├── anchor missing / placeholder    → BLOCK
  │
  └── Exempt (no anchor required):
      • Files under tests/, docs/, migrations/, scaffold/, .coding-os/
      • CLEAR 1 ad-hoc fixes (`thinking-os-gate = "CLEAR 1"`)
      • Exploratory/spike/governance tasks (marker substring match)
      • One-shot override: `touch $COS_STATE_DIR/.doc-anchor-override`
```

### Why every post-hook exists

| Hook | Failure it addresses |
|---|---|
| `enforce-template.sh` | Free-written `docs/tasks/TASK-*.md` bypasses template and tasks index. Redirects to `make task-create`. |
| `block-migration-conflict.sh` | Two `MIGRATIONS.append((5, ...))` silently corrupts the DB. Catastrophic. |
| `block-hardcoded-literals.sh` | `"django"` or `"claude"` inside `cli/*.py` breaks the zero-hardcoding contract. Was caught only at test time before; now caught at edit time. |
| `enforce-doc-anchor.sh` | "I forgot to read the spec" becomes impossible to hide. Either find the doc, mark trivial, or ask the user. |
| `regen-reminder.sh` | Change `stack.yaml` / `adapter.yaml` / scaffold → test_manifest_fresh and test_golden_parity fail silently. Hook tells you exactly which `make` target or `capture_golden` to run. Also warns on hand-edits to generated files. |
| `test-first-reminder.sh` | Ship code → test goes stale → coverage erodes. Soft nudge at edit time keeps the habit visible. |
| `block-uv-heredoc.sh` | CLAUDE.md rule #9 — `uv run` with heredoc hangs. I learned this the hard way during Phase D; the hook now catches it for every future agent. |
| `doc-sync-reminder.sh` | README / features / architecture drift from code. Post-write reminder lists the specific docs to refresh. |

### Helpers (not standalone enforcers)

`cos-env.sh` · `check-state.sh` · `write-state.sh` · `record-verify.sh` · `test-hooks.sh` · `verify-agent-system.sh`

---

## 7. Skills (SSOT + stack-scoped)

### Core Skills (agent-agnostic, `core/skills/`)

| Skill | Purpose |
|---|---|
| `thinking-os` | Complexity Gate + Cognitive Cycle + 10 Thinking Tools |
| `clean-code` | fail-closed error handling, self-documenting code, edge coverage |
| `codebase-explorer` | mapping unfamiliar code before editing |
| `worktree-orchestration` | dispatching parallel subagents via git worktrees |

### Stack Skills (`templates/<stack>/skills/`)

| Stack | Skills |
|---|---|
| `django` | `python-django` |
| `fastapi` | `python-fastapi` |
| `go` | `go-patterns` |
| `nextjs` | `nextjs-react` · `frontend-design` |

All skills are symlinked into `.claude/skills/<name>/SKILL.md`. From D.1 onward the adapter install wires **both** core and stack skills automatically; before D.1, stack skills were silently missing.

---

## 8. Per-Project Structure (what `cos init` creates)

```
my-project/
├── .coding-os/                  ← STATE (gitignored), per-project
│   ├── thinking-os.db           ← SQLite v6 (13+ tables, FTS5, embeddings)
│   ├── rag-config.yaml          ← RAG sources + priorities
│   ├── domain-config.json       ← task-create REF code map
│   ├── installed-manifest.json  ← NEW in D.3: snapshot of linked assets
│   ├── Makefile.base            ← universal targets (copy, not symlink)
│   └── session-id               ← current agent session
│
├── .claude/   (or .codex/)      ← ADAPTER
│   ├── hooks/*.sh               → symlinks to core/hooks/
│   ├── skills/*/SKILL.md        → symlinks (core + stack)
│   ├── rules/*.md               → mix: core symlinks + stack-rule copies
│   ├── commands/*.md            → symlinks to core/commands/
│   ├── settings.json            ← hook wiring (generated)
│   └── settings.local.json      ← user permissions
│
├── docs/                        ← SCAFFOLD (editable)
│   ├── 00-index.md              ← master navigation
│   ├── foundation-map.md        ← REF code shortcuts
│   ├── tasks.md                 ← task list (SSOT for status)
│   ├── tasks/                   ← per-task detail files
│   ├── PRD/                     ← product spec (filled by `cos setup`)
│   ├── architecture/            ← system architecture + ADRs
│   ├── api-contracts/           ← per-endpoint / per-service contracts
│   ├── engineering/             ← code rules (per-stack)
│   ├── playbooks/               ← step-by-step task workflows
│   ├── governance/              ← policy docs (docs-system, agent-workflow, …)
│   ├── ops/                     ← runbooks
│   ├── design/                  ← design tokens (frontend stacks)
│   ├── pages-content-spec/      ← per-page copy specs (nextjs)
│   ├── breakthroughs/           ← auto-filed narratives (Phase C.5 onward)
│   └── workflow-docs/           ← thinking-os reference, workflow guide
│
├── .mcp.json                    ← `cos server-start` (portable)
├── AGENTS.md                    ← routing protocol (generated once)
├── Makefile                     ← wrapper that includes Makefile.base
└── .coding-os.yaml              ← project config (agents, templates, verify map)
```

---

## 9. Database Schema (v6)

13 tables in SQLite with WAL + FTS5 (graceful degradation if FTS5 absent):

| Table | Phase | Purpose |
|---|---|---|
| `task_outcomes` | v1 | Completed task records |
| `agent_metrics` | v1 | Per-invocation telemetry |
| `learned_patterns` | v1 | Extracted patterns with confidence |
| `experiment_log` | v1 | Hypothesis tracking |
| `observations` | v1 | Raw captures from capture-observation.sh |
| `session_summaries` | v1+v4 | Session digests + enrichment |
| `schema_version` | v1 | Applied migration log |
| `observations_fts` | v2 | FTS5 virtual table |
| `routing_weights` | v3 | Adaptive model/skill routing |
| `outcome_history` | v4 | Breakthrough narratives |
| `concept_graph` | v4 | File/concept edges (co_edit, concept_link) |
| `embeddings` | v5 (Phase B) | ~384-dim float32 BLOBs |
| `document_chunks` | v5 (Phase B) | Heading-aware markdown chunks |
| `tasks` | v6 (Phase C) | Structured task index |

---

## 10. Self-Learning Pipeline

```
Observation captured   (capture-observation.sh after every Write/Edit)
        │
        ▼
Text embedded          (fire-and-forget via Phase B `upsert_embedding`)
        │
        ▼
Pattern extracted      (cos_learn_extract — k-means style over outcomes)
        │
        ▼
Pattern validated      (cos_learn_validate — was it helpful?)
        │                   │ yes: LTP boost (confidence + 0.05 × temporal proximity)
        │                   │ no:  LTD penalty (confidence × 0.85)
        ▼
High-confidence rule   (cos_promote → moves to core/rules/ as policy)

Parallel pipeline for breakthroughs:
   rework → success transition
        │
        ▼
Narrative captured     (cos_learn_narrative)
        │
        ├── outcome_history row (DB)
        ├── learned_pattern with high impact_score
        └── docs/breakthroughs/<TASK-ID>-<slug>.md (filed back)
```

---

## 11. Two Principles That Drive Everything

### SSOT (Single Source of Truth)
Every asset — hook, skill, rule, command — exists in exactly one location under `core/` or `templates/`. Projects get symlinks. `cos update` keeps them fresh. `cos eject` or `cos eject-file` converts to copies when a user needs to customize.

### Idempotent + Non-destructive
- `cos init` on an already-initialized project → offers sync, never overwrites
- `cos update` → adds missing, removes orphans, **never** touches `docs/`, `AGENTS.md`, or user-ejected files
- `cos setup` → idempotent per file (existing PRD files skipped)
- All hooks fail-closed + report reasons, never silently succeed
- `.coding-os/installed-manifest.json` records what we manage so we know what we own

---

## 12. Quick Reference: "Which command do I need?"

| Situation | Command |
|---|---|
| Starting a brand-new project | `cos init` |
| I pulled a new version of coding-os, my projects need the new hooks | `cos update` |
| Project feels empty — no PRD | `cos setup` |
| Adding an agent after init | `cos add-adapter codex` |
| Adding a stack after init (backend was missing) | `cos add-stack fastapi` |
| Something's wrong — not sure what | `cos doctor` |
| Want to fork a policy doc without affecting upstream | `cos eject-file docs/workflow-docs/workflow-guide.md` |
| Want the project self-contained (no more symlinks) | `cos eject` |
| Ready to query the docs via RAG | `cos docs-index` |
| Ready to query the tasks graph | `cos task-sync` |
| Just want to start the MCP server manually | `cos server-start` |

---

## 13. What's New in v0.2.0 (this session, phases D.1–D.6)

| Phase | Delivered |
|---|---|
| **D.1** | Stack-skill auto-linking (fix critical B1 bug) · `cos server-start` portable MCP · `.coding-os.yaml.verify` auto-populated · Doctor checks C13 + C14 |
| **D.2** | Interactive `cos init` with prompts · `--yes` flag for CI · Idempotent detection on re-run · Multi-agent init (`-a claude,codex`) |
| **D.3** | `cos update` command · manifest-diff + dry-run + orphan cleanup · `installed-manifest.json` snapshot |
| **D.4** | `cos setup` command · 3 modes (interactive / import-prd / skip) · PRD keyword classifier (11 targets + misc) |
| **D.5** | `cos eject-file <path>` for fine-grained customization |
| **D.6** | `uv tool install --editable .` packaging · v0.2.0 version bump · `cos` on PATH |

Tests: **985 passing, 0 failing.** Commands: **16** (was 13).

See [development-roadmap.md § Phase D](./development-roadmap.md) for the per-phase plan and verification matrix.
