<!-- domain:CORE | layer:governance | ssot:true | updated:2026-06-10 -->
# ADR — Task-ID Allocator Seam + external_ref

**Status:** Accepted (2026-06-10, TASK-316). Builds on [adr-task-id-collision-resistance.md](adr-task-id-collision-resistance.md).

> Nav: [docs/](../) · [governance/](./)

## Context

Task ids must stay collision-free across many contributors AND across every
project `cos init` produces — most of which are NOT on GitHub. The
collision-resistance ADR shipped two offline allocators (`local` sequential,
`namespaced` per-contributor). The open risk is **getting trapped**: hard-wiring
a single allocator (e.g. GitHub issues) into `_next_task_id` would lock the
host-agnostic kernel to one forge and force a `task = issue` 1:1 that clutters
public trackers with internal work.

## Decision

Two seams, so any future allocator drops in with **zero migration** and issue
linking is **never** the primary id.

### 1. `TaskIdAllocator` seam

`_next_task_id` becomes a thin dispatcher over a strategy:

```python
class TaskIdAllocator(Protocol):
    def allocate(self, conn, project_root) -> str: ...
```

| allocator | id | network | status |
|---|---|---|---|
| `local` | `TASK-NNN` | none | shipped |
| `namespaced` | `TASK-<NS>-NNN` | none | shipped |
| `forge` | issue number → `TASK-42` | online (offline → falls back) | deferred behind seam |
| `service` | `id.coding-os.dev` atomic seq | online (offline → falls back) | deferred behind seam |

Contract: the id **format stays `TASK-<token>`** (the broadened canonical regex
already matches every variant); an allocator MUST be synchronous and offline-safe
or fall back to `local`/`namespaced`; the config key `task_id_scheme` selects it
(`local` is an alias of the default `sequential`). The seam is a pure refactor of
the two existing allocators — byte-identical output, existing tests stay green.

### 2. `external_ref` — optional bidirectional link, NOT the id

A task MAY carry one `external_ref` frontmatter field linking it to a forge
issue/PR. It is metadata for cross-referencing, never the canonical id:

- Shape: `<forge>#<n>` / `<forge>!<n>` — e.g. `github#42`, `gitlab!17`.
- Set via `cos task-link TASK-NNN <issue>`; the forge is **detected** from
  `git remote get-url origin` (github.com → github, gitlab → gitlab) — no
  hardcoded host in the kernel (P2).
- Never blocks task creation, never needs the network at create time, never
  drives uniqueness. A task without it is fully valid.

## Why not GitHub-issue-as-primary-id

It traps a meta-project: host-locks to GitHub (consumer projects use GitLab /
private / no forge), forces public-issue clutter for internal tasks, and adds a
network dependency on the task-create hot path with an unavoidable offline
fallback (so you maintain two id sources and must answer "which is canonical?").
The seam keeps the offline allocator canonical and makes the forge an *optional
link*, dissolving all four traps.

## Consequences

- Adding `forge`/`service` later = one new class + a config value, no migration,
  no id rewrite, no caller change.
- `external_ref` unlocks Linear-grade issue↔task↔PR navigation without coupling
  the kernel to any forge.
- Offline-first stays the kernel default; online is strictly opt-in per project.

## References

- [adr-task-id-collision-resistance.md](adr-task-id-collision-resistance.md)
- [src/core/board_os/mcp_tools.py::_next_task_id](../../src/core/board_os/mcp_tools.py)
- [task-lifecycle.md § Task ID Scheme](task-lifecycle.md)
