<!-- domain:DOCS | layer:policy | ssot:true | updated:2026-05-08 -->
# Task Lifecycle Policy

> P: Canonical lifecycle for creating, executing, and closing tasks under the Scrumban model (`src/core/board_os/`).
> R: Creating a task, transitioning status, or aligning task scripts and templates.
> S: Reading existing task content unrelated to lifecycle change.
> N: [docs-system.md](docs-system.md), [agent-workflow.md](agent-workflow.md), [_templates/task-detail.md](_templates/task-detail.md)

> Nav: [Governance Index](./00-index.md) | [Docs Index](../00-index.md)

## SSOT and Mirrors

- `docs/tasks/TASK-###-slug.md` — **canonical detail file**. One per active or completed task. File frontmatter and body are the source of truth.
- the `tasks` table in `.coding-os/coding-os.db` (schema: `src/core/thinking_os/database.py` migrations) — **derived mirror**. Mtime-incremental sync from the detail files; never edited by hand.
- `cos board` / `cos board --web` — **live view** rendered from the DB.

There is no flat `docs/tasks.md` index. Status is read from frontmatter, not from a top-level checkbox file.

### Board↔git coherence

Because the detail files are the durable, version-controlled truth and the DB is **gitignored** (`.coding-os/`), a DB task row whose `.md` is uncommitted — untracked or modified — is **drift**: the board knows about work a fresh clone would not. `src/core/board_os/git_coherence.py` (`detect_board_git_drift`) is the single detector behind three surfaces:

- `cos doctor` — the on-demand `board.git_tracked` WARN check.
- the nightly `board_coherence` maintenance task — files **one** idempotent `auto-git-drift` board task while drift persists, so no-hook personas see it without invoking the doctor.
- the CI gate — fails on drift in the checked-out tree.

Materialization churn (status transitions, work-log appends, `committed <sha>` commit links) re-writes `.md` files as a side-effect; this is **expected** and is deliberately excluded from the per-turn uncommitted-work nag (`session-end.sh`). It is reconciled in batches, not auto-committed per operation.

**Auto-commit (autonomy-gated).** When the project's git autonomy permits unattended writes (`COS_GIT_AUTONOMY ∈ {local_autonomous, autonomous}`), the nightly `board_coherence` task commits the drift itself — staging **only** `docs/tasks/*.md` in one idempotent `chore(board): …` commit. The tasks-only scope is load-bearing: `_post_commit_body.sh` appends a `committed <sha>` work-log line only when a commit also carries non-task files, so a tasks-only commit no-ops that hook and the tree converges clean in a single pass. When autonomy does not permit it, the task only *files* the drift task and leaves the commit to a human or agent.

## Status States

`icebox → in_progress → testing → complete`, plus `blocked` reachable from any state (and `emergency` / `archive` for the incident and retirement lanes).

Transitions go through `cos task-*` (or the equivalent MCP tool). The CLI writes the detail-file frontmatter and the DB row atomically; manual edits to one side without the other create drift that the doctor will flag.

## Required Artifacts

For any task that is `in_progress`, `testing`, `blocked`, or `complete`:

- A primary detail file at `docs/tasks/TASK-###-slug.md` authored from `src/templates/task-detail.md`.
- A non-empty Work Log section once execution starts (transition gates check this).
- An Outcome line at the top, plus Read First, Acceptance (Given/When/Then), and Rollback sections.
- Optional companion reference docs only when the primary file would exceed the size cap (warn ≥1.5 k tokens, block ≥3 k — Rule 14).

Backlog entries that are not yet started may live in `cos board` (icebox status) without a detail file. Detail file becomes required at the moment of first transition out of icebox.

## Execution Rules

- **Pull from icebox requires the `ready` label.** With `workflow_policy.require_ready_label` (default on), `icebox → in_progress` is blocked until the task is marked pullable — `cos task-ready TASK-NNN` (or create with `--ready`). The `emergency` fast lane is exempt. This separates "groomed idea" from "raw idea": the content DoR gate proves the task is well-formed, the `ready` label proves it was deliberately scheduled. Marking ready also *surfaces* that DoR check at authoring time — `cos_task_ready` reuses the same validator the `icebox → in_progress` gate uses: by default it warns and still sets the label, returning any gaps under `data.dor`; with `COS_READY_DOR=strict` it refuses the label until the DoR is met (override: `COS_DOR_OVERRIDE=1` + a ≥15-char `COS_OVERRIDE_REASON`), so a task can no longer be silently labeled ready while incomplete.
- **Dependency-aware readiness.** `depends_on` is load-bearing, not documentation. With `workflow_policy.require_deps_complete` (default on), `icebox → in_progress` is blocked while any task in `depends_on` is not yet `complete` — finish the prerequisites or override with `force=True` (`cos task-move --force`). The error is **retryable** (category `transient` — the MCP envelope's retryable-by-default class): re-issue the pull once the upstream tasks complete and it succeeds with no edit. The `emergency` fast lane (`emergency → in_progress`) is exempt, so a fire never waits on a backlog item. `cos_task_pick` mirrors this — a `ready` icebox card with any incomplete dependency is omitted from candidates, so the picker only ever surfaces work that is runnable *now*.
- **Completion cascade.** When a task transitions to `complete`, every dependent it unblocks is reconsidered automatically (`cos_task_move` returns the result under `data.cascade`). A dependent whose dependencies are now *all* complete **and** whose body passes the Definition-of-Ready check is auto-labeled `ready` (moving `blocked → icebox` first if needed) and listed under `cascade.readied`. A dependent that is unblocked but DoR-incomplete is surfaced under `cascade.needs_authoring` (not silently hidden — author it, then it's pullable). A dependent still waiting on another open dependency — or on one that was `archive`d/cancelled (terminal-failed) — is left where it is under `cascade.still_blocked` with a reason, so it never hangs invisibly. The cascade is fire-and-forget: it can never turn a successful completion into a failure.
- **Atomic claim-next (`cos_task_claim_next`).** For safe autonomous multi-agent runs, this tool selects *and* claims the highest-priority runnable-now task in one atomic step — reusing `cos_task_pick`'s dependency-filtered, priority-ordered candidate list, then an atomic `→ in_progress` move under the same `BEGIN IMMEDIATE` + compare-and-set the regular transition uses. N sessions racing on the same runnable set each receive a **distinct** task (`data.claimed` = the claimed card) or `data.claimed = null` — no two sessions ever claim the same task, a loser whose compare-and-set missed walks to the next candidate, and a session already at its per-session WIP cap stops and returns `null`. It never raises and never stalls.
- **Concurrent sessions don't block each other.** With `workflow_policy.per_session_wip` (default on), the `in_progress` cap is counted per `agent_session` — each session keeps its own focus limit of 1 while two Claude tabs or a Claude + Codex pair run in parallel. `testing` / `emergency` caps stay board-global. An `in_progress` task whose owning session goes inactive and is idle past `reclaim_idle_hours` (default 24h) is returned to `icebox` + `ready` by `cos task-reclaim` (also run opportunistically by `cos daily`), so a crashed session never strands work.
- Move the task to `in_progress` before any substantial Write/Edit. Hooks block code edits without an active task marker.
- Complexity Gate (AGENTS.md § Core Loop) runs in Classify before Orient. The gate's Dimension Map and Read List inform the rest of the loop and are recorded in the task's Notes when non-trivial.
- Keep Work Log up to date as you go — one bullet per meaningful checkpoint. The CLI's `cos work-log TASK-NNN "note"` is preferred so the DB cache (`work_log_last_5`) stays fresh.
- Use `Given / When / Then` for Acceptance criteria.
- Move to `complete` only after Verification Matrix tests for the changed surface pass. Untested error paths fail the gate.
- **A missing task file fails the DoD gate CLOSED.** When `to_status == complete` and the task's `.md` is absent on disk, the transition is BLOCKED (`task file not found — cannot verify DoD`) instead of silently skipping the verify-freshness / work-log / Read-First checks. A complete-transition must never be cheaper than one with a present file, so a DB row with no file can no longer close unverified (TASK-532).
- **Acceptance completeness is re-checked at `complete`, graduated by kind.** The DoD gate (`evaluate_dod`) re-reads the task body so the close is never cheaper than the pull: a kind whose DoR *requires* a Given/When/Then Acceptance (feature / bug / refactor / test / security) is BLOCKed with `DOD_ACCEPTANCE_MISSING` when that section is absent or malformed at `complete`; kinds that opt out of Acceptance in DoR (docs / chore / spike) only WARN. This closes the DoR-rich / DoD-shallow asymmetry — a task can no longer reach `complete` with the acceptance criteria that *are* its definition-of-done stripped, or after entering via a path that skipped DoR (emergency lane, force). The severity is derived from the same DoR config that decides whether the kind needs Acceptance, so there is no separate kind list to drift; disable per kind with `definition_of_done.<kind>.require_acceptance_met: false`.
- **Direct `in_progress → complete` is blocked by default.** With `workflow_policy.block_in_progress_to_complete` (default on), the shortcut is rejected — route `in_progress → testing → complete` so the Verification Matrix runs. The state-machine edge stays legal (`force=True` / `cos task-move --force` overrides for genuine trivial work, and is audited). When the policy knob is off, `workflow.transition` falls back to the legacy soft warning instead of blocking.
- **Aging blockers surface, never auto-escalate.** A card dwelling in `blocked` past `workflow_policy.blocked_sla_hours` (default 72h ≈ the "Day 3: surface" escalation rung) is flagged `stale` on `cos board` / `cos daily` with a blocked-specific reason — an **observability signal only**, so a stuck blocker becomes visible without ever being silently moved to the `emergency` lane. Set `0` to disable the flag.
- Search the repo and the graph before creating any new file, pattern, or rule. Reuse beats reinvention.

## Primary Task File Contract

Required sections in this order (template lives at `src/templates/task-detail.md`):

- `## Outcome` — single sentence describing the externally visible result.
- `## Read First` — annotated list of files and refs the executor should load before editing.
- `## Acceptance` — numbered list, Given/When/Then format.
- `## Work Log` — append-only bullets, newest at the bottom. On a body edit, `cos_task_edit` swaps in the **fresh on-disk Work Log** in place, so a concurrent `cos_work_log_append` that lands between the editor's fetch and its save is never overwritten (the drawer's body is a snapshot).
- `## Rollback` — one-paragraph plan for backing the change out.

Optional sections:

- `## Notes` — working notes, findings, dimension maps for COMPLICATED+ tasks.
- `## Dependencies` — only when the task is gated by other tasks; mirrored in the `depends_on` frontmatter.

## Frontmatter Fields

| Field | Required | Notes |
|---|---|---|
| `id` | yes | matches the file name slug |
| `title` | yes | one line, no trailing punctuation |
| `swimlane` | yes | agent-defined; common: `infra`, `frontend`, `docs`, `research` |
| `kind` | yes | one of `feature · bug · chore · spike · docs · refactor · test · security` |
| `status` | yes | `icebox · in_progress · testing · blocked · complete · emergency · archive` |
| `priority` | yes | `P0 · P1 · P2 · P3` |
| `appetite` | yes | shape-up budget, e.g. `30m · 2h · 1d · 2w` |
| `epic`, `labels` | no | grouping helpers |
| `depends_on`, `blocked_by` | no | task IDs |
| `references` | no | doc paths the task points at |
| `external_ref` | no | optional forge issue/PR link (e.g. `github#42`), set via `cos task-link TASK-NNN <issue>`; forge auto-detected from `git remote`, metadata only — never the canonical id ([adr-task-id-allocator-seam.md](adr-task-id-allocator-seam.md)) |
| `created`, `started`, `completed` | auto | written by the CLI on transitions |
| `agent_session` | auto | fingerprint of the agent that started the task |

## Task ID Scheme

The `id` is allocated by [`_next_task_id`](../../src/core/board_os/mcp_tools.py). Two schemes, set in `.coding-os/scrumban-config.yaml`:

| `task_id_scheme` | Format | Use |
|---|---|---|
| `sequential` (default) | `TASK-NNN` | Single-owner projects — readable, sortable, zero config. |
| `namespaced` | `TASK-<NS>-NNN` | Multi-contributor projects — a per-contributor `NS` keeps each person's counter independent, so two un-synced contributors never compute the same id (the OSS fork/PR collision). |

Under `namespaced`, `NS` comes from `task_id_prefix` (2–8 chars, uppercase, letter-first — e.g. `KO`) when set; otherwise it is derived stably from `git config user.email`. The counter is `max(ids with this NS) + 1`, so `KO-…` and `JD-…` sequences never cross. Every task-id-aware site (parser, frontmatter validation, `.task-current`, commit-linking, `git log --grep`) matches both `TASK-NNN` and `TASK-<NS>-NNN` via one backward-compatible regex, so a project can switch schemes without breaking existing ids. Rationale + the options considered (incl. a future GitHub-issue allocator): [adr-task-id-collision-resistance.md](adr-task-id-collision-resistance.md).

## CLI and MCP Surface

| Action | CLI | MCP |
|---|---|---|
| View board | `cos board` / `cos board --web` | `cos_task_board` |
| Create | `cos task-create --title "…" --swimlane … --kind …` | `cos_task_create` |
| Mark ready | `cos task-ready TASK-NNN` | `cos_task_ready` |
| Start | `cos task-start TASK-NNN` | `cos_task_move` → `in_progress` |
| Reclaim zombies | `cos task-reclaim` | `cos_task_reclaim` |
| Move to testing | `cos task-move TASK-NNN --to testing` | `cos_task_move` → `testing` |
| Complete | `cos task-done TASK-NNN` | `cos_task_move` → `complete` |
| Block | `cos task-move TASK-NNN --to blocked` | `cos_task_move` → `blocked` |
| Append work log | `cos work-log TASK-NNN "note"` | `cos_work_log_append` |
| Daily standup | `cos daily` | `cos_task_daily` |
| WIP check | `cos wip` | `cos_task_wip_check` |
| Pick next | `cos task-pick` | `cos_task_pick` |

## The `make task-*` wrappers

`cos task-*` is the canonical task interface. `src/templates/_base/Makefile.base` keeps a few `make task-*` targets purely as muscle-memory wrappers — each shells straight out to `cos`:

| Wrapper | Delegates to |
|---|---|
| `make task-start TASK=098` | `cos task-start TASK-098` |
| `make task-done TASK=098` | `cos task-done TASK-098` |
| `make task-block TASK=098 REASON="…"` | `cos task-block TASK-098 --reason "…"` |
| `make task-create` | prints the `cos task-create` usage (it needs `--swimlane` / `--kind`) |

The legacy file-based task system — the `task-*.sh` scripts and the flat `docs/tasks.md` index — has been removed. `make task-*` provides nothing that `cos task-*` does not; new code and docs should always call `cos task-*` directly.

## Script Output Convention

| Prefix | Meaning | Stream |
|---|---|---|
| `OK:` | success | stdout |
| `ERROR:` | fatal | stderr, exit 1 |
| `WARN:` | non-fatal | stderr |
| `INFO:` | progress / context | stdout |

## Outcome Tracking

After every transition into `complete` or `blocked`, the workflow records an outcome row to `coding-os.db` for the Learning Loop:

| Field | Values | Source |
|---|---|---|
| outcome | `success · rework · partial · blocked` | agent assessment |
| duration_min | integer | session elapsed time |
| model | active model id | dispatcher |
| skills_used | JSON array | skill enforcement hook |

Outcomes feed pattern extraction every N completions. See [agent-workflow.md](agent-workflow.md) § Memory & Learning.
