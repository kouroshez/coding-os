<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-03 -->
# Agent Hub & Multi-Agent Orchestration

Purpose: Canonical contract for the task-system web UX, multi-agent concurrency stabilization, the session↔transcript id bridge, and the live-agents/traces surfaces. This is the doc-anchor for the `agent-hub` epic (TASK-167+).
Read when: editing `src/core/board_os/`, `src/core/web/routes/`, `src/core/web/ui/src/features/{cos-board,cognition}`, `src/core/hooks/` commit/attribution path, or `src/adapters/claude/sdk_dispatcher.py`.

> Nav: [docs/](../) · [engineering/](./) · related: [hub-architecture.md](hub-architecture.md) · [state-files.md](state-files.md) · [claude-sdk.md](../adapters/claude-sdk.md)

The Hub already does more than it looks. The blockers are NOT missing
features — they are one **structural id-space split** plus three
**concurrency seams** that the agent-and-commit machinery leaves unguarded.
This doc records the finding, the product decisions, and the per-task contract.

## 1. The linchpin — two un-reconciled session id-spaces

```
coding-os session-id  ──names──►  presence.json · trace.jsonl · snapshot.jsonl
  ses-<agent>-YYYYMMDD-HHMMSS-xxxx            ▲
  └─ stored in tasks.agent_session            │ content-only copy, NOT a shared key
                                              │
Claude SDK session uuid  ──names──►  ~/.claude transcript  ◄── chat API (ChatView) keys here
```

`snapshot-transcript.sh` copies the SDK transcript **content** under the
coding-os **filename**, but the chat API (`/api/cognition/chat/{id}`) never
reads the snapshot — it reads `~/.claude` keyed by the SDK uuid. So
`tasks.agent_session` can never reach the chat API: task→chat click-through
404s, and traces cannot be joined to their transcript.

**Decision — the bridge (TASK-184, refined during Plan):** the coding-os↔SDK
id mapping is a **per-session** fact, not a per-task one — so it lives in the
per-session presence record, NOT on the `tasks` table. `agent-presence.sh`
reads the host runtime's `.session_id` (the SDK transcript uuid) from the hook
payload and `presence_write.py` stores it as `sessions/<coding-os-id>.json::sdk_uuid`,
alongside the coding-os id that names the file. A task's `agent_session`
(coding-os id) then resolves to the chat transcript via that record (live), or
via the in-tree transcript snapshot keyed by the same id (TASK-093) for ended
sessions. No schema migration — normalized, lower-risk, and written by the hook
that actually has the uuid (the MCP server, which can't resolve the calling
panel, never sees it). This single bridge unblocks T10, T11, and traces↔chat.

## 2. Product decisions (locked 2026-06-05)

| Decision | Choice |
|---|---|
| Execution | All four phases, autonomous; per-task verify + commit; flow tracked in board + TodoWrite. |
| Session governance | **No concurrency cap.** Root cause of "stuck" is the MCP attribution bug, not session count. Keep the unlimited-sessions design (`per_session_wip`); fix attribution only (TASK-F2). |
| Traces UX | **Human summary as default + raw cognition trace behind a developer toggle.** |
| context-window | Build it, **honestly Claude-only**. Codex renders `N/A` (no runtime usage signal) — never a fabricated number. |
| Adapter scope | Transcript list/read is adapter-loaded. Claude remains the writable chat runtime; Codex is read-only until start/send/cancel move behind the shared runtime port. |

### 2.1 Adapter-loaded transcript contract

`GET /api/cognition/chats` and `GET /api/cognition/chat/{id}` may read from
adapter-owned transcript providers declared as `chat_provider` in
`src/adapters/<agent>/adapter.yaml`. A provider normalizes its native thread
objects into the existing Hub payload and declares whether the transcript is
writable. Core discovers providers from manifests; it must not import an
adapter SDK or parse a provider's private transcript files.

The Codex provider uses the official Python SDK/app-server surface:
`thread/list` for project history and `thread/read(includeTurns=true)` for a
stored transcript. Codex threads are intentionally read-only in Hub until the
mutation operations below share one runtime port. The composer must therefore
be hidden for a Codex transcript instead of sending its id to Claude's resume
endpoint.

Presence is only a link hint, never proof that a transcript exists. A dead
runtime process with no `SessionEnd` transition is stale and must not remain an
active clickable agent. Adapter lifecycle dispatchers must upgrade identity
from the hook payload before writing their final presence transition.

## 3. Concurrency-safety guardrails for the implementing agent

Three other Claude sessions are live (TASK-100, TASK-166, …) and the tree
carries their uncommitted WIP. Therefore:

- **Commit only own files with explicit paths.** Never `git commit -a` / bare `git commit`. Never stage `config_composer.py`, `main.py`, `00-index.md`, `BrainGraph3D.tsx`, or any file this epic did not create/modify.
- **Never touch** `docs/engineering/00-index.md` (a peer session owns it). If the index-regen hook rewrites it, leave it unstaged.
- One logical change → one commit → one `cos task-done`. Re-verify green before close.

## 4. Phase 0 — Concurrency stabilization (highest ROI, no product fork)

| ID | Outcome | Files | Acceptance |
|---|---|---|---|
| **F1** | A task title containing `"` renders valid YAML and stays editable. | `src/core/board_os/mcp_tools.py` `_render_lean_frontmatter` (route title + all string scalars through a YAML-safe quoter). | Create task title `Fix "ready" gate` → `is_lean_format` true → `cos_task_edit` succeeds → board renders. Unit test in `board_os/tests`. |
| **F2** | MCP task ops are attributed to the CALLING panel, killing false WIP blocks/mis-reclaim under concurrent same-agent panels. | `src/core/board_os/_agent_runtime.py` (accept explicit `agent_session`), `mcp_tools.py` (thread it from tool arg), `_shared`/tool signatures. | Two simulated panels create+move tasks concurrently → each task's `task_status_history.agent_session` matches its caller, not last-writer. Test asserts no cross-attribution. |
| **F3** | A hung/orphaned pre-commit child can never stall the next commit. | `src/scripts/_pre_commit_body.sh` (hard `timeout`/alarm wrapper on the batch helper + reap orphaned children on exit). | Inject a sleeping child → pre-commit aborts within timeout with a clear message; next commit succeeds. `make verify-hooks` green. |
| **F4** | Concurrent commits that race `index.lock` retry automatically instead of failing hard. | New thin helper invoked by the commit path (wait+retry ONLY on `Unable to create '.git/index.lock'`, bounded retries, never blind-delete). | Two commits fired same instant → both land (one after a short retry); no lock left behind. |

## 5. Phase 1 — Task UX

| ID | Outcome | Files | Acceptance |
|---|---|---|---|
| **T5** | Task detail opens as a CENTERED modal, not a right drawer. | `CosBoardPage.tsx` (replace `TaskDetailDrawer` geometry with the centered-overlay pattern already used by `CreateTaskModal`). | Click a card → centered modal with backdrop; Esc/overlay-click closes; all sub-panels (body/history/transcript/edit) preserved. |
| **T6** | Provenance distinguishes **initiator** (human/user) from **executor** (agent/session/adapter/model); UI shows created-by + contributors from `cos_task_history`. | `mcp_tools.py` (record initiator on web/agent create), web `board.py` create (pass initiator), `CosBoardPage.tsx` history panel. | A web-created task records initiator=human + executor; an agent-created task records initiator=human-who-triggered + executor=agent session; both visible in the detail modal. |
| **T7** | Clicking a file name in a task shows its git before/after diff. | New read-only endpoint `GET /api/board/task/{id}/diff?sha=&file=` (wraps `git show`/`git diff`), UI popup in the detail modal. | Endpoint returns unified diff (added/removed lines) for a committed file; UI renders it in a popup/tab; path-sandboxed to repo. |
| **T8** | Each commit appends its committed-file list to the active task's Work Log. | New `post-commit` hook (or extend `capture-work-log`) writing `cos_work_log_append` with the commit's file set; registered in `registry.yaml`. | A commit while a task is active appends one Work Log line listing the committed files + sha. Idempotent, fail-open. |

## 6. Phase 2 — Id bridge + chat/session

| ID | Outcome | Files | Acceptance |
|---|---|---|---|
| **T9** | The per-session presence record carries the SDK transcript uuid (the bridge). | `agent-presence.sh` (read `.session_id` from the hook payload), `_helpers/presence_write.py` (store `sdk_uuid`). | `sessions/<coding-os-id>.json` gains `sdk_uuid`, preserved across events, backward-compatible with the 7/8-arg helper; unit tests cover capture + preservation. No schema migration. |
| **T10** | A task card links to the chat session that created it. | `board.py` task-detail (expose the join), `cos-board` UI (link button → cognition chat). | Click "open originating chat" on a task → ChatView opens the correct transcript; gracefully disabled when no uuid. |
| **T11** | A new chat/session can be started from the UI (role/prompt/model → start). | New route `POST /api/cognition/chat` (fresh `sdk.query` without `resume`, capture minted session_id, persist), reuse `sdk_dispatcher` query machinery; `cognition` UI create form. | Form submit → new live session appears in the chat list and streams; new session_id captured. Claude-only; non-Claude adapters show disabled. |
| **T12** | A prompt can launch an agent that researches and writes a TASK autonomously. | New thin runner (fresh headless session, bespoke research+author system prompt, MCP allow-list = `cos_task_create`+`cos_graph_*`+`cos_doc_search`), web trigger in CreateTask flow (agent mode). | "Agent mode" create → headless session researches and calls `cos_task_create`; resulting task is attributed initiator=user, executor=that session. |

## 7. Phase 3 — Live agents + traces

| ID | Outcome | Files | Acceptance |
|---|---|---|---|
| **T13** | One presence classifier (SSOT); the divergent web classifier is retired. | `web/routes/sessions.py` (delegate to `board_os/presence.py` verdict), reconcile vocab/thresholds. | `/api/sessions/active` and `cos_presence_query` agree on state for the same session; test asserts parity. |
| **T14** | One endpoint returns the full live-agent snapshot (model+gate+role+skills+lifecycle); HUD popup is clickable per agent. | New/extended `GET /api/presence/agents` merging presence+roles+lifecycle; `LiveStatus.tsx` clickable per-agent detail. | One call returns all fields per agent; clicking an agent opens its live detail. No field hardcoded. |
| **T15** | Live context-window % per Claude agent; `N/A` for others. | `cognition`/presence join to SDK transcript usage; HUD gauge. | Claude agent shows live token-usage %; Codex shows `N/A` (never a fake number). |
| **T16** | Traces default to a human-readable "what the agent did" summary; raw cognition events behind a dev toggle. | New summary projection over trace events (server `cognition.py` + `TraceTimeline.tsx`), dev toggle. | Normal user sees plain-language steps; toggle reveals raw jsonl. |
| **T17** | The home page surfaces a live-agents section inline (not only the popover). | `HubHome.tsx` mounts a live-agents panel using the T14 endpoint. | Home page shows live agents inline with click-through to detail. |

## 8. Changed/added contracts (track for API-contract-discipline)

- `sessions/<coding-os-id>.json::sdk_uuid` (new presence field, no migration) — the per-session chat join key.
- `GET /api/board/task/{id}/diff` — `{file, sha, diff, added, removed}`.
- `POST /api/cognition/chat` — `{role?, prompt, model?}` → `{session_id}` (fresh session).
- `GET /api/presence/agents` — unified `{agent, session_id, sdk_uuid?, model, gate, role, chain, skills, lifecycle, context_pct?}`.
- Trace summary projection — `{ts, label, role, phase}` (human) vs raw event (dev).
- `GET /api/cognition/roles` — `{roles: [name,…]}` derived from `thinking_os/agents/*.md` (the role producer that `_role_system_prompt` loads); UI pickers consume this instead of a hardcoded literal.

Every consumer of these reads field names from the producer emit site, never from memory.

## 9. Phase 4 — Hardening (post-epic)

| ID | Outcome | Files | Acceptance |
|---|---|---|---|
| **T18** | The chat role picker is data-driven from the role producer, not a hardcoded literal that silently drifts when a role file is added/removed. | New `GET /api/cognition/roles` (lists `thinking_os/agents/*.md`, filtered `^[a-z_]+$`, no `_`-prefixed helpers); `NewChatForm.tsx` consumes it via a `useRoles()` hook. (AgentTaskModal is model-only — no role picker — so it is unaffected.) | Adding/removing a role file changes the picker with no UI edit; the picker reads the producer, not a literal; fixture-backed route test + `tsc` + `ui-build` green. |
