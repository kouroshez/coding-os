---
name: search
tier: exploration
domain: [universal]
description: 'Use for ANY search, find, replace, or rename operation across a codebase — text literals, code symbols, semantic concepts, docs, or tasks. INVOKE BEFORE grep, before rename, before "find all X", before any cross-cutting edit. Enforces ground-truth counting before edits so nothing gets missed. Triggers — "find all", "rename X to Y", "replace everywhere", "where is X used", "update all references", "search for", "grep for", "change X to Y in all files", refactor, rename, cross-cutting edits.'
last_reviewed: "2026-05-11"

---

# search

Purpose: Route every search task to the correct layer, establish a ground-truth count before any edit, and verify zero remaining matches after. Prevents: agent edits some matches, declares done, but 20+ remain.

Read when: Anything involving finding or replacing something — in files, code, memory, docs, tasks.

Skip when: You already have the exact file:line from a search earlier in this session and are doing a single-file targeted edit.

## Step 0 — Decision Gate

| Target | Layer | Tools |
|---|---|---|
| Literal text / string in files | **File** | `grep -rnF` → see `references/grep.md` |
| Code symbol — function, class, import, MCP tool | **Graph** | → use `graph-explorer` skill |
| Semantic concept / "how did we solve X" | **Memory** | `cos_search` |
| Spec / doc by meaning | **Docs** | `cos_doc_search` |
| Task / ticket by topic | **Tasks** | `cos_task_search` |

**Composition:** For a symbol rename, run Graph first (graph-explorer gives you call-sites + doc refs), then File verify to catch comments and unindexed strings. Never rely on a single layer for cross-cutting renames.

## Step 1 — INVENTORY (mandatory before any edit)

```bash
# Get ground truth count — this number must reach 0 after editing
grep -rnF "OLD_STRING" . $EXCL | wc -l   # N = ground truth

# List affected files
grep -rlF "OLD_STRING" . $EXCL
```

N is your contract. You are not done until the same command returns 0.

**Never edit before knowing N.** This is the root cause of the "declared done but 20 remain" failure.

## Step 2 — VARIANT SCAN

Run a multi-variant search before editing. Same string appears in multiple forms.

```bash
grep -rnF -e "MyClass" -e "my_class" -e "MY_CLASS" -e '"MyClass"' . $EXCL
```

→ Full variant families and flag reference: `references/grep.md`

## Step 3 — EDIT

For small counts (< 10 files): use `Edit` per file.
For bulk: use `grep -rlZF ... | xargs -0 sed ...` or Python replace.

→ Replace options with NUL-safe pipelines: `references/grep.md`

**Skip generated / lock / migration files** — note them, regenerate via `make` instead.

## Step 4 — VERIFY (no exceptions)

```bash
# Must return 0 lines — if not, return to Step 2
grep -rnF "OLD_STRING" . $EXCL

# Confirm replacement landed
grep -rnF "NEW_STRING" . $EXCL | wc -l

git diff --stat
```

## Existing hook coverage

`verify-rename-callers.sh` fires automatically on every `Edit` and warns if the old identifier still appears in other files. Coverage: identifier-shaped strings ≥ 4 chars only. **This hook is a safety net — it does not replace the ground-truth protocol above**, which covers non-identifier strings, YAML, docs, and bulk bash operations.

## Required report (end of every search/replace task)

```
Pattern(s): <what was searched>
Variants checked: <all forms>
Ground truth count: N
Files changed: X | Files skipped: Y (reason)
Matches remaining: 0  (verify grep: empty ✓)
Layers used: File / Graph / Memory / Docs / Tasks
Risks: <public API, DB migration, generated files, etc.>
```

"Done" without this report is not done.
