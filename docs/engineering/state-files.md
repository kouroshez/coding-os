<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-18 -->
# State Files — Design, Ownership, and Multi-Agent Isolation

Purpose: Canonical explanation of what lives under `.coding-os/`, how state files prove ownership, how two agents running against the same project stay isolated, and why the `.claude/.*` state files are gone.

Read when: Adding a new session-scoped marker · debugging a "session mismatch" BLOCK · planning a multi-agent (Claude + Codex) workflow on one repo · considering moving any of this to the database.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## The split — shared root vs. agent-private subdir

```
.coding-os/                              ← SHARED root  ($COS_STATE_DIR)
├── .agent                                  adapter identity marker (written by install.sh)
├── .hooks.log                              append-only hook log (every line tagged agent=X session=Y task=Z)
├── .capture-errors.log                     background capture.py errors
├── .dogfood-reminded                       10-min debounce for remind-dogfood
├── .last-decay / .last-verify*             singleton timestamps
├── coding-os.db + -shm + -wal              SQLite brain (WAL = shared reader; one writer lock)
├── domain-config.json                      project config (routing, paths)
├── rag-config.yaml                         doc indexer config
├── installed-manifest.json                 what `cos init` installed
├── Makefile.base                           inherited make targets
│
├── claude/                              ← AGENT-PRIVATE  ($COS_AGENT_DIR for Claude)
│   ├── .agent · .model · .task-mode        ┐
│   ├── .swimlane · .turn-activity.log      ├ SHARED across panels of this agent
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
│       ├── .memory-check                   "<session-id> cos_search:<query>"
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

The single source of truth for which cognitive markers are panel-private is `$COS_PER_PANEL_FILES` in [src/core/hooks/cos-env.sh](../../src/core/hooks/cos-env.sh) — appending a basename to that list makes the writer (`write-state.sh`) and reader (`check-state.sh`) auto-route from then on; no per-hook edits needed.

## Panel-id resolution — multi-adapter, data-driven

Two panels of the same agent get distinct `$COS_PANEL_ID` values via the resolver in `cos-env.sh::_cos_resolve_panel_id`:

1. **Explicit override** — `$COS_PANEL_ID` env (tests, manual debugging).
2. **Stdin `session_id`** — every Claude / Codex / Cursor hook payload carries one; `cos_panel_upgrade_from_payload <payload>` refines `$COS_PANEL_ID` right after the hook reads stdin. Strongest signal.
3. **Adapter env vars** — declared per adapter in [src/adapters/`<id>`/adapter.yaml `::runtime_session_marker`](../../src/adapters/claude/adapter.yaml). Probed in order: `CLAUDE_SESSION_ID` · `CURSOR_SESSION_ID` · `CURSOR_TRACE_ID` · `CODEX_SESSION_ID` · `GEMINI_SESSION_ID` · `ANTHROPIC_SESSION_ID`. **Add a new agent (e.g. Gemini) = add its `runtime_session_marker` block and adapter dir; zero code change** anywhere in `src/core/`.
4. **PPID-derived hash** — last resort for raw shell tests. Format `ppid-<8hex>`. Stable per parent process; documented as best-effort because PPID semantics differ across raw bash vs SDK-spawned hooks.

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

Outcome: no observation loss, no zombie session-id bleeding into the next chat. Fully covered by [src/core/thinking_os/tests/test_session.py::TestOrphanSessionRecovery](../../src/core/thinking_os/tests/test_session.py).

### S5 — Context compact (Claude compacts mid-chat)

Persona: long Claude chat, context gets compacted, same session-id continues.

- `SessionStart:compact` → `session-context` does NOT generate a new id, does NOT clear state.
- Prints the Workflow Rules reminder (task management · Verification Matrix · Complexity Gate · Domain skill) so the post-compact agent doesn't forget them.
- State files stay valid, session-id unchanged, mtime unchanged.

Outcome: compact is transparent to the hook layer. The agent's working state survives.

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
