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

## Header is load-bearing (why it matters)

The exact header fields and the navigation contract are **owned by
[docs-system.md](../../../../docs/governance/docs-system.md)** — do not memorize
a second copy. The craft point: the header is not decoration. `regen_doc_index.py`
parses the `<!-- … -->` comment, so a malformed one makes the doc invisible to
its `00-index.md`; the `Purpose/Read-when/Skip-when` block tells the *agent*
whether to open the doc before spending tokens. Get either wrong and the doc
exists but no one finds it.

## Skeletons — start from the canonical template

Don't hand-build a layer's structure — every layer has a co-shipping template:
[playbook-template.md](../../../../docs/governance/_templates/playbook-template.md),
[task-detail.md](../../../../docs/governance/_templates/task-detail.md),
[runbook-template.md](../../../../docs/governance/_templates/runbook-template.md),
[post-mortem-template.md](../../../../docs/governance/_templates/post-mortem-template.md).
Copy the template, then apply the craft here. The craft the templates *don't*
carry: keep each section one altitude (a playbook sequences, it doesn't exhaust),
and let the verification block name the exact commands that prove done.

## Splitting vs sectioning

Add a section to an existing doc when the topic shares the doc's scope. Create a
new doc only when the scope genuinely differs *and* a reader would look for it
separately. A 2000-line doc that covers six scopes is six docs; a six-line doc
that duplicates a section of another is zero docs.
