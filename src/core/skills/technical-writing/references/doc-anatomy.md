<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-06-04 -->
# Doc Anatomy — What Good Looks Like Per Layer

> P: How to write each coding-os doc layer *well* — the craft per taxonomy slot.
> R: Creating or reviewing a doc and deciding what belongs in it.
> S: The taxonomy/naming *rules* themselves — those are governed by docs-system.md.
> N: [SKILL.md](../SKILL.md), [writing-craft.md](writing-craft.md), [docs-system.md](../../../../docs/governance/docs-system.md)

> Nav: [Skill](../SKILL.md)

The *rules* (header fields, file naming, where a layer lives) are SSOT in
[docs-system.md](../../../../docs/governance/docs-system.md). This file is the
*craft*: given the layer, what makes it good.

## By layer

| Layer | Job | Good looks like | Smell |
|---|---|---|---|
| `index` | route only | one-line entries, no content | prose paragraphs, duplicated content |
| `playbook` | sequence a task | ordered steps + a verification block + read-selection guide | reference-grade tables inline |
| `spec` | define requirements | testable statements ("X MUST Y"), acceptance criteria | aspirational prose, no acceptance |
| `policy` | govern a process | the rule + the why + enforcement pointer | a rule with no rationale |
| `reference` | exhaust a topic | complete tables, every edge case, dated | half-coverage; a "see code" hand-wave |
| `adr` | justify a decision | context → options → decision → consequences, immutable | edited after the fact; no alternatives |
| `task` | log one work item | pointer to specs, not inlined content (Rule 14) | a spec pasted into the task |

## Header is load-bearing

The `<!-- domain | layer | ssot:true | updated:YYYY-MM-DD -->` comment is parsed by
`regen_doc_index.py` — a missing or malformed header makes the doc invisible to
its `00-index.md`. The `Purpose / Read when / Skip when / Read next` block (or
the compact `> P/R/S/N` form inside skills) tells the *agent* whether to open
the doc before spending tokens on it. Both are mandatory, not decoration.

## Playbook skeleton (the most common authored layer)

```markdown
<!-- domain:X | layer:playbook | ssot:true | updated:YYYY-MM-DD -->
# Playbook — <verb the task>

> P: <one line> · R: <when> · S: <when not> · N: <links>
> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## When to use this playbook
## The model            <- the mental model, briefly
## Steps                <- ordered, each step = one action + its verify
## Verification         <- the exact commands that prove done
## Anti-patterns        <- what to reject on sight
## See also
```

## Splitting vs sectioning

Add a section to an existing doc when the topic shares the doc's scope. Create a
new doc only when the scope genuinely differs *and* a reader would look for it
separately. A 2000-line doc that covers six scopes is six docs; a six-line doc
that duplicates a section of another is zero docs.
