<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-04-06 -->
# Phase C — Hybrid Task Store: Execution Plan

> Nav: [Development Roadmap](./development-roadmap.md) | [Phase B Plan](./phase-b-rag-plan.md)

Purpose: Detailed, implementation-ready execution plan for Phase C (hybrid task storage — files as SSOT, SQLite as structured + semantic index).
Read when: Starting any Phase C sub-task.
Skip when: Working on unrelated maintenance or Phase A/B follow-ups.
Read next: [core/thinking_os/db.py](../core/thinking_os/db.py) (migration append pattern), [core/thinking_os/doc_indexer.py](../core/thinking_os/doc_indexer.py) (mtime sync pattern to mirror).

## Status

- **Phase A** ✅ Done (template completion, 38 tests)
- **Phase B** ✅ Done (RAG integration, 109 new tests, 639 total green, verified end-to-end on real NakoDigital 1063-chunk corpus; MCP stdio protocol verified; scale tested to 50K vectors)
- **Phase C** ⏳ This plan

## Context

NakoDigital has **241 task files** in `docs/tasks/TASK-###-slug.md` format. Each task is a structured markdown with exactly these sections (per `docs/governance/task-lifecycle.md`):

1. `## Goal` — 1-3 sentences
2. `## Read First` — REF codes / file paths
3. `## Source of Truth` — target code files
4. `## Scope` with `### In` and `### Out` subsections
5. `## Requirements` — numbered Given/When/Then acceptance criteria
6. `## Dependencies` — list of `TASK-### — description` refs
7. `## Open Questions` — "None." or unresolved items
8. `## Rabbit Holes` — "None." or traps
9. `## Verification` — commands to run
10. `## Notes` (optional)

Status is tracked **only** in `docs/tasks.md` (the task index). Each task line matches: `- [<status>] TASK-###: [DOMAIN] description`. Statuses: `[ ]` open, `[/]` in-progress, `[x]` done, `(BLOCKED: reason)`.

Currently the agent has no structured access. Every "which tasks depend on TASK-195?" requires grep-scanning 241 files. Phase C adds a `tasks` table that mirrors the files (SSOT preserved) plus semantic embeddings so the agent can:

- `cos_task_search("payment splitting")` — semantic query over 241 tasks
- `cos_task_dependents("TASK-195")` — graph-style impact analysis via indexed dependency column
- `cos_task_by_filter(domain="BACKEND", status="open")` — structured filter
- `cos_task_dependencies("TASK-199")` — what does this task need before it starts

## Design Decisions (locked in before implementation)

1. **Files are SSOT.** The DB is a derived cache. Any re-sync rebuilds the table from files. Never write back to files.
2. **mtime-based incremental sync** — reuse the pattern proven in `doc_indexer.py`. A file is re-parsed only when its mtime changed.
3. **Content hash dedup** — same SHA256[:16] helper as `capture.py` and `doc_indexer.py` for change detection beyond mtime.
4. **Status lives in `docs/tasks.md`, not detail files.** The sync reads both: detail files for content, `tasks.md` for status.
5. **Dependencies stored as JSON array** in the `tasks` table. Query via `LIKE '%TASK-195%'` on `dependencies` column for dependents lookup. Good enough for 241 tasks; not a real graph DB.
6. **Embedding scope**: embed `title + goal_text + " ".join(requirements)`. That's the richest compact signal for retrieval. Don't embed scope/out/rabbit-holes (too noisy).
7. **Parser is tolerant** — tasks missing any optional section (Rabbit Holes, Notes, Open Questions) must still parse. Only `Goal` is strictly required; everything else is optional.
8. **Auto-sync integration** — `make task-start`, `task-done`, `task-create` call the sync helper before doing their work. This keeps the DB current without requiring the agent to remember `task-sync`.
9. **No separate embedding source_table name** — use `"tasks"` as the `source_table` value in the existing `embeddings` table (already migration-v5 ready).
10. **Idempotent and safe under concurrent runs** — SQLite's WAL mode handles it, but the sync itself is a series of UPSERTs.

## Sub-Phase Breakdown

### C.1 — Migration v6: `tasks` table

**Goal:** add the structured task index table alongside Phase B's `document_chunks` and `embeddings`.

**Modified:** [core/thinking_os/db.py](../core/thinking_os/db.py)

Append migration v6 after v5:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,          -- "TASK-199"
    title           TEXT NOT NULL,             -- "[BACKEND] Commission model"
    domain          TEXT,                      -- BACKEND / FRONTEND / DOCS / INFRA / ...
    status          TEXT NOT NULL DEFAULT 'open',  -- open/wip/done/blocked
    file_path       TEXT NOT NULL,             -- relative: "docs/tasks/TASK-199-commission-model.md"
    content_hash    TEXT NOT NULL,             -- SHA256[:16] of parsed content
    mtime           INTEGER NOT NULL,          -- file mtime for incremental sync
    goal_text       TEXT,                      -- first paragraph of ## Goal
    scope_in        TEXT,                      -- JSON array
    scope_out       TEXT,                      -- JSON array
    requirements    TEXT,                      -- JSON array
    dependencies    TEXT,                      -- JSON array of TASK-### strings
    source_of_truth TEXT,                      -- JSON array of paths
    read_first      TEXT,                      -- JSON array of refs/paths
    open_questions  TEXT,                      -- raw text (or "None.")
    rabbit_holes    TEXT,                      -- raw text (or "None.")
    verification    TEXT,                      -- raw text of ## Verification section
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_domain ON tasks(domain);
CREATE INDEX IF NOT EXISTS idx_tasks_file_path ON tasks(file_path);
```

Also append `"tasks"` to `_TABLES` list in `get_db_stats()` so health check reports the count.

Add helper `has_tasks_table(conn)` following the `has_fts5_table` / `has_embeddings_table` pattern.

### C.2 — Parser module: `core/thinking_os/task_parser.py`

**New file.** Pure, stateless parser — no DB dependency, fully unit-testable.

Public API:

```python
@dataclass(frozen=True)
class ParsedTask:
    task_id: str              # "TASK-199"
    title: str                # "[BACKEND] Commission model" (without TASK-### prefix)
    raw_title: str            # "TASK-199: [BACKEND] Commission model" (original H1)
    domain: str | None        # "BACKEND" (from [DOMAIN] tag in title)
    goal_text: str            # first paragraph of ## Goal section
    scope_in: list[str]       # bullet list items from ### In
    scope_out: list[str]      # bullet list items from ### Out
    requirements: list[str]   # numbered items from ## Requirements
    dependencies: list[str]   # TASK-### refs extracted from ## Dependencies
    source_of_truth: list[str]  # bullet items from ## Source of Truth
    read_first: list[str]     # bullet items from ## Read First
    open_questions: str       # raw text (or "None.")
    rabbit_holes: str         # raw text (or "None.")
    verification: str         # raw text of ## Verification section
    content_hash: str         # SHA256[:16] of the full file content

def parse_task_file(content: str) -> ParsedTask | None:
    """Parse a task markdown file. Returns None if task_id cannot be extracted."""

def extract_task_id_from_h1(h1_text: str) -> tuple[str, str, str | None]:
    """Extract (task_id, title_without_prefix, domain) from `# TASK-199: [BACKEND] Title`."""

def extract_dependencies(section_text: str) -> list[str]:
    """Pull all TASK-### refs from a Dependencies section body."""
```

Parser strategy (matches the NakoDigital format documented in `task-lifecycle.md`):

1. Strip the `<!-- domain:... -->` front-matter header (like doc_indexer does).
2. Find H1: regex `^# (.+)$` on first match only. If none → return None.
3. Parse H1 with `r"^TASK-(\d+):\s*(?:\[([A-Z_-]+)\]\s*)?(.+)$"` to extract task_id, optional domain tag, title text.
4. Split content into sections by H2 headings (same `_split_by_pattern` pattern as `doc_indexer.py`).
5. For each expected section, look up by exact heading match (case-insensitive): Goal, Read First, Source of Truth, Scope, Requirements, Dependencies, Open Questions, Rabbit Holes, Verification.
6. For `## Scope`: find `### In` and `### Out` subsections.
7. For `## Goal`: take the first paragraph (up to first `\n\n`), strip whitespace.
8. For bulleted lists: extract lines starting with `- ` (strip the dash, trim).
9. For numbered lists (Requirements): extract lines matching `^\d+\.\s+(.+)$`.
10. For `## Dependencies`: run `extract_dependencies` — find all `TASK-\d+` patterns in the section body, dedupe, preserve order.

All sections are optional. Missing sections yield empty lists / "None." strings.

### C.3 — Sync module: `core/thinking_os/task_sync.py`

**New file.** Walks `docs/tasks/*.md`, parses each file, reads status from `docs/tasks.md`, upserts into the DB, and embeds the result.

Public API:

```python
def sync_tasks(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    tasks_dir: Path | None = None,
    index_file: Path | None = None,
    force: bool = False,
) -> dict:
    """Walk tasks/, parse each, sync to DB, embed.

    Returns stats dict:
        processed, skipped (mtime unchanged), new, updated, deleted (orphans), errors
    """

def parse_task_index(index_path: Path) -> dict[str, str]:
    """Parse docs/tasks.md → {task_id: status}.

    Handles four status patterns:
        - [ ] TASK-001: ...  → "open"
        - [/] TASK-001: ...  → "wip"
        - [x] TASK-001: ...  → "done"
        - (BLOCKED: reason) TASK-001: ...  → "blocked"
    """

def _upsert_task(conn, parsed: ParsedTask, file_path: str, mtime: int, status: str) -> None:
    """Insert or replace a row in the tasks table."""

def _delete_task(conn, task_id: str) -> None:
    """Remove a task row and its embedding."""

def _embed_task_safe(conn, task_id: str, title: str, goal_text: str, requirements: list[str]) -> None:
    """Embed title + goal + requirements. Fire-and-forget with debug logging."""
```

Sync algorithm:

1. Resolve `tasks_dir` (default: `project_root / "docs/tasks"`) and `index_file` (default: `project_root / "docs/tasks.md"`).
2. If `tasks_dir` does not exist → return stats with `processed=0` (not an error).
3. Read `docs/tasks.md` → build `status_by_task_id` map via `parse_task_index`.
4. Walk `tasks_dir` for `*.md` files (excluding `archive/` subdir).
5. For each file:
   a. Compute `mtime = int(stat.st_mtime)`.
   b. If not `force`: lookup existing row by `file_path`. If row exists and stored `mtime >= file_mtime` → skip.
   c. Read file content, run `parse_task_file(content)`.
   d. If `parse_task_file` returns None → log warning, increment errors, continue.
   e. Look up `status = status_by_task_id.get(task_id, "open")`.
   f. Compute rel_path from project_root (use `.resolve()` consistently — same fix as doc_indexer).
   g. `_upsert_task(conn, parsed, rel_path, mtime, status)`.
   h. `_embed_task_safe(...)` — fire-and-forget.
   i. Track `task_id` in `seen_task_ids`.
6. After walking: delete any row whose `task_id` is not in `seen_task_ids` (orphan cleanup — file was deleted).
7. `conn.commit()` at end.
8. Return stats.

### C.4 — MCP tools: `core/thinking_os/tools/tasks.py`

**New file.** Implements the four query functions. Pure functions over the `tasks` table.

Public API:

```python
def task_search(
    conn: sqlite3.Connection,
    query: str,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 10,
    threshold: float = 0.1,
) -> list[dict]:
    """Semantic + filter search over tasks.

    Algorithm:
        1. If embeddings available: embedding.search_similar(source_tables=['tasks'])
        2. Hydrate rows + apply status/domain filters.
        3. If embeddings unavailable or zero results: fall back to LIKE on title+goal_text.
        4. Return sorted by score DESC (or created_at DESC when LIKE fallback).
    """

def task_dependencies(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    """Get the tasks that `task_id` depends on (upstream)."""

def task_dependents(conn: sqlite3.Connection, task_id: str) -> list[dict]:
    """Get the tasks that depend on `task_id` (downstream).

    Implementation: SELECT from tasks WHERE dependencies LIKE '%"TASK-NNN"%'.
    Stores dependencies as a JSON-encoded list, so the quoted form makes
    partial-match false positives (TASK-19 vs TASK-195) impossible.
    """

def task_by_filter(
    conn: sqlite3.Connection,
    status: str | None = None,
    domain: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Structured filter, no semantic query. Orders by task_id ASC."""
```

Each function returns a list of dicts with consistent shape:

```python
{
    "task_id": "TASK-199",
    "title": "[BACKEND] Commission model",
    "domain": "BACKEND",
    "status": "open",
    "file_path": "docs/tasks/TASK-199-commission-model.md",
    "goal_text": "Design and implement a flexible commission model...",
    "score": 0.73,                   # only for task_search
    "dependencies": ["TASK-195"],    # parsed JSON
}
```

### C.5 — MCP server registration: `core/thinking_os/server.py`

Register four new `@mcp.tool` decorators after `cos_doc_search`:

```python
@mcp.tool(name="cos_task_search", annotations={"readOnlyHint": True, ...})
def cos_task_search(query: str, status: str = "", domain: str = "", limit: int = 10) -> str:
    results = task_search(_db_conn, query=query, status=status or None, domain=domain or None, limit=limit)
    return json.dumps({"results": results, "count": len(results)}, indent=2, default=str)

@mcp.tool(name="cos_task_dependencies", annotations={"readOnlyHint": True, ...})
def cos_task_dependencies(task_id: str) -> str:
    results = task_dependencies(_db_conn, task_id)
    return json.dumps({"task_id": task_id, "dependencies": results, "count": len(results)}, indent=2, default=str)

@mcp.tool(name="cos_task_dependents", annotations={"readOnlyHint": True, ...})
def cos_task_dependents(task_id: str) -> str:
    results = task_dependents(_db_conn, task_id)
    return json.dumps({"task_id": task_id, "dependents": results, "count": len(results)}, indent=2, default=str)

@mcp.tool(name="cos_task_by_filter", annotations={"readOnlyHint": True, ...})
def cos_task_by_filter(status: str = "", domain: str = "", limit: int = 20) -> str:
    results = task_by_filter(_db_conn, status=status or None, domain=domain or None, limit=limit)
    return json.dumps({"results": results, "count": len(results)}, indent=2, default=str)
```

Also extend `cos_health` to report `tasks_count` under the existing `rag` block → rename to a broader `thinking_os` or add a new `tasks` block. Safer choice: add `tasks_count` to the existing stats dict at top level.

After C.5, MCP tool count goes from **17 → 21**.

### C.6 — Auto-sync hooks: wire sync into `task-start`, `task-done`, `task-create`

**Modified:** [core/scripts/task-start.sh](../core/scripts/task-start.sh), [core/scripts/task-done.sh](../core/scripts/task-done.sh), [core/scripts/task-create.sh](../core/scripts/task-create.sh)

Each script currently runs fire-and-forget Python blocks for thinking_os side effects. Add a similar fire-and-forget block at the end of each:

```bash
# Auto-sync tasks table (Phase C) — fire-and-forget, never blocks the user
(
  python3 -c "
import sys, os
sys.path.insert(0, '${COS_ROOT}/core/thinking_os')
try:
    from db import init_db
    from task_sync import sync_tasks
    from pathlib import Path
    conn = init_db(os.environ.get('COS_DB_PATH'))
    sync_tasks(conn, project_root=Path.cwd())
    conn.close()
except Exception as exc:
    print(f'task sync skipped: {exc}', file=sys.stderr)
" > /dev/null 2>&1 &
)
```

Why fire-and-forget? Because:

- The agent should never wait for sync when starting/completing a task.
- A missing DB / missing RAG extras should never break the task lifecycle.
- `sync_tasks` is idempotent and cheap (mtime check skips unchanged files).

### C.7 — Makefile.base: `make task-sync` target

**Modified:** [templates/_base/Makefile.base](../templates/_base/Makefile.base)

```makefile
.PHONY: task-sync
task-sync: ## Sync docs/tasks/*.md → thinking_os.db (Phase C)
	@uv run --extra rag --directory $(COS_ROOT) python -m core.thinking_os.task_sync --project-root . --db $(COS_DB_PATH)

.PHONY: task-resync
task-resync: ## Force full re-sync of all task files
	@uv run --extra rag --directory $(COS_ROOT) python -m core.thinking_os.task_sync --project-root . --db $(COS_DB_PATH) --force
```

Add a CLI entry point `_main()` to `task_sync.py` with `argparse` (mirroring `doc_indexer.py`'s `_main`).

## Test Plan (explicit)

### C.T1 — `tests/test_task_parser.py` (NEW — pure unit tests, no DB)

| Test class | Test |
|---|---|
| `TestExtractH1` | `test_extracts_task_id_domain_title` |
| | `test_title_without_domain_tag` |
| | `test_malformed_h1_returns_none` |
| `TestStripFrontMatter` | `test_removes_comment_header` |
| | `test_no_front_matter_unchanged` |
| `TestGoalExtraction` | `test_first_paragraph_only` |
| | `test_handles_multi_line_goal` |
| | `test_missing_goal_returns_empty` |
| `TestScopeExtraction` | `test_parses_in_and_out_subsections` |
| | `test_missing_scope_returns_empty_lists` |
| | `test_scope_without_subsections` |
| `TestRequirementsExtraction` | `test_numbered_list_parsed` |
| | `test_missing_requirements_returns_empty_list` |
| `TestDependenciesExtraction` | `test_single_dependency` |
| | `test_multiple_dependencies_dedupe` |
| | `test_none_returns_empty_list` |
| | `test_task_ref_in_prose_detected` |
| | `test_no_partial_match_task19_vs_task195` |
| `TestContentHash` | `test_hash_deterministic` |
| | `test_hash_differs_for_different_content` |
| `TestEndToEnd` | `test_parses_real_nakodigital_task_199` — uses the actual TASK-199-commission-model.md content as a fixture |
| | `test_parses_minimal_task_with_only_goal` |
| | `test_returns_none_when_no_task_id_in_h1` |

Target: **~22 tests, all pass without `rag` extras** (parser is pure).

### C.T2 — `core/thinking_os/tests/test_db.py` additions

| Test (class `TestMigrationV6Tasks`) | What |
|---|---|
| `test_tasks_table_created` | Table exists after migration |
| `test_tasks_columns` | All 17 expected columns present |
| `test_tasks_primary_key_is_task_id` | UNIQUE on task_id |
| `test_tasks_indexes_exist` | idx_tasks_status, idx_tasks_domain, idx_tasks_file_path |
| `test_has_tasks_table_helper` | Returns True after migration, False before |
| `test_v6_idempotent` | Running migrations twice is a no-op |
| `test_tasks_in_get_db_stats` | `get_db_stats()` reports tasks count |

Target: **7 tests, all pass without `rag` extras.**

### C.T3 — `core/thinking_os/tests/test_task_sync.py` (NEW)

| Test class | Test |
|---|---|
| `TestParseTaskIndex` | `test_parses_open_status` |
| | `test_parses_wip_status` |
| | `test_parses_done_status` |
| | `test_parses_blocked_status` |
| | `test_ignores_phase_headings` |
| | `test_missing_index_returns_empty_map` |
| `TestSyncTasks` | `test_first_run_indexes_all` |
| | `test_second_run_skips_unchanged` |
| | `test_modified_file_re_synced` |
| | `test_deleted_file_removed_from_db` |
| | `test_status_read_from_tasks_md` |
| | `test_missing_tasks_dir_returns_empty_stats` |
| | `test_invalid_task_file_counted_as_error` |
| | `test_force_resyncs_all` |
| `TestSyncEmbeddings` (marked `REQUIRES_RAG`) | `test_sync_creates_embeddings` |
| | `test_re_sync_updates_embedding_on_content_change` |
| | `test_sync_succeeds_without_rag_extras` (patched) |

Target: **~16 tests, ~13 run without rag extras + 3 marked.**

### C.T4 — `core/thinking_os/tests/test_task_tools.py` (NEW)

| Test class | Test |
|---|---|
| `TestTaskByFilter` | `test_filter_by_status_open` |
| | `test_filter_by_status_done` |
| | `test_filter_by_domain` |
| | `test_filter_by_status_and_domain` |
| | `test_limit_respected` |
| | `test_empty_db_returns_empty_list` |
| `TestTaskDependencies` | `test_returns_prerequisites` |
| | `test_returns_empty_for_task_with_no_deps` |
| | `test_returns_empty_for_unknown_task` |
| `TestTaskDependents` | `test_finds_single_dependent` |
| | `test_finds_multiple_dependents` |
| | `test_no_false_positive_substring` (TASK-19 not a dependent of TASK-195) |
| | `test_returns_empty_for_leaf_task` |
| `TestTaskSearch` (REQUIRES_RAG) | `test_semantic_search_finds_related_task` |
| | `test_semantic_search_honors_status_filter` |
| | `test_semantic_search_honors_domain_filter` |
| | `test_like_fallback_when_embeddings_unavailable` (patched) |
| | `test_empty_query_returns_empty` |
| | `test_limit_respected` |

Target: **~19 tests, ~13 run without rag extras + 6 marked.**

### C.T5 — End-to-end integration test (Python script under `scripts/verify-phase-c-e2e.sh` — NEW)

After the main test suite, run a scripted E2E that mirrors the Phase B smoke test:

1. Create a temp project via `coding-os init --agent claude --template django`
2. Copy the entire NakoDigital `docs/tasks/` directory (241 files) into the project
3. Copy the NakoDigital `docs/tasks.md` into the project root
4. Run `task_sync.sync_tasks` once → verify 241 tasks indexed, 0 errors
5. Run again → verify 241 skipped, 0 updated
6. Modify one task file + bump mtime → verify exactly 1 updated
7. Query `task_search("commission payment splitting")` → verify relevant results
8. Query `task_dependents("TASK-195")` → verify real downstream tasks from NakoDigital
9. Query `task_by_filter(domain="BACKEND", status="open")` → verify count > 0
10. Run MCP stdio protocol test: call each of the four new tools via JSON-RPC

This script is **not** part of the pytest suite (it needs NakoDigital as an external fixture). It lives in `scripts/` and is invoked manually or via a Makefile target for manual verification.

### Test count target

| Test file | New tests |
|---|---|
| `tests/test_task_parser.py` | ~22 |
| `core/thinking_os/tests/test_db.py` (additions) | 7 |
| `core/thinking_os/tests/test_task_sync.py` | ~16 |
| `core/thinking_os/tests/test_task_tools.py` | ~19 |
| **Total** | **~64 new tests** |

All non-rag tests (≥52 of the ~64) must pass without `rag` extras installed — this enforces graceful degradation for the whole task store pipeline.

## Files Summary

| Type | Path |
|---|---|
| New module | [core/thinking_os/task_parser.py](../core/thinking_os/task_parser.py) |
| New module | [core/thinking_os/task_sync.py](../core/thinking_os/task_sync.py) |
| New module | [core/thinking_os/tools/tasks.py](../core/thinking_os/tools/tasks.py) |
| Modified | [core/thinking_os/db.py](../core/thinking_os/db.py) — migration v6 + `_TABLES` + `has_tasks_table` |
| Modified | [core/thinking_os/server.py](../core/thinking_os/server.py) — 4 new MCP tools + `cos_health` tasks count |
| Modified | [core/scripts/task-start.sh](../core/scripts/task-start.sh) — auto-sync hook |
| Modified | [core/scripts/task-done.sh](../core/scripts/task-done.sh) — auto-sync hook |
| Modified | [core/scripts/task-create.sh](../core/scripts/task-create.sh) — auto-sync hook |
| Modified | [templates/_base/Makefile.base](../templates/_base/Makefile.base) — `task-sync` + `task-resync` targets |
| New tests | `core/thinking_os/tests/test_task_parser.py` |
| New tests | `core/thinking_os/tests/test_task_sync.py` |
| New tests | `core/thinking_os/tests/test_task_tools.py` |
| Modified tests | `core/thinking_os/tests/test_db.py` (add `TestMigrationV6Tasks`) |
| New script (manual E2E) | `scripts/verify-phase-c-e2e.sh` |

## Existing Code to Reuse

| Pattern | Source | Reuse for |
|---|---|---|
| Migration append pattern | `db.py:MIGRATIONS.append` | Add `(6, ..., _migrate_v6_tasks)` |
| FTS5/embeddings graceful degradation | `tools/memory.py:_augment_with_semantic` | Same structure for `task_search` semantic + LIKE fallback |
| mtime incremental sync | `doc_indexer.py:index_docs` | Same pattern for `sync_tasks` |
| Path resolution fix for macOS `/tmp` vs `/private/tmp` | `doc_indexer.py:index_docs` (just fixed) | Apply same `resolve()` pattern |
| Content hash helper | `embeddings._compute_text_hash` + `capture._compute_content_hash` | Same SHA256[:16] convention |
| Markdown section split | `doc_indexer._split_by_pattern` | Used by `task_parser` for section extraction |
| Fire-and-forget embedding helper | `tools/learning._embed_pattern_safe` | Mirror for `_embed_task_safe` |
| MCP tool registration | `server.py:cos_doc_search` block | Copy the structure for 4 new cos_task_* tools |
| CLI entry point | `doc_indexer._main()` | Copy for `task_sync._main()` |

## Verification Matrix (Phase C complete)

```bash
# 1. Migration v6 applied cleanly
uv run python -c "
from core.thinking_os.db import init_db, has_tasks_table, MIGRATIONS
c = init_db()
assert has_tasks_table(c)
assert len(MIGRATIONS) == 6
print('OK')
"

# 2. Parser unit tests (pure, no rag required)
uv run pytest core/thinking_os/tests/test_task_parser.py -v

# 3. Sync tests (mostly pure)
uv run pytest core/thinking_os/tests/test_task_sync.py -v

# 4. Task tools tests
uv run pytest core/thinking_os/tests/test_task_tools.py -v

# 5. Full suite green with and without rag extras
uv run --extra rag pytest core/thinking_os/tests/ tests/ -q
uv run pytest core/thinking_os/tests/ tests/ -q  # must still pass (just skip rag-marked)

# 6. MCP protocol exposes new tools
# (same stdio JSON-RPC harness used for Phase B)
python3 scripts/mcp-protocol-test.py
# Expected: tools/list contains cos_task_search, cos_task_dependencies,
#           cos_task_dependents, cos_task_by_filter

# 7. Manual E2E on real NakoDigital 241 tasks
bash scripts/verify-phase-c-e2e.sh
# Expected: sync reports 241 processed, 0 errors; queries return sensible results
```

## Sub-Phase Ordering and Commit Strategy

Each sub-phase should be independently shippable. Suggested order (same as the numbering):

1. **C.1** — Migration v6 only. One commit. Runs all existing tests green (plus 7 new migration tests).
2. **C.2** — `task_parser.py` + its ~22 unit tests. One commit. No DB changes needed.
3. **C.3** — `task_sync.py` + its ~16 tests. Depends on C.1 and C.2. One commit.
4. **C.4** — `tools/tasks.py` + ~19 tests. Depends on C.1. One commit.
5. **C.5** — `server.py` MCP tool registration. Depends on C.4. One commit.
6. **C.6** — Auto-sync hooks in `task-*.sh`. Depends on C.3. One commit.
7. **C.7** — Makefile targets + CLI `_main()`. One commit.
8. **Final** — Roadmap update + E2E verification script. One commit.

## Open Decisions (to revisit during implementation)

1. **Should `task_search` embed `title + goal + requirements` or just `title + goal`?**
   Recommendation: include requirements — they contain the actionable language ("commission calculated at checkout"). Re-evaluate if relevance drops.

2. **Should `task_dependents` traverse transitively?**
   Recommendation: no, direct dependents only. Callers can compose for multi-hop.

3. **Should status be a separate lightweight sync (just parse `tasks.md`) so `make task-done` updates status fast?**
   Recommendation: yes — add `sync_status_only(conn, project_root)` as a second entry point. Called from `task-done.sh` for instant status refresh without re-embedding every task.

4. **Auto-sync on every `make task-start`/`task-done` — is fire-and-forget with `&` safe on all shells?**
   Recommendation: yes, bash+zsh both handle it. Add `wait` in test harnesses to avoid races.

5. **Should `cos_task_search` deduplicate results the same way `cos_doc_search` does (max per file)?**
   Recommendation: no. One row per task, no dedupe needed. Each task already corresponds to exactly one file.

## Estimated scope

- **New Python:** ~700 LOC (`task_parser.py ~250`, `task_sync.py ~250`, `tools/tasks.py ~200`)
- **New tests:** ~600 LOC (~64 tests across 3 new files + additions to test_db.py)
- **Modifications:** ~100 LOC (migration v6, 4 MCP tools in server.py, 3 script hooks, 2 Makefile targets)

**Smaller than Phase B** because we reuse all the infrastructure (embeddings, migration pattern, MCP registration, graceful degradation pattern) — Phase B did the heavy lifting.
