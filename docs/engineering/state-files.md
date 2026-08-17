<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# State Files — Design, Ownership, and Multi-Agent Isolation

Purpose: Canonical explanation of what lives under `.coding-os/`, how state files prove ownership, how two agents running against the same project stay isolated, and why the `.claude/.*` state files are gone.

Read when: Adding a new session-scoped marker · debugging a "session mismatch" BLOCK · planning a multi-agent (Claude + Codex) workflow on one repo · considering moving any of this to the database.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Project-root resolution — how `$COS_STATE_DIR` is found

Every hook and every Python entry point must agree on **one** project root, or
they split-brain: a hook firing with `cwd != repo root` (e.g. `cd src/backend &&
go build`) would lazily create a stray nested `.coding-os/` at the subdir while
the long-lived MCP server correctly uses the real root (this was the
nested-`.coding-os` bug; the phantom-Hub-project class is TASK-117).

The resolver in [`cos-env.sh`](../../src/core/hooks/cos-env.sh) applies this
precedence, and **only** when `COS_STATE_DIR` is still the bare default
(`.coding-os`):

1. **Explicit `COS_STATE_DIR`** (any non-default value) → used verbatim.
2. **`$CLAUDE_PROJECT_DIR`** set → `$CLAUDE_PROJECT_DIR/.coding-os`. (Claude Code
   exports this in most runtimes — but **not** the VSCode native extension,
   where it is unset; that gap is why steps 3–4 exist.)
3. **`$COS_PROJECT_ROOT`** set → `$COS_PROJECT_ROOT/.coding-os`. Explicit escape
   hatch a consumer can export (e.g. in VSCode `settings.json`).
4. **Upward marker-walk** from `$PWD` (resolved with `cd -P`, Critical Rule 5):
   accept the first ancestor that has a `.coding-os/` directory **and**
   co-locates one of the root markers; else fall back to the innermost bare
   `.coding-os/`. This skips a stray nested `.coding-os/` left by a pre-fix run.
5. **No match** → the relative `.coding-os` default (legacy behavior; no root
   could be proven, so we do not guess).

**Worktree routing (pr-mode, TASK-515).** When `$PWD` is inside a git worktree
under `~/.coding-os/worktrees/` (or `$COS_WORKTREE_ROOT`), the resolver overrides
the precedence above: `$COS_PROJECT_ROOT` (exported by the `cos pr` dispatch) is
authoritative, else the main repo is recovered git-natively via
`git rev-parse --git-common-dir`. So every worktree of one repo shares that
repo's single `$COS_STATE_DIR` (DB, board, presence, the `test-governor`
`.test-run.lock`). If resolution would bind worktree state to the **global hub**
(`$HOME/.coding-os`) it is **refused** (`COS_STATE_MISROUTE=1`, surfaced to
stderr) rather than silently written. See [pr-workflow.md § 3](../playbooks/pr-workflow.md).

**Root markers** (a `.coding-os/` is the *real* root only if one is co-located):
`.git`, `.coding-os.yaml`, `pyproject.toml`, `package.json`, `go.mod`,
`AGENTS.md`. This set is the **SSOT** in
[`database.py::_ROOT_MARKERS`](../../src/core/thinking_os/database.py); the
`cos-env.sh` walk mirrors it exactly. `.git` alone never anchors (it must
co-locate a `.coding-os/`), so a parent monorepo `.git` cannot hijack the walk.

**`$HOME` hard-stop.** The shell walk stops *below* `$HOME` and `/`: it never
inspects or accepts `$HOME/.coding-os`, which is the **global hub** state
(registry of all projects), not a project root. Paths are `cd -P`-resolved
before the `$HOME` comparison so a `/tmp → /private/tmp` symlink (macOS) cannot
defeat it (Critical Rule 5).

**Drift guard.** `cos-env.sh` and `database.py` are two implementations of one
contract. `tests/test_hooks.py` asserts (a) their marker lists are identical and
(b) they resolve the same root for a battery of fixture trees — so the mirror
can never silently drift. The Python-side `$HOME` hard-stop and the
consolidation of the remaining cwd-only Python resolvers onto this one contract
are tracked in **TASK-498**.

### The multi-project exception — the Hub daemon starts env-clean

Precedence rule 1 (explicit `COS_STATE_DIR` wins) is right for a hook or a CLI
command: each runs *inside* one project, and an explicit override is the
operator saying which. It is **wrong for the Hub daemon**, which serves every
registered project and resolves each one per request from the
`/api/p/<slug>/` middleware. A single ambient `COS_STATE_DIR` pins that whole
server to one directory — and the daemon outlives the shell that set it, so the
pin is invisible from then on.

`cos hub start` therefore **strips** two var groups before the server binds —
the **project-scoped** ones that name *which* project (`COS_STATE_DIR` ·
`COS_DB_PATH` · `COS_PROJECT_ROOT` · `COS_LOG_FILE` · `COS_AGENT_DIR` ·
`COS_PANEL_DIR`) and the **session-scoped** ones that name *which* panel wrote
them (`COS_PANEL_ID` · `COS_SESSION_FILE` · `COS_SESSION_ID` · `COS_AGENT` ·
`COS_HOOK_LOG` · `COS_HOOK_BLOCK_LOG`). Machine-wide knobs
(`COS_GRAPH_BACKEND`, `COS_LOG_LEVEL`, `PATH`, …) pass through untouched — they
name *how* the server runs, not *which project* it is. Both the detached spawn
and a direct `--foreground` run scrub, because the `service install` unit and
the detached path both end at `cos hub start --foreground` — that process *is*
the daemon.

The two groups are one SSOT tuple pair, `PROJECT_SCOPED_ENV_VARS` /
`SESSION_SCOPED_ENV_VARS` in
[`_db_paths.py`](../../src/core/thinking_os/_db_paths.py) (re-exported from
`thinking_os.database`), beside the project-root resolver they undo. The Hub
daemon drops both groups; the nightly maintenance child
(`web/routes/scheduled.py`) drops the project-scoped group for the same reason —
it runs one *named* project and must not inherit the Hub's launch directory.

The failure this prevents is silent, not loud. A shell that had leaked a pytest
fixture's `COS_STATE_DIR` started a Hub that served the whole UI from a
`/private/tmp/pytest-of-*/` directory: adapters read `installed: false` (no
`.coding-os.yaml` there), Agent Supervision read as off however many times the
operator enabled it (no `hub-settings.json` there), and the board rendered a
throwaway test database. Every panel painted successfully — with the wrong
project's data, and no error anywhere. Env-clean startup is what makes the
per-request resolution above the *only* way a project is chosen. `SessionStart`
surfaces `COS_STATE_DIR` on stderr when it is not the resolved project's own, so
a poisoned *shell* is still visible even though the daemon now ignores it.

## The split — shared root vs. agent-private subdir vs. panel-private subdir (three-tier scope)

```
.coding-os/                              ← SHARED root  ($COS_STATE_DIR)
├── .agent                                  adapter identity marker (written by install.sh)
├── .hooks.log                              append-only hook log (every line tagged agent=X session=Y task=Z)
├── .capture-errors.log                     capture.py stderr on failure (synchronous since TASK-048)
├── .dogfood-reminded                       10-min debounce for remind-dogfood
├── .last-decay / .last-verify*             singleton timestamps
├── coding-os.db + -shm + -wal              SQLite brain (WAL = shared reader; one writer lock)
├── domain-config.json                      project config (routing, paths)
├── rag-config.yaml                         doc indexer config
├── installed-manifest.json                 what `cos init` installed
├── subsystems-state.json                   module toggles {"disabled": [...]} — absent = all on,
│                                           created lazily by cli/subsystems.py (TASK-349)
├── Makefile.base                           inherited make targets
│
├── claude/                              ← AGENT-PRIVATE  ($COS_AGENT_DIR for Claude)
│   ├── .agent · .model · .task-mode        ┐
│   ├── .swimlane · .turn-activity.log      ├ SHARED across panels of this agent
│   ├── .active-session                     │ fresh "latest active session" pointer
│   ├── sessions/<sid>.json                 │ (presence, panel-id-agnostic by design)
│   ├── traces/<sid>.jsonl                  ┘
│   │
│   └── panels/<panel-id>/               ← PANEL-PRIVATE  ($COS_PANEL_DIR for this panel)
│       ├── session-id                      ses-claude-YYYYMMDD-HHMMSS-xxxx
│       ├── heartbeat                       unix ts, written every hook fire (orphan GC signal)
│       ├── .task-current                   "<session-id> <task-name>"
│       ├── .thinking_os-gate               "<session-id> <CYNEFIN> <DIMS>"
│       ├── .zoom-checkpoint                "<session-id> PROBLEM_FRAMED"
│       ├── .doc-anchor                     "<session-id> task:<id>\n<doc paths>"
│       ├── .memory-check                   "cos_search:<query>" (auto-written by the cos_search MCP tool; write-state self-attest is the fallback)
│       ├── .active-skill                   "<session-id> skill1 skill2 …"
│       ├── .active-formula                 active cognition formula id
│       ├── .learn-suggestions              learn-suggest payload for this prompt
│       └── .intent.json                    extract_intent.py output for current turn
│
└── codex/                               ← AGENT-PRIVATE  ($COS_AGENT_DIR for Codex)
    ├── …                                   same shape as claude/
    └── panels/<panel-id>/               ← per-Codex-panel state
```

**Rule of thumb (two axes):**
- If two *agents* (Claude + Codex) attached to the same repo could have DIFFERENT answers, the file is **agent-private** → lives at `$COS_AGENT_DIR/`.
- If two *panels of the same agent* (two Claude tabs) could have DIFFERENT answers, the file is **panel-private** → lives at `$COS_PANEL_DIR/` (`$COS_AGENT_DIR/panels/<panel-id>/`).
- If there's only one correct answer (DB row, install manifest, log stream, runtime model, task-mode classifier output), it's **shared** → lives at `$COS_STATE_DIR/` or `$COS_AGENT_DIR/` per scope.

### Calling-agent resolution

`COS_AGENT` is an execution-boundary value. Rendered adapter hook commands set it explicitly, and the Codex project config sets it for Codex shell and MCP subprocesses. Runtime-specific markers are secondary signals. `.coding-os/.agent` is a legacy fallback for a plain shell and may reflect whichever adapter was installed last; it must never be used to distinguish concurrent adapters in a multi-adapter project.

The installed-adapter list comes from `.coding-os.yaml::agents`. The calling runtime comes from its adapter-owned environment. Keeping those concepts separate prevents Codex Desktop from writing a GPT-backed session under `.coding-os/claude/` merely because Claude was installed most recently.

### `.active-session` — attribution for the long-lived MCP server (TASK-094)

Task `agent_session` attribution faces an architectural seam: the MCP
server is a long-lived process that has **no `$COS_PANEL_DIR`**, so it
cannot read the strict per-panel `session-id`. Reading the flat
agent-level `session-id` is wrong — that file is a stale fossil from
whichever panel last wrote it (the shell reader at `cos-env.sh` refuses
it for the same reason).

`session-context.sh` therefore refreshes `$COS_AGENT_DIR/.active-session`
with the current panel's session-id on **every prompt**. The resolvers
(`server.py::_detect_agent_session_default`, `board_commands.py::_agent_session_id`,
and `_agent_runtime.py::resolve_agent_session` — the board-write
attribution path, aligned in TASK-168) read, in order: (0)
`$COS_PANEL_DIR/session-id` / `$COS_SESSION_FILE` when a panel dir is in
env (hook/CLI callers — exact), (1) `$COS_AGENT_DIR/.active-session`
(fresh, MCP-server path), (2) the legacy `session-id` fossil, (3) a
`ses-<agent>-mcp-<pid>` synth. Before TASK-168 the board-write path
skipped step (1) and fell straight to the synth, so every MCP-created
task shared one `ses-<agent>-pid<server-pid>` id — collapsing
per-session WIP across panels.

**Concurrent-panel caveat:** `.active-session` is last-writer-wins, so a
task mutated via MCP would otherwise be attributed to the *most recently
active* panel. As of TASK-212 the `inject-mcp-caller-session` PreToolUse
hook closes this for the attribution-critical tools: it threads the
calling panel's session into the args of `cos_task_move`,
`cos_task_create`, and `cos_work_log_append` via
`hookSpecificOutput.updatedInput`, and `resolve_agent_session` treats the
injected explicit `agent_session` as its highest-priority signal — so
those writes are attributed to the REAL calling panel even under genuinely
simultaneous panels. The `.active-session` pointer remains the fallback
for MCP tools the hook does not cover and for runtimes without PreToolUse
argument injection (bounded by adapter hook capability — Claude-first; a
per-session MCP server would be the alternative for a runtime that cannot
inject).

The single source of truth for which cognitive markers are panel-private is `$COS_PER_PANEL_FILES` in [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh) — appending a basename to that list makes the writer (`write-state.sh`) and reader (`check-state.sh`) auto-route from then on; no per-hook edits needed.

## Panel-id resolution — multi-adapter, data-driven

Two panels of the same agent get distinct `$COS_PANEL_ID` values via the resolver in `cos-env.sh::_cos_resolve_panel_id`:

1. **Explicit override** — `$COS_PANEL_ID` env (tests, manual debugging).
2. **Stdin `session_id`** — every Claude / Codex hook payload carries one; `cos_panel_upgrade_from_payload <payload>` refines `$COS_PANEL_ID` right after the hook reads stdin. Strongest signal.
3. **Adapter env vars** — declared per adapter in [src/adapters/`<id>`/adapter.yaml `::runtime_session_marker`](../../src/adapters/claude/adapter.yaml). Probed in order: `CLAUDE_CODE_SESSION_ID` · `CLAUDE_SESSION_ID` · `CODEX_SESSION_ID` — the **authoritative** list is the hardcoded loop in `cos-env.sh::_cos_resolve_panel_id`. **Adding a new agent (e.g. Gemini)** means: add its `runtime_session_marker` block + adapter dir **and** add its session env var to that probe loop — the shell kernel cannot parse `adapter.yaml` at source-time, so the probe is a hand-maintained mirror, not auto-derived (the earlier "zero code change in `src/core/`" claim was wrong: ≥1 shell edit is required). `tests/test_adapter_session_marker_probe_parity.py` (TASK-213) enforces `adapter.yaml::runtime_session_marker.env_vars ⊆ the probe` so the mirror can never silently drift. *(TASK-054: Claude Code actually exports `CLAUDE_CODE_SESSION_ID`, not the originally-guessed `CLAUDE_SESSION_ID`; the wrong name meant this ladder silently missed and Claude fell to the fragile PPID fallback below — verified & corrected 2026-06-01.)*
4. **PPID-derived hash** — last resort for raw shell tests. Format `ppid-<8hex>`. Stable per parent process; documented as best-effort because PPID semantics differ across raw bash vs SDK-spawned hooks.

> **Operational warning (PPID fallback fragility).** The `ppid-<hash>` form is stable per *parent* process — i.e. per Claude Code daemon, per terminal shell. It is NOT stable when an agent runtime spawns hook subprocesses through a fresh shell each time (some CI runners, certain `bash -c` invocation patterns). For production multi-panel correctness, **stdin `session_id` is the primary contract**; the env-var ladder is a secondary fallback; PPID is the last-resort safety net so panels never collapse to an empty identifier. If you ever see >5 `ppid-*` subdirs accumulating per agent in normal use (visible via `ls .coding-os/<agent>/panels/`), the runtime is not propagating its session identity — file a bug rather than relying on the fallback at scale.

## Session-id format — identity in the name itself

```
ses-<agent>-YYYYMMDD-HHMMSS-<4-hex-random>
```

Example: `ses-claude-20260418-201128-1945` / `ses-codex-20260418-201132-c0d3`.

Generated by `session-context.sh` on `SessionStart:startup`. Three properties:

1. **Agent-embedded** — reading any session-id tells you which runtime wrote it. Logs become self-describing without an extra field (the `agent=` field is still emitted for grep-filter ergonomics, but the session-id alone would suffice).
2. **Monotonic** — UTC timestamp means `sort` gives chronological order across sessions.
3. **Collision-safe** — 16-bit random suffix makes same-second start of two agents still distinct (ses-claude-YYYYMMDD-HHMMSS-xxxx ≠ ses-codex-YYYYMMDD-HHMMSS-yyyy).

## State file format — proof of ownership

Every state file is written by [src/core/hooks/write-state.sh](../../src/core/hooks/write-state.sh) with a fixed shape:

```
<session-id> <value>
```

Example from `.coding-os/claude/.task-current`:

```
ses-claude-20260418-201128-1945 TASK-043
```

First whitespace-separated token is the session-id, everything after is the value. Reader hooks (`enforce-*`, `check-state.sh`) always verify the session-id BEFORE trusting the value:

```bash
# check-state.sh (simplified)
file_session=$(head -1 "$STATE_FILE" | awk '{print $1}')
[[ "$file_session" != "$COS_SESSION" ]] && STATE_VALID=false
[[ $(file_age) -gt $MAX_AGE ]]           && STATE_VALID=false
```

This gives three layers of proof:
- **Session-id match** — "I wrote this *this run*"
- **Freshness** — "still within the ownership horizon" (default 120 min for gate/skill, 8 h for task)
- **Agent-scoped dir** — "the other agent's state cannot spoof mine because they live in a different directory"

The `session-id` also contains the agent prefix, so even a stale file from the OTHER agent that somehow leaked into this dir would fail the session-id compare.

## Why `.claude/.*` is gone

Before 2026-04, state files lived at `.claude/.active-skill`, `.claude/.task-current`, etc. When `COS_STATE_DIR` was moved to `.coding-os/`, a fallback in `cos-env.sh` kept reading `.claude/` if nothing existed in `.coding-os/`. The fossil files in `.claude/` were never re-written but the fallback made them look live.

As of this change:
- The 6 fossil state files under `.claude/` are deleted (see commit for this session).
- The legacy fallback branch in `cos-env.sh` is removed.
- `.claude/` now contains ONLY what Claude Code needs natively: `settings.json`, `settings.local.json`, `commands/`, `hooks/`, `rules/`, `skills/`.

`.codex/` never had state fossils — it was built correctly from the start.

## Multi-agent scenarios — how the design handles them

### S1 — Solo dev, single agent (most common)

Persona: one human, uses Claude Code only. `.coding-os/claude/` has all the state; `.coding-os/codex/` may not even exist.

- On `startup` → new `ses-claude-…` id written to `.coding-os/claude/session-id`.
- Previous state files in `.coding-os/claude/` are cleared.
- All hooks read `$COS_AGENT_DIR` = `.coding-os/claude/`.

Outcome: identical to the pre-split design. Zero overhead, zero functional change.

### S2 — Agent switch (serial, same project)

Persona: dev uses Claude for backend work, closes it, opens Codex for a refactor.

- Claude session ends → `.coding-os/claude/session-id` stays (fossil for next Claude run, safely ignored on its next startup).
- Codex opens → `session-context` runs in Codex runtime, `COS_AGENT=codex`, writes `ses-codex-…` to `.coding-os/codex/session-id`.
- Hooks during Codex run read `.coding-os/codex/.*`. Claude's stale state is untouched.

Outcome: perfect isolation. Each agent's history in `.hooks.log` is filterable via `cos hooks-log --agent claude` vs `--agent codex`.

### S3 — Multi-agent concurrent (Claude + Codex on one repo)

Persona: Claude in terminal A, Codex in terminal B, both attached to the same repo at the same time.

- Each agent's SessionStart generates its own `ses-{agent}-…` id into its own `$COS_PANEL_DIR`. **No shared file is overwritten.**
- Each agent's hook state (task, gate, skill) writes to its own panel dir under its own agent dir.
- Shared DB writes (observations from capture-observation) use WAL — multiple readers, one writer at a time. SQLite serializes writes; each observation row carries its `session_id` and any schema column also implicitly carries the agent prefix, so cross-agent analytics stay separable.
- `.hooks.log` is append-only text — both agents write to it, each line tagged `agent=X`. `cos hooks-log --agent claude` gives Claude's stream.

Outcome: no thrashing.

### S7 — Multi-panel same agent (two Claude tabs on one repo)

Persona: two panels (browser tabs, terminals, IDE windows) of the same Claude on the same project, working different tasks in parallel.

- Each panel's SessionStart receives a distinct stdin `session_id` from the Claude runtime → `cos_panel_upgrade_from_payload` writes `$COS_PANEL_ID` accordingly, and `session-context.sh` materialises `$COS_AGENT_DIR/panels/<panel-id>/` with its own `session-id`, `.task-current`, `.thinking_os-gate`, etc.
- The startup-time cleanup loop in `session-context.sh` is scoped to `$COS_PANEL_DIR` only — sibling panels' state is untouched.
- Shared per-agent state (`.model`, `.task-mode`, `.swimlane`, presence `sessions/<sid>.json`, traces, the DB) stays at `$COS_AGENT_DIR` / `$COS_STATE_DIR`.
- `auto-brain-decay.sh` reaps `panels/<panel-id>/` subdirs whose `heartbeat` is older than `$COS_PANEL_GC_TTL` (default 24h). Live panels rewrite `heartbeat` on every hook fire (`cos-env.sh` line ~140), so an active session is never collected.
- Coverage: regression locked by `tests/test_panel_isolation.py` and `tests/test_cos_env_panel_resolution.py`.

Outcome: per-panel isolation. The "two panels share `$COS_AGENT_DIR/session-id`, last `SessionStart` wins" failure mode that previously required a `git worktree` workaround is eliminated.

**Remaining limitation:** the SQLite DB is still a single writer at a time. Under heavy concurrent observation capture (thousands of edits/sec), WAL may throttle. In practice the aggregate throughput across two or three panels is low enough that this is not measurable.

### S4 — Session abandoned (laptop closes mid-task)

Persona: Claude running, laptop lid closes without `Stop` firing.

- `.coding-os/claude/session-id` still points at the abandoned session.
- On next Claude startup, `session-context.sh` runs `session_summary.py` idempotently for the PREVIOUS `session-id` **before** overwriting it — observations from the abandoned session get rolled up into a summary row. Then a fresh `ses-claude-…` is generated.
- `.coding-os/claude/.*` volatile markers are cleared.

Outcome: no observation loss, no zombie session-id bleeding into the next chat. Fully covered by [src/core/thinking_os/tests/test_session_recovery.py::TestOrphanSessionRecovery](../../src/core/thinking_os/tests/test_session_recovery.py).

### S5 — Context compact (Claude compacts mid-chat)

Persona: long Claude chat, context gets compacted, same session-id continues.

- `SessionStart:compact` → `session-context` does NOT generate a new id, does NOT clear state.
- Emits the minimal **recovery card** (the 5 critical Workflow Rules + the `[Session State]` gate/task/skill line) as a hidden `additionalContext` envelope — never operator-visible stdout — so the post-compact agent doesn't forget them. Recovery is the **floor**: it is re-injected on every source, so a compacted agent is never blinded.
- **Suppresses the heavy digest on `compact`.** `[Agent Digest]`, trajectory, routing, and token-economics run on `startup`/`resume` only. A same-session compact still holds the regenerable digest in working memory, so re-emitting it was the wasted re-dump that put a multi-thousand-token wall mid-chat. Channel + tier contract: [transparency-banner.md § SessionStart emission](../../src/core/rules/transparency-banner.md).
- State files stay valid, session-id unchanged, mtime unchanged.

Outcome: compact is transparent to the hook layer. The agent's working state survives, and the operator no longer sees a re-primed wall mid-chat.

### S6 — Fresh `cos init` (new consumer project)

Persona: user runs `cos init --stack django --agent claude` in an empty dir.

- `cos init` creates `.coding-os/` with `installed-manifest.json`, `.agent=claude`, stack-linked skills.
- `src/adapters/claude/install.sh` writes `.agent` again (idempotent) and regenerates `.claude/settings.json`.
- First agent action triggers `SessionStart:startup` → creates `.coding-os/claude/`, writes first `ses-claude-…`.
- `.coding-os/codex/` stays absent until codex adapter is added.

Outcome: correct-by-construction. Nothing touched outside the chosen agent's subdir.

## Personas × scenarios matrix

| | P1 Solo-Claude | P2 Solo-Codex | P3 Dual-serial | P4 Dual-concurrent | P5 Power-user w/ worktrees | P6 Multi-panel same agent |
|---|---|---|---|---|---|---|
| **S1 normal session** | ✅ panel under `claude/panels/` | ✅ panel under `codex/panels/` | ✅ each uses own dir when active | ✅ both dirs coexist | ✅ each worktree has own `.coding-os/` | ✅ each panel under its own `panels/<id>/` |
| **S2 agent switch** | N/A | N/A | ✅ clean handoff, stale dir ignored on next run | ✅ no handoff needed | ✅ per-worktree anyway | N/A (same agent) |
| **S3 concurrent** | N/A | N/A | N/A | ✅ no file contention | ✅ different filesystems | ✅ no panel contention |
| **S4 abandoned** | ✅ orphan recovery | ✅ orphan recovery | ✅ each agent recovers own | ✅ per-agent recovery | ✅ per-worktree recovery | ✅ panel-dir GC + per-panel orphan summary |
| **S5 compact** | ✅ transparent | ✅ transparent | N/A | ✅ each agent compacts independently | ✅ per worktree | ✅ each panel compacts independently |
| **S6 fresh init** | ✅ only claude dir | ✅ only codex dir | ✅ add-adapter later | ✅ add-adapter later | ✅ per worktree | ✅ each panel materialises its own subdir |
| **S7 multi-panel** | N/A | N/A | N/A | N/A | N/A (already isolated by FS) | ✅ panel-id from stdin/env/PPID |

**Every cell resolves safely.** The two historical failure modes (P4 × S1 with the old shared session-id file, and P6 × S7 with two panels racing on `$COS_AGENT_DIR/session-id`) are both eliminated; the `git worktree` workaround for P6 is no longer needed and the corresponding fallback paragraph has been removed.

## What intentionally stays shared

Question: "should `.hooks.log` also be per-agent?"

Answer: **no**. A shared log with `agent=X` tag gives you one chronological stream, filterable in any direction. Per-agent logs would split the timeline and lose the ability to see "Claude edited X, then Codex saw the git status change and reacted" causality.

Similarly `coding-os.db` is shared because:
- Observations across agents should analyze together ("which agent gets what rework rate?")
- Learned patterns are universal knowledge
- DB rows carry `session_id` (which includes agent) — analytics can split if needed

Explicitly shared things:
- `.hooks.log` — one stream, agent-tagged
- `coding-os.db` — one brain, session-tagged
- `installed-manifest.json` — one install
- `.agent` — identity marker (written by install.sh, not mutated per session)
- `domain-config.json`, `rag-config.yaml` — one project config

### WAL size discipline — the cap and the guard

Sharing one DB across long-lived MCP servers, Hub, and every hook subprocess
makes `coding-os.db-wal` the one state file that can grow without bound. It did:
**59.29 GB of WAL against a 342 MB database**, taking the boot volume to 92%
full, while `PRAGMA wal_checkpoint(PASSIVE)` reported only 531 live frames. The
WAL was not full of data — it was a never-truncated high-water mark, because
SQLite's default `journal_size_limit = -1` means "after a checkpoint, keep the
file at whatever size it once reached". Three stale server processes (up 11d,
5d, and 4d) had each pinned a read snapshot long enough to block checkpointing;
once the file had grown, nothing ever gave the space back.

Two mechanisms, deliberately at different layers:

| Layer | Mechanism | Fires |
|---|---|---|
| Connection | `PRAGMA journal_size_limit` in [`apply_pragmas`](../../src/core/thinking_os/_db_pool.py) | at every WAL restart, on every connection opened through the pragma SSOT |
| Session | WAL guard in [`auto-brain-decay.sh`](../../src/core/hooks/auto-brain-decay.sh) → [`wal_guard.py`](../../src/core/hooks/_helpers/wal_guard.py) | SessionStart, only when the `-wal` is over threshold |

The cap is the fix; the guard is the safety net for the case the cap cannot
reach — a checkpoint blocked by a reader holding a snapshot. The cap
(**32 MB**) sits above the `wal_autocheckpoint = 1000` target (~4 MB of 4 KB
pages), so normal operation never pays for a truncate, and below the 50 MB
`state.size_within_budget` budget `cos doctor` warns at, so a healthy WAL never
trips that check.

**The cap applies at the WAL *restart*, not at the checkpoint** — measured on
SQLite 3.50.4, an over-cap WAL is still at its high-water size the instant
`wal_checkpoint(RESTART)` returns, and shrinks to the cap on the *next write*,
when the log wraps back to frame 0. Probing straight after a checkpoint
therefore makes the pragma look ignored; it is not. Two consequences worth
holding onto: a continuously-written database (this one — every hook fire and
observation writes) stays bounded on its own, and an idle-but-pinned database
never restarts its WAL at all, which is precisely the gap the SessionStart
guard covers.

The guard stats the `-wal` first and returns without opening the database when
it is under threshold (`COS_WAL_GUARD_MB`, default 50 — the same number
`cos doctor` warns at, so "over budget" means one thing). Over threshold it
forces `PRAGMA wal_checkpoint(TRUNCATE)` and reports the reclaimed bytes on
stderr, the operator-visible channel.

**When TRUNCATE returns `busy=1`, a reader is the blocker and no amount of
retrying will help** — so the guard names the PIDs holding the `-wal` open
(`lsof`, with command and elapsed time) instead of reporting a generic failure.
That line is the whole diagnostic: the 59 GB incident cost hours precisely
because "checkpoint didn't work" did not say *who* was preventing it. Kill the
named stale process and the next SessionStart reclaims the space.

Manual recovery, when a session start is not imminent:

```bash
sqlite3 .coding-os/coding-os.db 'PRAGMA wal_checkpoint(TRUNCATE);'   # → (busy, log, checkpointed)
lsof -- .coding-os/coding-os.db-wal                                  # busy=1 → who is holding it
```

## Migration behavior

For existing projects:

1. `make sync` picks up the new code and runs install.sh for each adapter.
2. On next SessionStart, `session-context.sh` creates `.coding-os/<agent>/` if missing and writes `session-id` there.
3. Existing `.coding-os/session-id` (flat) is NOT auto-migrated — it's left in place until the user deletes it or `session-context.sh` ignores it (new code reads only `.coding-os/<agent>/session-id`).
4. The 6 `.claude/.*` fossils can be safely deleted at any time (`rm -f .claude/.{active-skill,doc-anchor,task-current,thinking_os-gate,zoom-checkpoint,memory-check,session-id}`).

No DB migration needed — the session-id format evolution is a string change, not a schema change. Existing rows with the old format (`ses-YYYYMMDD-…`) remain valid; new rows use the new format.

## Should any of this be in the DB?

Tradeoff analysis (deferred, per user request):

- **Pro DB:** atomic multi-key reads, transactional clear-on-session-end, cross-agent queries like "what was the last 3 sessions' gate classification?"
- **Pro files:** zero dependency on MCP server liveness (files work when MCP is down), readable with `cat`, editable with `$EDITOR` for emergency overrides, backup-friendly.

**Verdict for now:** keep files. The "MCP is down" failure mode is important — when the user sees `warn-mcp-down` the hook layer still works because state is on disk. Moving to DB would make the hook layer depend on MCP liveness, which breaks the safety net exactly when it's needed most.

Revisit when:
- >10 distinct state markers exist (we have 7 today)
- Multi-host usage (agents on different machines sharing one project) — then DB becomes the natural sync point.

## Debugging cheat sheet

```bash
# "who am I?" — agent + session + task identity
source src/core/hooks/cos-env.sh
echo "agent=$COS_AGENT session=$(cos_current_session) task=$(cos_current_task)"

# inspect all markers for this agent
ls -la $COS_AGENT_DIR/

# see last 20 log lines for just my runtime
cos hooks-log --agent $COS_AGENT -n 20

# compare claude vs codex activity side by side
cos hooks-log --agent claude -n 10 && echo '---' && cos hooks-log --agent codex -n 10

# force a fresh session (rare)
rm -f $COS_AGENT_DIR/session-id $COS_AGENT_DIR/.{task-current,thinking_os-gate,zoom-checkpoint,active-skill,doc-anchor,memory-check}
```

## References

- [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh) — `COS_AGENT_DIR` definition + detection logic
- [src/core/hooks/session-context.sh](../../src/core/hooks/session-context.sh) — session lifecycle + orphan recovery
- [src/core/hooks/write-state.sh](../../src/core/hooks/write-state.sh), [check-state.sh](../../src/core/hooks/check-state.sh) — the read/write protocol
- [docs/engineering/hooks-reference.md](hooks-reference.md) — catalog of every hook that reads state
- [docs/engineering/adapter-parity.md](adapter-parity.md) — which state-gated hooks fire on which adapter
- AGENTS.md Rule 1 & Rule 5 — canonical policy summary
