<!-- domain:ARCH | layer:adr | ssot:true | updated:2026-04-20 -->

# ADR-0005: board_os — file-first Scrumban with DB sync, not DB-first

- **Status:** Accepted (2026-04-20)
- **Deciders:** Kourosh Ebrahimzadeh
- **Context tags:** scrumban, task-system, source-of-truth

## Context

Every task system has the same choice: where is the source of
truth?

1. **DB-first.** Tasks live in a SQLite/Postgres table; the agent
   reads and writes them via tool calls; markdown files are
   exports.
2. **File-first.** Tasks live as markdown files (`TASK-NNN-slug.md`)
   on disk; a DB indexes them for query but never owns them.

The coding-os agent reads files all day — that's its native
medium. A DB-first design would force the agent to context-switch
into "tool calls to enumerate tasks" instead of "grep / read /
edit", losing fluency. File-first keeps the agent in its medium.

But files-only loses two things the DB does well:

- Cross-cutting queries ("show me every blocked task in domain X
  with label perf").
- Eventual atomicity (mid-edit state in markdown is undefined; a
  DB row update is atomic).

## Decision

**File-first with DB as a derived index.** Specifically:

- `docs/tasks/TASK-NNN-slug.md` is the source of truth. Body,
  frontmatter (kind, swimlane, epic, labels, status), Work Log,
  Acceptance criteria — all in markdown.
- `.coding-os/coding-os.db::tasks` is rebuilt from the markdown
  files via `cos task-sync` (incremental on file mtime).
- `cos task-move`, `cos task-start`, etc. write **back to the
  markdown file first**, then update the DB row. The file is
  authoritative; the DB is reproducible.
- Query tools (`cos board`, `cos_task_*` MCP tools) read from
  the DB for speed but treat any conflict between file and DB as
  "file wins; resync".

The WIP limit, completion guardian, and intent enforcement all
read the file. The Hub UI reads the DB. They never disagree
because the DB is derived.

## Consequences

**Positive:**

- The agent edits tasks the same way it edits any other markdown
  doc — no special tooling. Tasks are diff-friendly.
- Reviewers can see task state changes in git history.
- The DB stays small and incremental; rebuild from scratch is
  cheap (seconds for a 200-task corpus).
- Cross-cutting queries (`cos board`, `cos_task_by_filter`) get
  DB speed for free.
- Audit trail is real: the markdown commit log IS the audit log.

**Negative:**

- File parse must be tolerant — malformed frontmatter cannot
  crash the indexer.
- Mid-edit state is visible (a half-edited frontmatter shows up
  in `cos board` until the file save completes + sync runs).
- Renames are a markdown operation, not a DB rename; the indexer
  has to detect renames via content hash.

**Mitigations:**

- The task-frontmatter validator (`validate-task-frontmatter.sh`
  pre-commit hook) catches malformed frontmatter at commit time.
- Mid-edit state is rare in practice (a save flushes within
  milliseconds; the sync polls every few seconds).
- Content-hash rename detection is implemented and tested
  (`src/core/board_os/sync.py`).

## Alternatives considered

- **DB-first.** Rejected — see Context (agent fluency).
- **GitHub Issues as backing store.** Tempting (free issue UI,
  integrated with PRs), rejected because (a) coding-os runs
  offline / per-project / without GH, (b) coupling the project's
  cognitive layer to a SaaS issue tracker is wrong direction.
- **Hybrid (some tasks in DB, some in files).** Rejected — the
  two-source ambiguity creates exactly the drift this design
  avoids.
