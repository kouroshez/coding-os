<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-04-25 -->
# Workflow Audit — V1 Flowchart vs Current Source

> **Historical snapshot (2026-04-25) — superseded on adapter coverage.**
> The Codex figures below (21/62, Bash-only, Codex.app 0) predate the
> 2026-08-03 parity work; the current SSOT is [adapter-parity.md](adapter-parity.md).

> P: Gap analysis of the original workflow flowchart against the live source as of late April 2026, ranked by remediation priority.
> R: Updating the flowchart, deciding which gaps deserve dedicated tasks.
> S: Day-to-day implementation work — the audit is historical and informational.
> N: [hooks-reference.md](hooks-reference.md), [adapter-parity.md](adapter-parity.md)

> Nav: [Engineering Index](./00-index.md) | [Docs Index](../00-index.md)

**Audited by:** Claude Code (thinking_os full Zoom cycle).
**Baseline:** the original workflow flowchart at `docs/architecture/agent-workflow-flowchart.html` (1195 lines, embedded JSON workflow).
**Current state:** post the bash-heredoc / MCP fast-path / Codex-presence session of 2026-04-25.
**Method:** dimension map → targeted reads → per-persona scenarios → gap rank.

The V1 flowchart is **wrong in three structural ways and silent on six dimensions** that exist in the live codebase. The wrongness is mostly load-bearing: a new agent following V1 will misread enforcement coverage, miss orphan-cleanup, and never see the Hub presence pipeline. Below is what is actually true today, organized by phase, and ranked recommendations.

## 1. Baseline (V1) — what it modeled

Sixteen phases linked by colored edges:

```
n-user → n-sinit → n-gate → n-cynefin → {n-clear | n-complex | n-chaotic}
                                              ↓
                                          n-analyzer ──→ n-router ──→ n-supervisor
                                                                            ↓
                                  ┌─── n-presets ───┬─── n-roles-grid ───┐  │
                                  │  n-situations  │   n-route-dec       │  │
                                  └────────────────┴─────────────────────┘  │
                                                                            ↓
                                                     n-ambi (anti-ambiguity, 7 criteria)
                                                                            ↓
                                                                       n-trace
                                                                            ↓
                                          n-precheck (pre-write hooks)  n-impl (F5)
                                                                            ↓
                                                                       n-postwrite
                                                                            ↓
                                                                       n-verify (F6)
                                                                            ↓
                                                              n-pass {PASS / FAIL_1 / FAIL_2X}
                                                                            ↓
                                                                       n-done → n-end → n-await ↺ n-gate
```

Plus eleven role tiles (F1–F11) with backtrack edges, six situational paths (incident-response, onboarding, scope-change, external-integration, design-review, existing-project-takeover), four retrieval layers, and a static fact sheet (V1 baseline: 39 → 42 MCP tools, 45 hooks, DB v14).

V1 was accurate **for a single-agent / single-subprocess world** as of late April 2026 (≈ 2026-04-19). It has drifted in proportion to everything shipped since.

## 2. Numerical drift since V1

| Metric | V1 | Now (2026-05-09) | Δ |
|---|---|---|---|
| MCP tools | 42 | **79** | +37 (graph + cognition + audit-trail + scrumban tools landed since V1) |
| Hooks on disk (`src/core/hooks/*.sh`) | 45 | **70** | +25 |
| `SessionStart:startup` hooks | 2 | **8** | +6 (including `cleanup-stale-mcp`) |
| `PreToolUse:Write\|Edit` hooks | ~5 | **19** | +14 |
| Hook helper scripts | 0 | **2** Python helpers in `src/core/hooks/_helpers/` | new dir |
| Adapter dispatcher shims | not shown | **11** dispatch scripts in cursor + codex | hidden layer |
| MCP entrypoints | 1 (`cos server-start`) | **2** (`cos-mcp-start` preferred) | new fast-path |

## 3. Per-phase delta

### V1 Phase 1 — Session Init
**V1 says:** hooks `warn-mcp-down`, `session-context-recovery`.
**Reality:** 8 hooks fire on `SessionStart:startup`:
1. `remind-daily` — nudge `cos daily` if stale
2. `ensure-hub-up` — start the Hub on :9188 if down (Scrumban addition)
3. `cleanup-stale-mcp` — kill orphan `src/core/thinking_os/server.py` siblings (added 2026-04-25 this session)
4. `session-context` — renamed from `session-context-recovery`; rotates session-id, clears volatile state
5. `agent-presence` — write presence JSON for Hub UI
6. `warn-mcp-down` — probe MCP liveness
7. `auto-brain-decay` — debounced pattern-decay sweep
8. `warn-graph-empty` — alert if graph_os index empty

The `compact|resume` matcher fires 5 of these (skip ensure-hub-up + cleanup-stale-mcp; resume gets `remind-daily` instead).

**Gap:** V1 doesn't show that `session-context` rotates the session-id and clears `.thinking_os-gate` / `.task-current` / `.zoom-checkpoint` etc. on EVERY startup. Agents resuming work after `compact` keep state; agents on a fresh `startup` lose it.

### V1 Phase 2–4 — Complexity Gate → Cynefin Branch
**V1 says:** record `.thinking_os-gate`, branch CLEAR / COMPLICATED|COMPLEX / CHAOTIC.
**Reality:** Unchanged. `thinking_os-gate.sh` still BLOCKS code writes without the gate file. CHAOTIC branch path is technically there but no automation switches CHAOTIC → quick-stabilize-then-rezoom.

### V1 Phase 5 — Task Analyzer
**V1 says:** `cos_analyze_task` reads prompt + cos_search + cos_graph_impact + cos_doc_search → `TaskSignals`.
**Reality:** Matches. `src/core/thinking_os/task_analyzer.py` produces `TaskSignals` with caching by `task_marker`. Handles partial source failures via `source_errors`.

### V1 Phase 6 — Role Router
**V1 says:** preset-lookup → composer-fallback → situational-override.
**Reality:** Matches. `src/core/thinking_os/presets/registry.yaml` and `situations/registry.yaml` both ship with their entries. Order in code: `situation_override > preset_match > composer_fallback > hard_fallback` (same as V1 fact sheet).

### V1 Phase 7 — Supervisor Loop
**V1 says:** states `IDLE → CLASSIFYING → ROUTING → DISPATCHING → AWAITING_AGENT → INTEGRATING → DONE`, with backtracks tracked as transitions not states.
**Reality:** Implemented in `src/core/thinking_os/cognition.py` against a pydantic `SupervisorState` from `cognition_schemas.py`. Matches V1.

### V1 Phase 8 — Anti-Ambiguity
**V1 says:** 7 criteria (observable, measurable, testable, scoped, owned, reversible, user-value), blocking.
**Reality:** Hook is `enforce-anti-ambiguity.sh`, registered at `PreToolUse:Write|Edit`. Still blocking. Matches.

### V1 Phase 9 — Traceability
**V1 says:** triggers on phase-boundary and session-end.
**Reality:** `cos_traceability` MCP tool exists. Trace files at `.coding-os/<agent>/traces/<session_id>.jsonl` written by `src/core/thinking_os/tracing.py`. Trace replay at `docs/cognition-trace-replay.html`. Matches.

### V1 Phase 10 — Implement (F5)
**V1 says:** pre-hooks `enforce-doc-anchor`, `enforce-skill`, `enforce-task-start`, `enforce-template`, `enforce-rename-plan`, `block-*`.
**Reality:** All five enforce-* still ship. Pre-hook count is now 19 on `Write|Edit` (V1 mentions ~6). Newly added since V1:
- `enforce-zoom` (Plan checkpoint for COMPLICATED+)
- `enforce-graph-context` (graph-context marker for load-bearing files)
- `enforce-memory-check` (cos_search recorded)
- `enforce-anti-ambiguity` (the 7 criteria gate, was a phase node in V1 but is now a hook — V1 split it logically)
- `enforce-task-body` (DoR/DoD transition gates)
- `enforce-wip-limit` (Scrumban WIP cap)
- `validate-task-frontmatter` (lean task format)
- `block-bad-patterns` (now also catches the bash 5.3.9 heredoc — added this session)
- `block-protected-files`, `block-migration-conflict`, `block-hardcoded-literals`
- `warn-template-drift`

### V1 Phase 11–14 — Verify → Pass → Done → Session End
**V1 says:** `n-verify` (F6, parallelizable), pass/fail decision, `make task-done`, `n-end` does summary + discovery-promote + bundle-ttl-cleanup.
**Reality:** Matches. `cos task-done` is the Scrumban form (`make task-done` is legacy). `session-end.sh` still writes summary + cleans bundles.

## 4. Dimensions V1 didn't model at all

V1 was drawn before these existed; today's agent will not find them on the chart.

### 4.1 MCP entry strategy
- `.mcp.json` now points at **`cos-mcp-start`**, not `cos server-start`. Both work, fast-path is preferred.
- Both run an **orphan sweep at boot** (`_sweep_stale_servers`) — kills stale `server.py` siblings whose parent is dead OR etime > `COS_STALE_SERVER_AGE_S` (12 h).
- Without sweep, Codex/Cursor pool MCP children that never close → SQLite WAL contention → auxiliary subprocess timeouts.
- Reference: [docs/engineering/mcp-fast-path-entry.md](mcp-fast-path-entry.md).

### 4.2 Hook helper layer (`src/core/hooks/_helpers/`)
- New convention: hot-path Python that used to live inside `python3 - <<HEREDOC` is now in `_helpers/<name>.py`, invoked as a normal subprocess.
- Required because Homebrew bash 5.3.9 sporadically deadlocks `cmd - <<HEREDOC` in `heredoc_write` before fork — high-frequency hooks (agent-presence) accumulated zombies.
- Symlink-aware path resolution (readlink-walk at top of `agent-presence.sh`) finds `_helpers/` from the symlinked install dir.
- Reference: [docs/engineering/bash-heredoc-deadlock.md](bash-heredoc-deadlock.md).

### 4.3 Adapter dispatcher shims
- Cursor and Codex install scripts that REGISTER a single dispatcher per event, e.g. `codex-sessionstart-dispatch.sh` and `cursor-sessionstart-dispatch.sh`. Those dispatchers internally `for delegate in <list>; do bash "$delegate"; done` over a **hardcoded list** of core hook scripts.
- V1 shows hooks firing directly. Reality: Cursor and Codex hide behind a shim that fans out.
- **Drift hazard:** adding a hook to `registry.yaml` is NOT enough for Cursor/Codex — you must also append the script name to the dispatcher's hardcoded list.

### 4.4 Hub UI presence + agent_states
- The Hub at :9188 reads `.coding-os/<agent>/sessions/*.json` (written by `agent-presence.sh`) and computes `{active, present, offline}` per agent. Returned via `/api/board/list` → `data.agent_states`.
- Three-state ladder: tool/prompt within 30 s → ACTIVE; PID alive + heartbeat within 1 h → PRESENT; otherwise OFFLINE.
- This is the live-agents panel in the Hub, NOT the cognition trace replay. V1 only mentions the latter.

### 4.5 Subprocess #2 risk + auxiliary spawns
- Anthropic VSCode extension spawns auxiliary Claude subprocesses for session-title generation and config-cache loading. Each repeats the FULL MCP boot.
- Under contention (multiple agents on same project, recovering DB locks, slow MCPs), aux init blows the 60 s extension timeout → "Subprocess initialization did not complete within 60000ms" → first message hangs.
- Mitigations now in place: orphan sweep, `cos-mcp-start` fast-path, no-zombie hooks. Without all three, the failure recurs.

### 4.6 Codex.app GUI hook gap
- `codex-cli` 0.124 / 0.125 GUI (Codex.app + Antigravity extension's `codex app-server`) **silently ignores `.codex/hooks.json`**. Only the deprecated `notify=[...]` field is consulted, logged as `hook_name=legacy_notify`.
- Hub presence falls back to scanning `~/.codex/sessions/**/rollout-*.jsonl` for files whose first-line `cwd` matches the project (`_codex_rollout_recent_for` in `src/core/web/routes/board.py`).
- See **§5 Persona 2** below for the security implication.
- Reference: [docs/engineering/codex-presence-fallback.md](codex-presence-fallback.md).

### 4.7 Bash 5.3.9 deadlock incident
- Already covered in §4.2. Worth flagging as its own dimension because the discipline (no `python3 - <<HEREDOC`) is now enforced in `block-bad-patterns.sh` and applies to every future hook author.

### 4.8 Adapter capability filtering
- `src/adapters/<agent>/adapter.yaml::hook_capabilities` declares which `{event, matcher}` pairs each runtime can actually fire. The renderer skips registry entries whose pair is missing.
- Today's coverage:
  - **Claude:** 58 of 62 hook-events fire (full)
  - **Cursor:** 59 of 62 hook-events fire
  - **Codex (CLI):** 21 of 62 hook-events fire — Bash matcher only on PreToolUse/PostToolUse, no `Write|Edit` or `Skill` matchers
  - **Codex.app (GUI):** **0** fire (upstream bug — even the 21 configured ones are dropped)
- This means Codex CLI users do NOT get the 19 `PreToolUse:Write|Edit` enforcers (block-bad-patterns, enforce-template, enforce-task-start, enforce-doc-anchor, enforce-skill, etc.). They get the Bash safeties only.

## 5. Per-persona reality

### Persona 1 — Claude Code in VSCode (primary user, this chat)
| Aspect | Status |
|---|---|
| Hooks fire | ✅ 58/62 events |
| Block class enforces | ✅ all 21 BLOCK/ENFORCE hooks active |
| MCP boot | ✅ via `cos-mcp-start`, ~430 ms |
| Auxiliary subprocess survives | ✅ orphan sweep + no-zombie hooks |
| Hub presence | ✅ fed by `agent-presence.sh` |
| Sub-agent dispatch (F1–F11) | ✅ via `claude-agent-sdk>=0.1.68` with `setting_sources`, `mcp_servers`, `model`, `effort`, `thinking`, `max_budget_usd` |

No P0/P1 gaps for this persona.

### Persona 2 — Codex.app GUI (Antigravity extension)
| Aspect | Status |
|---|---|
| `.codex/hooks.json` lifecycle hooks | ❌ **never fire** (only `legacy_notify`) |
| BLOCK class enforcement | ❌ **none** — `block-secrets`, `block-bad-patterns`, `enforce-doc-anchor`, etc. all silent |
| Workflow gates (thinking_os, anti-ambiguity, doc-anchor) | ❌ silent |
| MCP boot | ✅ via `cos-mcp-start`, same fast path |
| Hub presence | ✅ via rollout-file fallback |
| Sub-agent dispatch | n/a (Codex doesn't use the SDK dispatcher) |

**This is the biggest gap in the system.** A user opening Codex.app on coding-os has none of the workflow enforcement that V1 promises. The hook configuration files exist (`.codex/hooks.json` is regenerated by `make sync`), but Codex.app reads only `notify=[...]` from `~/.codex/config.toml`. Until upstream fixes this, **work that requires gate enforcement should not be done in Codex.app**.

### Persona 3 — Codex CLI (`codex exec` non-interactive)
| Aspect | Status |
|---|---|
| Hooks fire | ✅ 21/62 events (capability bound) |
| BLOCK class enforcement | ⚠️ partial — Bash hooks only; Write/Edit BLOCK hooks **don't run** |
| Hub presence | ✅ via agent-presence on tool calls |
| Sub-agent dispatch | n/a |

Codex CLI is a fine path for batch tasks. Not a fine path for code-editing tasks where `block-bad-patterns` etc. are load-bearing.

### Persona 4 — Cursor IDE (Agent mode)
| Aspect | Status |
|---|---|
| Hooks fire | ✅ 59/62 events |
| BLOCK class enforcement | ✅ via dispatcher fan-out |
| Hub presence | ✅ via agent-presence on tool calls |
| Sub-agent dispatch | n/a (Cursor doesn't use the SDK dispatcher) |
| **Drift hazard** | ⚠️ adding a hook to registry.yaml requires also editing `cursor-*-dispatch.sh` hardcoded delegate lists |

### Persona 5 — Human (running `cos` directly)
| Aspect | Status |
|---|---|
| Hooks fire | ❌ no agent runtime → no PreToolUse / Write|Edit hooks |
| BLOCK class enforcement | ❌ none (manual edits bypass everything) |
| Workflow gates | ❌ none |
| Hub presence | ✅ shown as `human` (special pseudo-agent in `agent_manifest`) |

**V1 doesn't acknowledge this persona at all.** A human editing `docs/tasks/TASK-NNN.md` directly bypasses `validate-task-frontmatter`, `enforce-wip-limit`, `lint-task`. A human editing `src/core/hooks/<x>.sh` bypasses `block-bad-patterns`. The Hub doesn't know to flag manual edits.

### Persona 6 — Sub-agent (F-formula spawned via SDK)
| Aspect | Status |
|---|---|
| Spawned via | `claude-agent-sdk.query()` (Claude parent) OR `codex_app_server.AsyncCodex` / `codex exec` subprocess (Codex parent) |
| MCP server | NEW `cos-mcp-start` per dispatch (recursive) |
| Hooks fire | ✅ Claude: inherits via `setting_sources=["project"]` · Codex: inherits via `.codex/hooks.json` (CLI fires correctly even when GUI doesn't) |
| Cost cap | ✅ Claude: `max_budget_usd` per formula frontmatter · Codex: per-formula `model` honored, no native budget cap (use `--config token_limit`) |
| Risk | ⚠️ recursive MCP boots stack — F1→F2→F3 chain = 3 extra `cos-mcp-start` invocations |
| Symmetry rule | Rule 22 — both `src/adapters/claude/sdk_dispatcher.py` and `src/adapters/codex/sdk_dispatcher.py` ship; the factory loads whichever matches `COS_AGENT`. Cursor has no programmatic SDK upstream → falls back to the `default` DB-only dispatcher. |

## 6. Critical gaps (ranked by harm × likelihood)

### P0 — Codex.app silent enforcement gap (Persona 2)
**Symptom:** every BLOCK / ENFORCE hook is invisible to Codex.app users. Secret leaks in commits, bad patterns in code, missing doc anchors, missing thinking_os gates — all uncaught.
**Cause:** upstream codex-cli 0.124/0.125 GUI doesn't honor `.codex/hooks.json`.
**Mitigation options:**
- A. **Project banner / AGENTS.md warning:** explicit "Codex.app skips enforcement" line so users know to switch runtimes for protected work. Cheapest, no code.
- B. **Sidecar daemon:** poll `~/.codex/log/codex-tui.log` and run equivalent hooks externally on detected events. Heavy, fragile, partial coverage (no PreToolUse blocking).
- C. **Wait for upstream fix:** open issue with OpenAI, monitor codex releases.
**Recommendation:** A immediately, C tracked as a follow-up task in the Scrumban board.

### P1 — Cursor/Codex dispatcher delegate-list drift  *(SHIPPED)*
**Symptom:** new hooks added to `registry.yaml` don't reach Cursor/Codex unless someone remembers to also append the script name in `cursor-sessionstart-dispatch.sh` / `codex-sessionstart-dispatch.sh`. We hit this in this session with `cleanup-stale-mcp.sh`.
**Status:** Closed. `src/scripts/verify_dispatchers.py` (matcher-aware, hybrid-aware drift detector) added and wired into `make verify-dispatchers` + `make verify`. Initial run revealed 8 missing hooks across the cursor/codex SessionStart + Write|Edit dispatchers; all added, plus 4 double-coverage entries removed (capture-observation, capture-work-log, track-discovery, enforce-rename-plan were registered both inline AND in the dispatcher → fired twice per Edit). All 10 (adapter, event, matcher) cells now report aligned. The user's preference is to keep dispatcher delegate lists hardcoded (not auto-generated), so the detector is the long-term guard.

### P2 — V1 flowchart is structurally outdated
**Symptom:** new agents reading `docs/agent-workflow-flowchart-V1.html` get a wrong mental model — wrong hook counts, missing MCP entry, missing Hub UI, missing per-persona reality.
**Mitigation options:**
- A. **Regenerate as V2** from `registry.yaml` + `roles/` + `situations/` + `presets/` (script: `src/cli/render_workflow.py`). Living diagram.
- B. **Mark V1 deprecated** with a banner pointing at this audit + the per-domain engineering docs.
- C. **Delete V1**; `cos cognition trace` + Hub UI become canonical.
**Recommendation:** B now (one-line edit), A as an audit-trail follow-up task.

### P3 — Human persona uncodified
**Symptom:** a human editing repo files bypasses every workflow gate. Drift accumulates silently.
**Mitigation options:**
- A. **Document explicitly in AGENTS.md:** humans editing protected files manually are responsible for running `cos task-validate` / `make verify` / etc. before committing.
- B. **Pre-commit hook (git):** install a git hook that runs `block-bad-patterns.sh` and `validate-task-frontmatter.sh` against staged changes. Catches manual edits at commit time.
- C. **fsevents watcher:** run via `cos hub` daemon, fire hooks on filesystem changes. Heavy and noisy.
**Recommendation:** A immediately, B as a Scrumban follow-up task.

### P4 — Sub-agent recursive MCP boots
**Symptom:** F1→F2→F3 chain means 3 extra `cos-mcp-start` invocations (sub-agent of sub-agent of parent). Each takes ~430 ms cold and adds an SQLite WAL connection. Not a current pain point but a scaling cliff.
**Mitigation options:**
- A. **Profile** real chain costs first; defer.
- B. **In-process subagent** via `claude-agent-sdk`'s `agents=AgentDefinition(...)` instead of `query()` subprocess. Sub-agent runs in parent's process, no extra MCP boot.
**Recommendation:** A this quarter (data-driven), B if profiling shows ≥ 2× boot overhead.

### P5 — Discoverability of incidents + workarounds
**Symptom:** the bash 5.3.9 deadlock, Codex hook gap, MCP fast-path are documented but in three separate engineering docs. No index. Future agent investigating "why does X behave Y" has to know to grep.
**Mitigation:** create `docs/engineering/incident-log.md` — one paragraph per incident, link to deep-dive. Add a row per incident in `changes.log`.
**Recommendation:** ship with this audit (already partially done in `changes.log`).

## 7. Revised mental model (per phase, per persona)

If you remember nothing else from this audit:

```
                   Claude     Codex.app     Codex CLI    Cursor    Human
SessionStart hooks   ✅           ❌            ✅           ✅        ❌
PreToolUse:Bash      ✅           ❌            ✅           ✅        ❌
PreToolUse:W|E       ✅           ❌            ❌(no cap)   ✅        ❌
BLOCK enforcement    ✅           ❌            ⚠️ partial   ✅        ❌
Hub presence ACTIVE  ✅           rollout       ✅           ✅        ✅(human)
MCP fast-path        ✅           ✅            ✅           ✅        n/a
Sub-agent SDK        ✅           n/a           n/a          n/a       n/a
```

`✅` = workflow as designed. `❌` = silent gap. `⚠️` = partial.

## 8. Read-this-list for new agents

- [AGENTS.md](../../AGENTS.md) — rules 0–21, the Critical Rules block
- [hooks-reference.md](hooks-reference.md) — what every hook does
- [mcp-fast-path-entry.md](mcp-fast-path-entry.md) — why two MCP entries
- [bash-heredoc-deadlock.md](bash-heredoc-deadlock.md) — the deadlock + safe forms
- [codex-presence-fallback.md](codex-presence-fallback.md) — Codex GUI gap
- This audit — for the per-phase / per-persona picture
- `src/core/hooks/registry.yaml` — SSOT for hook registration

V1 flowchart is **historical**, not current.
