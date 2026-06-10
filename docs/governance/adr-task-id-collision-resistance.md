<!-- domain:META | layer:adr | ssot:true | updated:2026-06-09 -->
# ADR — Task ID Collision Resistance for OSS Multi-Contributor Flow

**Status:** Accepted (2026-06-09) — implemented as a per-contributor namespaced scheme (TASK-298). Originally Proposed 2026-05-23.
**Context:** User report — "if many contributors fork the repo and create tasks in parallel, all of them compute `TASK-016` independently, then collide at PR merge."

## Decision (implemented, TASK-298)

A config-driven, opt-in **per-contributor namespace** — a refinement of Option 2 that DOES solve the cross-fork collision (Option 2's per-*project* prefix did not). `.coding-os/scrumban-config.yaml`:

- `task_id_scheme: sequential` (default) → `TASK-NNN`, unchanged. Single-owner projects pay nothing.
- `task_id_scheme: namespaced` → `TASK-<NS>-NNN`, where `NS` is `task_id_prefix` (e.g. `KO`) or derived from `git config user.email`. The counter is per-`NS`, so `KO-280` and `JD-280` are distinct — two un-synced contributors cannot collide.

It is offline-first (no allocator/server), keeps the readable+sortable id shape, and is backward-compatible: one broadened regex matches both `TASK-NNN` and `TASK-<NS>-NNN` across every task-id-aware site (parser, frontmatter, `.task-current`, commit-linking, `git log --grep`), so a project switches schemes without rewriting existing ids. The GitHub-issue allocator (Option 3) remains a future enhancement layered on top, not a prerequisite.

Why per-contributor rather than the originally-recommended GitHub-issue path first: the namespace solves the stated problem with **zero new dependency** (no `gh` auth, works offline), which the owner prioritised over the bi-directional issue UX.

## Current state

`docs/tasks/TASK-NNN-*.md` files use a monotonic counter resolved by [`src/core/board_os/mcp_tools.py::_next_task_id`](../../src/core/board_os/mcp_tools.py) — it scans both the local SQLite (`tasks` table) and the filesystem (`TASK-*.md` glob), takes the max, increments. Atomic within a single workstation. **Not atomic across forks**, because each fork's local max is its own snapshot of the upstream.

For solo-dev / single-fork use this is perfect: every ID is short (`TASK-016`), sortable, and human-readable. The failure mode appears only when N forks compute the next ID in parallel without seeing each other.

## Options compared

### Option 1 — Status quo + manual rename on collision

**Mechanics:** Contributors create `TASK-NNN` locally; if the PR fails to merge because the slug already exists upstream, CI renames the file before merge.

| Pro | Con |
|---|---|
| Zero code change | High friction on contributors (their commit SHAs change) |
| Readable IDs | Lost task references in PR descriptions / commits |

### Option 2 — Project key prefix (Linear / Jira pattern)

**Mechanics:** `task_id_prefix: COS` in `.coding-os/scrumban-config.yaml`; tasks render as `COS-016`. Each consumer project picks its own prefix.

| Pro | Con |
|---|---|
| Linear-style readability | Doesn't solve the cross-fork collision (two contributors still both pick `COS-016`) |
| Trivial implementation (~20 lines) | Only useful as a foundation for option 3 or 4 |

### Option 3 — GitHub Issues as the allocator (recommended for OSS)

**Mechanics:** Contributors run `gh issue create --title "<one-liner>"` first; GitHub server-side assigns an issue number (atomic, fork-safe). Their local `cos task-create --issue 42` then mints `COS-42-slug.md`. The issue # IS the task ID.

| Pro | Con |
|---|---|
| Atomic + collision-free by construction | Requires GitHub authentication on contributor's machine |
| Free bi-directional UX (issue ↔ task) | Solo-dev mode still wants offline ID allocation — needs a "no-network fallback" |
| Cert-aligned (Domain 2.4 / 3.6 — programmatic enforcement) | Issue numbers and `COS-NNN` slugs may diverge in old projects |

### Option 4 — Time-sortable unique ID (ULID)

**Mechanics:** New IDs use `COS-01HN5KP3XY` (ULID = 26-char base32 timestamp + randomness). Always unique even across forks. Time-sortable. Backwards compat: existing `TASK-NNN` files keep their slugs.

| Pro | Con |
|---|---|
| Collision-free without any allocator | Less human-friendly than `COS-42` |
| Time-sortable (newer ULIDs sort later) | Filenames longer; harder to type |
| Works offline / no GitHub dependency | Two-style coexistence forever (legacy TASK-NNN + new ULID) |

### Option 5 — Hybrid: ULID storage + GitHub-issue display

**Mechanics:** Internally store a ULID per task (fork-safe). On display + filename, show `COS-<issue>` if the task is linked to a GitHub issue, else fall back to a short ULID. Renaming on PR merge upgrades the slug from ULID to issue number.

| Pro | Con |
|---|---|
| Best of both worlds | Most implementation work (~150 lines) |
| Migration path: legacy → ULID → issue | Two-layer naming = cognitive overhead in docs/playbooks |

## Recommendation

Adopt the layered path in this order:

1. **Today (Phase 8 ship):** add `task_id_prefix` to `scrumban-config.yaml` (Option 2 foundation). Default = `TASK` for backward compat. ~20 lines. No collision benefit, but unblocks both Option 3 and Option 5.
2. **Phase 11+:** implement Option 3 (`gh issue create` integration). 80% of OSS contributor pain solved. ~100 lines + GitHub CLI dep.
3. **Future (only if Option 3 is insufficient):** add Option 5 ULID fallback for contributors without `gh` auth.

**Why not jump straight to Option 5:** premature complexity. The user's stated problem is "OSS contributors collide" — Option 3 solves that with a UX contributors already understand (GitHub Issues). ULID is a power-user feature that adds complexity for solo-dev users (who are the current 100% of usage).

## Migration of existing tasks

Zero migration needed if Phase 8 lands as `task_id_prefix: TASK` (current state). Future projects can pick a different prefix in their `scrumban-config.yaml` from day one.

## Open questions

- **Should `cos task-create` ALWAYS create a GitHub issue when `gh` is on PATH?** Or only when explicitly `--issue`-flagged? Probably opt-in via flag; auto behavior surprises offline users.
- **What happens when a fork has no upstream link?** Falls back to local monotonic — same as today.

## References

- [src/core/board_os/mcp_tools.py::_next_task_id](../../src/core/board_os/mcp_tools.py) — the current allocator
- [src/core/board_os/config.py::ScrumbanConfig](../../src/core/board_os/config.py) — where `task_id_prefix` would be added
- [Linear docs on issue IDs](https://linear.app/docs/jira) (research source)
- [GitHub Issues atomic numbering](https://docs.github.com/en/issues) (research source)
- Claude Certified Architect exam guide Domain 2.4 (MCP server scoping) + 3.6 (CI integration) (research source)
