<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-06-14 -->

# ADR-0006: External task-tracker seam — the interface an outside tracker must satisfy

- **Status:** Accepted (2026-06-14, TASK-391) — contract only, no implementation
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** board_os, task-system, modularity, linear-ready

## Context

board_os ships a native, file-first Scrumban board ([ADR-0005](0005-board-os-file-first-scrumban.md)).
Some teams already run an external tracker (Linear, Jira, GitHub/GitLab issues)
and will want coding-os to drive *that* board instead of the native one. The
trap to avoid is hard-wiring a SaaS tracker into the kernel — that host-locks a
host-agnostic meta-project, forces every consumer onto one forge, and couples
the cognitive layer to a network dependency on the task hot path.

The seam already exists in the code; this ADR only *names the contract* so a
future adapter can drop in with zero kernel change. Two facts make it possible:

1. **The `tasks` subsystem is already modular.** `src/core/subsystems.yaml`
   declares it as a non-kernel module — `id: tasks`, `depends_on: [docs]`,
   `tools: ["cos_task_*", cos_work_log_append]`. It can be disabled per project.
2. **Disabling a module degrades gracefully, it does not vanish.** When `tasks`
   is off, `_gated_module` in `src/core/thinking_os/tools/_shared.py` makes every
   `cos_task_*` / `cos_work_log_append` call return the typed envelope
   `fail("module_disabled", …)` rather than disappearing — a stable, machine-
   readable signal an adapter can detect and take over.

## Decision

**An external task tracker plugs in as an adapter behind the existing
`cos_task_*` tool surface — it is never the canonical id source, and it never
makes board_os DB-first.** The contract has three parts.

### 1. The minimum adapter interface (against the real `cos_task_*` surface)

An external-tracker adapter MUST satisfy these five operations, each mapping to
the tool it stands in for in `src/core/board_os/mcp_tools.py`:

| Capability | Native tool it replaces | Minimum semantics |
|---|---|---|
| create | `cos_task_create` | create a tracked item; return a `TASK-<token>` id |
| move | `cos_task_move` | transition status across the Scrumban state machine |
| show | `cos_task_show` | fetch one item's frontmatter + body |
| board-list | `cos_task_board` | list items grouped by (swimlane, status) |
| append-work-log | `cos_work_log_append` | append one progress line to an item |

The adapter returns the **same `ok(data)` / `fail(category, message)` envelope**
every `cos_*` tool returns (`docs/engineering/mcp-error-envelope.md`); callers
(hooks, Hub UI, CLI) are unaffected because the surface is unchanged.

### 2. Linkage reuses `external_ref` — the forge link, never the id

A task that mirrors an external item carries the existing `external_ref`
frontmatter field from [adr-task-id-allocator-seam.md](../../governance/adr-task-id-allocator-seam.md)
(`<forge>#<n>`, e.g. `linear#ENG-42`, set via `cos task-link`). The canonical id
stays the offline `TASK-<token>`; the external item is an *optional bidirectional
link*, not the primary key. No parallel id scheme is invented here.

### 3. The off-switch is the seam

A project that wants its external tracker to own tasks disables the native
module (`cos module disable tasks`). From then on the native board is gone — the
`cos_task_*` tools answer `module_disabled` until an adapter is registered. The
adapter, once present, answers those same tool names against the external API.

## Consequences

**Positive:**

- A Linear/Jira/GitHub adapter is *additive*: implement the five operations
  behind the `cos_task_*` names, register it, disable the native module — no
  kernel edit, no caller change, no id rewrite.
- `external_ref` already gives issue ↔ task ↔ PR navigation without coupling the
  kernel to any forge.
- Offline-first stays the default; an external tracker is strictly opt-in.

**Reconciliation with [ADR-0005](0005-board-os-file-first-scrumban.md) (explicit):**

- This seam does **not** make board_os DB-first. The native board stays
  file-first; the DB stays a derived index. The seam is about *who owns the
  board*, not *where the native board stores state*.
- Disabling `tasks` **removes the native board**; it does **not** relocate or
  rewrite the user's `docs/tasks/TASK-NNN.md` files. They remain on disk, inert,
  re-activated the moment the module is re-enabled.

**Negative / deferred:**

- Status-vocabulary mapping (Linear states ↔ the Scrumban state machine) is
  per-adapter and is left to the implementing ADR.
- Two-way sync conflict policy (external edit vs local edit) is out of scope here
  and must be decided when an adapter is actually built.

## Alternatives considered

- **Hard-wire one tracker (e.g. Linear) into the kernel.** Rejected — host-locks
  the meta-project, forces public-tracker clutter for internal work, and adds a
  network dependency on the task hot path. Same trap the allocator-seam ADR
  rejected for ids.
- **Make `external_ref` the canonical id.** Rejected — see
  adr-task-id-allocator-seam.md; the offline `TASK-<token>` must stay canonical
  so create never needs the network and offline projects stay first-class.
- **A new parallel `cos_exttask_*` tool family.** Rejected — it would duplicate
  the whole surface and split every caller; standing the adapter behind the
  existing `cos_task_*` names keeps one surface and zero caller churn.
