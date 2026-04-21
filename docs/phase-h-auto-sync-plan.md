<!-- domain:ALL | layer:reference | ssot:true | updated:2026-04-18 -->
# Phase H — Auto-sync on Writes (Freshness Contract)

Purpose: Close the single most dangerous operational gap left after Phase G — stale retrieval data when a doc is edited without a manual `make docs-index`.
Read when: Starting any H.* sub-task, wiring a new write-path into the index pipeline, or investigating "cos_doc_search returns old content".
Read next: [core/thinking_os/doc_indexer.py](../core/thinking_os/doc_indexer.py), [core/hooks/registry.yaml](../core/hooks/registry.yaml), [docs/phase-g-brain-hardening-plan.md](./phase-g-brain-hardening-plan.md).

## Why (audit finding)

After Phase G, the brain is hardened but not self-freshening:

| Write path | Auto-sync today | Gap |
|---|---|---|
| Edit code file (`*.py` / `*.ts`) | ✅ `observations` + embedding (capture.py) | — |
| `task-start` / `task-done` / `task-create` | ✅ `tasks` table sync | — |
| Outcome recording | ✅ `outcome_history` + narrative embedding | — |
| **Edit `docs/PRD/*.md`** | ❌ **stale until manual `make docs-index`** | H.1 |
| **Edit `docs/engineering/*.md`** | ❌ same | H.1 |
| **Create/delete any rag-config source** | ❌ same | H.1 |
| Edit `docs/tasks/*.md` outside `task-*` | ❌ tasks index may drift | H.2 |

**Real-world symptom:** user edits `docs/PRD/billing.md` v1 → v2, agent subsequently queries `cos_doc_search("billing")` and retrieves v1. Silent regression.

Phase G.9 background indexer (opt-in) *eventually* closes this at 5-min cadence — but freshness should be deterministic, not best-effort. Phase H makes it immediate on every Edit/Write.

## Principles

- **P-H-1: Freshness by default.** No agent should ever need to remember to run `make docs-index` between an edit and the next retrieval.
- **P-H-2: Fire-and-forget.** The hook never blocks the Write/Edit tool call; worst-case freshness lag = one re-index cycle (~200ms cold, ~20ms warm).
- **P-H-3: Incremental.** Re-index ONE file, never the whole corpus on every edit. mtime + content_hash guards do the heavy lifting.
- **P-H-4: Scoped.** The hook fires only for files that match a `rag-config.yaml` source. Edits to `docs/playbooks/`, code files, or anything outside RAG scope are ignored — no wasted work.
- **P-H-5: Adapter-agnostic.** Hook declared once in `core/hooks/registry.yaml` and auto-rendered into both `.claude/settings.json` and `.codex/hooks.json`.
- **P-H-6: Degrades cleanly.** Pre-v5 DBs, missing embeddings, model load failure — all silently no-op. Never errors out a legitimate Write.

## Phase H Roadmap

| Slice | Scope | LOC | Ship gate |
|---|---|---|---|
| **H.1** | `doc_indexer.index_single_file(conn, file_path)` — single-file incremental re-index with embedding refresh + orphan cleanup | ~80 | `test_index_single_file` green |
| **H.2** | `core/hooks/auto-reindex-docs.sh` — PostToolUse hook (Write\|Edit) that classifies the path and fires H.1 in background | ~90 | hook syntax check + fire test |
| **H.3** | Registry entry in `core/hooks/registry.yaml` + `make regen-adapter-templates` | ~10 | adapter templates re-rendered, `warn-template-drift.sh` silent |
| **H.4** | Freshness contract paragraph in `templates/_base/fragments/retrieval-routing.md.tmpl` + `CLAUDE.md` | 0 code | docs-lint pass |
| **H.5** | E2E tests: edit doc → assert chunk updated; edit excluded path → assert no reindex; concurrent edits | ~150 | full test suite green |

**Execution order:** H.1 → H.5 strictly sequential. H.3 depends on H.2 entry; H.4 can parallel after H.3.

## H.1 — `index_single_file()`

**Contract:**

```python
def index_single_file(
    conn: sqlite3.Connection,
    file_path: Path,
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    project_root: Path,
) -> dict:
    """Incrementally (re-)index a single markdown file.

    PURPOSE:   Single-file freshness path for the auto-reindex hook.
               Called per Edit/Write, so must be cheap (<100ms warm).
    INPUT:     abs or relative file_path; project_root; config_path.
    OUTPUT:    {status: "reindexed"|"skipped"|"unscoped"|"unchanged",
                file: str, new_chunks: int, deleted_chunks: int}
    DEPENDS:   rag-config.yaml source match, document_chunks, embeddings.
    NOTES:     - Resolves file_path.resolve().relative_to(project_root_resolved)
                 so /tmp ↔ /private/tmp symlink doesn't bite (macOS).
               - Returns {status: "unscoped"} when file is NOT matched by any
                 rag-config source — the hook uses this to decide silence.
               - mtime guard: compare to max(document_chunks.mtime)
                 for source_path; if equal + not forced, return "unchanged".
               - On chunk delta (old mtime differs): delete existing chunks
                 for that source_path, re-chunk, insert, embed each.
    """
```

Reuses: `chunk_markdown`, `load_rag_config`, `_delete_chunks_for_path`, `_embed_chunk_safe` already in doc_indexer.py.

## H.2 — `auto-reindex-docs.sh`

```bash
#!/usr/bin/env bash
# PostToolUse hook: after a Write or Edit, if the file belongs to a
# rag-config.yaml source, fire a single-file re-index in background.
# Never blocks; output discarded; errors logged to .reindex-errors.log.
```

**Matcher:** `Write|Edit` (PostToolUse).

**Behavior:**
1. Read tool_name + file_path from stdin JSON.
2. If not Write|Edit → exit 0.
3. Resolve file_path to absolute → compare against rag-config sources in a fast Python one-liner (re-uses `walk_sources` logic).
4. If unscoped → exit 0 silently.
5. If scoped → fire `python -c "from doc_indexer import index_single_file..."` in background (`&`) so the Edit returns immediately.
6. Errors → append to `${COS_STATE_DIR}/.reindex-errors.log` (bounded, ~200 lines).

**Task-file special case:** if `file_path` matches `docs/tasks/TASK-*.md`, also trigger `task_sync.sync_one()` so the structured tasks table stays fresh outside `make task-*`.

## H.3 — Registry + Adapter Regen

Add to `core/hooks/registry.yaml`:

```yaml
- name: auto-reindex-docs
  script: core/hooks/auto-reindex-docs.sh
  events: [PostToolUse]
  matchers: ["Write", "Edit"]
  category: retrieval
  phase: H
  description: >
    Auto-reindex docs in the rag-config.yaml sources after any Edit/Write.
    Fire-and-forget; keeps cos_doc_search returns current without manual
    `make docs-index`.
```

Then `make regen-adapter-templates` writes the entry into both
`adapters/claude/settings.template.json` and
`adapters/codex/hooks.template.json`. The `warn-template-drift.sh` hook
verifies no hand-edits happened.

## H.4 — Freshness Contract (Docs)

Add to `templates/_base/fragments/retrieval-routing.md.tmpl`:

> **Freshness contract (Phase H).** Every Write/Edit on a file matched by
> `rag-config.yaml` triggers an automatic incremental re-index via the
> `auto-reindex-docs` PostToolUse hook. Agents MUST NOT assume
> `make docs-index` is needed after a doc edit — `cos_doc_search` already
> reflects the latest `mtime`. If you suspect staleness, run
> `cos hooks-log | grep auto-reindex-docs` to confirm the hook fired.

Mirror the same paragraph into `CLAUDE.md § Three-Layer Retrieval`.

## H.5 — Tests

`core/thinking_os/tests/test_auto_reindex.py`:

1. `test_index_single_file_new_file` — file not in DB → inserts chunks + embeddings
2. `test_index_single_file_edit_updates_content` — edit → old chunks removed, new chunks inserted, content reflects edit
3. `test_index_single_file_mtime_unchanged_is_noop` — same mtime → `status: "unchanged"`
4. `test_index_single_file_unscoped_path_returns_unscoped` — `docs/playbooks/X.md` → `status: "unscoped"`
5. `test_index_single_file_handles_delete` — file removed between events → status: "skipped"
6. `test_index_single_file_survives_missing_embeddings` — rag extras not installed → still inserts rows, no raise
7. `test_hook_fires_on_write_event` — simulate tool input → assert hook exited 0 + reindex log row
8. `test_hook_silent_on_unscoped_write` — edit `docs/playbooks/x.md` → hook exits 0, no reindex

## Risks & Mitigations

- **R-H-1: Re-index on every edit is expensive.** Mitigation: mtime + content_hash double-check → ~95% of edits short-circuit in <5ms.
- **R-H-2: Fire-and-forget hides errors.** Mitigation: bounded `.reindex-errors.log`; cos_health counts + surfaces recent errors.
- **R-H-3: Concurrent edits race.** Mitigation: each hook invocation opens its own DB connection (SQLite WAL handles concurrent readers/writers). index_single_file is idempotent w.r.t. duplicate mtime.
- **R-H-4: Embedding model cold-start on first invocation after session start.** Mitigation: hook is async, so the Edit returns instantly even if the embed takes 200ms behind the scenes.
- **R-H-5: Agent writes to excluded path thinking it's indexed.** Mitigation: H.4 contract is explicit; `cos_doc_search` meta explains `source_type` so agent sees which files are in scope.

## Ship Checklist

- [ ] `index_single_file` added to doc_indexer.py with tests
- [ ] `auto-reindex-docs.sh` syntax-valid, fires only on scoped paths
- [ ] Registry entry applied; `make regen-adapter-templates` no-op on second run
- [ ] Freshness paragraph in retrieval-routing fragment + CLAUDE.md
- [ ] All G.* and H.* tests pass
- [ ] MCP self-test green at schema v11
- [ ] `cos hooks-log --follow` shows `auto-reindex-docs` fire on a test edit
