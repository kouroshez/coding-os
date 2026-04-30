<!-- domain:CORE | layer:spec | ssot:true | updated:2026-04-30 | tokens:1800 -->
# Section Index — Intra-File Navigation Spec

Purpose: For every "fat" markdown doc (≥400 lines or ≥5k tokens), maintain a sidecar `<file>.INDEX.md` mapping H1/H2/H3 headings to anchor slugs, line ranges, line counts, and token estimates. The agent reads the **index only** (≈100–300 tokens) instead of the full doc (≥5k tokens) and pulls only the section it needs via `Read(offset, limit)` or `cos_doc_section`.

Read when: adding a long-form doc, building a new MCP tool that consumes a fat doc, debugging why an agent burned 8k tokens reading a single file.
Skip when: editing any doc under 400 lines — frontmatter + the directory's `00-index.md` already cover it.
Read next: [hooks-reference.md](hooks-reference.md), [retrieval-routing.md](retrieval-routing.md), [docs-system.md](../governance/docs-system.md).

## Why a sidecar, not in-place TOC

In-place TOCs decay every edit (drift), pollute the body the agent reads when it *does* need a section, and force a full read just to discover the structure. Sidecar `.INDEX.md`:

- **Stable** — a hook regenerates on every Write/Edit (debounced 5s).
- **Cheap** — index is ≈4% of the doc (target: ≤300 tokens for a 7k-token doc).
- **Composable** — same `<!-- BEGIN auto-index --> … <!-- END auto-index -->` fence as `00-index.md`, so hand-authored prose above survives regen.

## File layout

`docs/foo/big-doc.md` (≥400 lines) → `docs/foo/big-doc.INDEX.md` is auto-created next to it.

## INDEX.md contract

```
<!-- domain:<inherited> | layer:index | ssot:ref | updated:YYYY-MM-DD | parent:big-doc.md -->
# big-doc.md — Section Index

> Source: `big-doc.md` (3090 lines, ≈170 KB, ≈42k tokens)
> Read the section you need via `cos_doc_section("docs/foo/big-doc.md", "<slug>")`
> or `Read(file, offset, limit)`.

## Sections

| Lvl | Title | Slug | Start | End | Lines | ≈Tokens |
|-----|-------|------|------:|----:|------:|--------:|
| H1  | …     | …    | 1     | 4   | 4     | 80      |
| H2  | …     | …    | 5     | 19  | 15    | 320     |
| …   |       |      |       |     |       |         |

## Keyword → Section

- pet/profile/breed → §2.1 (`pet-profile-management`)
- …

## Giant sections

> ⚠️ `recommended-directory-tree` (75–2296, 2222 lines, ≈45k tokens). DO NOT read whole. Grep inside, then read ±50 lines.
```

## Slug rules

- ASCII-lower, spaces → `-`, strip punctuation except `-`.
- Suffix `-2`, `-3` on collisions (in document order).
- Stable across edits **as long as the heading text doesn't change**. Renaming a heading is a breaking change for anyone who linked to the slug — handled like a code rename (graph_os pick it up via `cos_graph_rename_plan`).

## Line range freshness

Line ranges drift on every edit. The hook regenerates them on every Write/Edit, debounced 5s per file. Worst-case stale range = one debounce window. Agents reading via `cos_doc_section(path, slug)` always get a fresh range because the tool re-reads the INDEX file.

## Token estimate

`max(1, len(section_text) // 4)` — same formula as `_shared.ok()` so budgets compose. A token estimate ≥3000 in the index is the agent's signal to grep first, read second.

## Threshold for index generation

A `.md` file gets an INDEX iff:

- `wc -l ≥ 400`, **or**
- `len(content) // 4 ≥ 5000` (token estimate), **or**
- frontmatter `force_index: true`.

Files below the threshold rely on `cos_doc_header` + the directory's `00-index.md`.

## Keyword map source

In priority order:

1. Frontmatter `keywords:` array (curated; wins over heuristics).
2. Heuristic: per-section TF-IDF over the doc's vocabulary, top-3 terms (>2 chars, not in stoplist), excluding terms already in the heading.
3. Empty — table is omitted entirely if both yield nothing.

## MCP tool — `cos_doc_section`

```
cos_doc_section(path: str, slug: str = "", section: str = "", with_body: bool = True) -> envelope
```

- Resolves `<file>.INDEX.md` → finds row by slug (preferred) or fuzzy section title.
- Returns `{path, slug, title, start, end, lines, token_estimate, body?}`.
- `with_body=False` is the cheap recon mode (≈40 tokens out).
- Path-traversal guarded (must stay inside project root).
- Fail categories: `not_found` (no INDEX or slug), `validation` (bad path), `permission` (escape).

## Hook — `auto-regen-section-index.sh`

PostToolUse Write|Edit on `*.md` (excluding `*.INDEX.md` and `00-index.md`). Decides:

1. If file ≥ threshold → spawn background regen of the sidecar.
2. If file < threshold AND sidecar exists → leave it (manual delete only — never auto-delete in case the threshold drop is temporary).

Debounce 5s per file. Fire-and-forget. Errors → `$COS_STATE_DIR/.section-index-errors.log` (bounded 200 lines). Same skeleton as `auto-regen-doc-index.sh`.

## Personas & scenarios

| Persona | Scenario | Without section index | With section index |
|---|---|---|---|
| Codex agent (no PostToolUse) | Asks "what does §5.2 require?" | Reads 3090-line doc → 42k tokens, blows context | Reads INDEX (≈300 tokens) → calls `cos_doc_section(slug="day-1-database-requirements")` → 24-line slice (≈480 tokens). 99% saving. |
| Claude implementing feature | Needs PRD §2.5 walk-tracking specs | Full PRD read, then mistakenly recalls competing §2.6 because both fetched together | Index → only §2.5 → cleaner context, lower cross-section bleed |
| Reviewer | Audits compliance against §6 Security | Reads everything to find §6 | INDEX → §6 (lines 722–743, 22 lines) directly |
| New maintainer onboarding | "How does Mocha bill?" | Greps blindly | Keyword map: `subscription/billing → §2.13` → direct |
| Refactor (rename a heading) | Heading "Pet Profile Management" → "Pet Profiles" | INDEX slug changes silently; downstream references break | `cos_doc_section` returns `not_found` → agent runs `cos_graph_rename_plan` (existing tool) to find dead links |
| Hub web UI | Renders nav | Falls back to `cos_doc_header` (no body shape) | Full nav tree from INDEX, click anchors land at byte offset |

## Anti-patterns

- ❌ Generating INDEX for files <400 lines — overhead > benefit.
- ❌ In-place TOC inside the body — drifts, doubles read cost.
- ❌ Hand-editing `<!-- BEGIN auto-index --> … <!-- END auto-index -->` block — gets clobbered next regen. Edit the prose **outside** the fence.
- ❌ Using line range as a stable identifier — slug is stable, line range is fresh-but-volatile.
- ❌ Embedding the full body in the INDEX — defeats the saving.

## Acceptance

- A doc ≥400 lines edited → its `<file>.INDEX.md` exists or is updated within ≤6 s of the edit.
- `cos_doc_section(path, slug)` returns the body slice for a known slug in <50 ms (filesystem cache warm).
- Index size ≤ 5% of the doc body for any doc up to 5000 lines.
- Slug stability: editing body without renaming a heading does NOT change any slug.
- Sub-threshold doc → no INDEX file is created on Write/Edit.
- Removing a heading → its slug disappears from INDEX on next regen.
