---
name: technical-writing
tier: quality
domain: [universal]
description: Write documentation, READMEs, ADRs, runbooks, commit/PR bodies, and code comments that a reader acts on without re-reading. Use when authoring or reviewing any prose deliverable — a playbook, a spec, an API doc, a migration note, a release changelog, or an in-code comment. Enforces altitude (right level of detail), active voice, one-idea-per-section, specificity over vagueness, the coding-os doc-header + P/R/S/N navigation contract, and comments-as-failure-signal. Triggers — "write docs", "document this", "README", "ADR", "runbook", "explain in the docs", "write a comment", any `docs/**/*.md`. Pairs with clean-code (comments), task-driver (task prose), api-design (contract docs).
globs: ""
paths: []
last_reviewed: "2026-06-04"
---

# Technical Writing

Docs are the contract (Rule 0/19) — code follows prose, not the reverse. A doc that buries its point, mixes altitudes, or restates the code is worse than no doc: it costs every future reader the time to discover it's useless. This skill makes "a reader acts on it the first time" the bar.

> Scaffold a doc with the house header already correct:
> `python3 scripts/new_doc.py --layer playbook --domain BACKEND --title "Service X runbook" --root docs/playbooks`

> **The doc *system* — taxonomy, layers, naming, header rules — is governed by
> [docs/governance/docs-system.md](../../../docs/governance/docs-system.md) (SSOT).**
> This skill is the *craft* layer on top: how to write each layer *well*.

## The five craft rules

1. **Altitude — match detail to the reader's decision.** An index routes; a playbook sequences; a reference exhausts; an ADR justifies. Don't put reference-grade tables in a playbook, or hand-wave in a spec. Ask "what does the reader decide here?" and write exactly that.
2. **One idea per section.** A heading is a promise. If a section covers two things, split it. The reader scans headings first — they must predict content.
3. **Active voice, present tense, specific subject.** "The hook blocks the write" not "the write may be blocked". Name the actor.
4. **Specificity over vagueness.** "completes in <50 ms on the highest-degree hub" beats "is fast". Numbers, file paths, exact commands — never "appropriately" or "as needed".
5. **Bad→good for every rule.** Show the failure and the fix. Prose advice the reader can't anchor to an example is weak.

Full sentence/paragraph craft → [references/writing-craft.md](references/writing-craft.md).

## The coding-os doc-header + navigation contract

Every active doc opens with a machine-readable header + nav block; `regen_doc_index.py` depends on it — malformed, and the doc is invisible to its index. The **canonical field spec is owned by [docs/governance/docs-system.md](../../../docs/governance/docs-system.md)** (it ships to every project); don't carry a second copy. Or scaffold it correctly with `new_doc.py`. Shape, for orientation:

```markdown
<!-- domain:BACKEND | layer:playbook | ssot:true | updated:2026-06-04 -->
# Title

Purpose: <one line>.
Read when: <trigger>.
Skip when: <when another doc is right>.
Read next: [related](related.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)
```

The compact `> P/R/S/N` form is the same contract inside a skill. Per-layer "what good looks like" → [references/doc-anatomy.md](references/doc-anatomy.md).

## Comments — a comment is a failure signal

```python
# Wrong — restates the code, rots on the next edit
i += 1   # increment i

# Correct — explains the non-obvious WHY the code can't
i += 1   # skip the sentinel row the loader prepends (see loader.py:42)
```

Rule 12: comments by exception, not default. If a comment explains *what*, delete it and rename until the code says what. Keep comments that explain *why* — a constraint, a workaround, a non-obvious invariant. The best comment is a better name.
Clean code should be readable enough not to need comments.

## Commit & PR prose

Commit title ≤100 chars, body ≤3 lines explaining *why* (Rule 24 — enforced). Verbose audit tables, file lists, and verification logs belong in the PR description, the audit doc, or the work-log — never `git log`. A PR body carries the *what changed and why it's safe*; a commit carries the *one-line intent*.

## Anti-patterns (reject on sight)

- A wall of prose with no headings — the reader can't scan.
- "This document describes…" preamble — start with the point.
- Reference tables inside a playbook (wrong altitude) — link a reference.
- A comment that restates the line below it.
- "Should", "appropriately", "as needed", "various", "etc." carrying real meaning — be specific.
- Duplicating policy that already lives in `docs-system.md` — link it.
- A new doc when an existing one has the right scope — add a section.

## See also

- [references/writing-craft.md](references/writing-craft.md) — sentence/paragraph craft, bad→good prose.
- [references/doc-anatomy.md](references/doc-anatomy.md) — per-layer "what good looks like".
- [assets/doc-checklist.md](assets/doc-checklist.md) — the ship gate.
- [docs/governance/docs-system.md](../../../docs/governance/docs-system.md) — the doc-system SSOT (taxonomy, headers, naming).
