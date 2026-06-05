<!-- domain:DOCS | layer:reference | ssot:true | updated:2026-06-04 -->
# Writing Craft — Sentences, Paragraphs, Structure

> P: The sentence- and paragraph-level moves that make technical prose act-on-able the first read.
> R: Drafting or editing any doc, README, ADR, or long comment.
> S: Choosing which doc layer to write — see [doc-anatomy.md](doc-anatomy.md).
> N: [SKILL.md](../SKILL.md), [doc-checklist.md](../assets/doc-checklist.md)

> Nav: [Skill](../SKILL.md)

## Structure — newspaper, not novel

Lead with the conclusion; expand below. The reader who stops after the first paragraph should still have the answer. Detail descends: point → why → how → edge cases.

```markdown
# Wrong — buries the lede
This document describes the various considerations that were taken into
account when designing the caching layer, including several trade-offs...

# Correct — point first
Cache reads in Redis with a 60s TTL; writes invalidate the key. Below: why
60s, and the two cases where you must bypass the cache.
```

## Sentences — active, present, specific

| Weak | Strong |
|---|---|
| "The request may be rejected by the validator." | "The validator rejects the request when `amount` is negative." |
| "Performance was improved." | "p95 latency dropped from 240 ms to 90 ms." |
| "This should be handled appropriately." | "Retry twice with exponential backoff, then dead-letter." |
| "There are several ways to do this." | "Three ways; use the first unless you need streaming." |

Cut hedges (*may, might, could, generally, typically*) unless the uncertainty is the point. Cut intensifiers (*very, really, quite*). Name the subject — passive voice hides who acts.

## Paragraphs — one idea, front-loaded

First sentence states the idea; the rest supports it. If you can't summarize a paragraph in its first sentence, it holds two ideas — split it. Three sentences that each say the same thing collapse to one.

## Lists vs prose vs tables

- **Prose** — reasoning, a "why", a narrative the reader follows once.
- **List** — steps in order, or a set of peers (≤7; past that, a table).
- **Table** — comparisons across a fixed set of dimensions. If every row repeats a column, that column is prose.

## Specificity checklist

- Every "fast / slow / large / small" → a number or it's deleted.
- Every "the file / the function / the config" → a path or symbol.
- Every "should" → either "must" (a rule) or "consider" (a suggestion) — pick.
- Every claim about behaviour → traceable to a file, a test, or a measurement.

## Editing pass (do this before shipping)

1. Delete the first sentence if it's preamble ("This section covers…").
2. Read each heading in order — do they tell the story alone? If not, rename.
3. Find every hedge/intensifier — justify or cut.
4. Find every vague noun — replace with the path/symbol.
5. Find every code-adjacent claim — verify against the code, not memory.
