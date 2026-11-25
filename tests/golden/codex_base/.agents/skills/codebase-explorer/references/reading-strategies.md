<!-- domain:UNIVERSAL | layer:reference | ssot:true | updated:2026-06-04 -->
# Code-Reading Strategies

> P: Understand an unfamiliar feature or data flow efficiently, top-down then drill.
> R: "How does X work?" — tracing a feature, following a flow, learning a domain.
> S: Symbol-precise queries (callers, blast radius, rename) — that's [graph-explorer](../../graph-explorer/SKILL.md).
> N: [SKILL.md](../SKILL.md), [reading-checklist.md](../assets/reading-checklist.md)

> Nav: [Skill](../SKILL.md)

## Read top-down, not line-by-line

1. **Entry point first** — find where the feature starts (a route, a CLI command,
   an event handler). `outline.py` on the file gives the shape in one call.
2. **Follow the call, skim the rest** — read the function on the path; skip
   sibling helpers until they're on the path.
3. **Name the data** — what's the core entity flowing through? Track its shape as
   it transforms.
4. **Note the boundaries** — where does control leave this code (DB, queue, HTTP,
   another service)? Those are the seams.

Reading every line of a 2000-line module to answer one question is the trap.
Read the *spine* of the feature, drill only where you must.

## Conceptual vs structural (pick the tool)

| Question | Tool |
|---|---|
| "how does auth work end to end?" | code-reading (this skill) + `outline.py` |
| "who calls `validate_token`?" | [graph-explorer](../../graph-explorer/SKILL.md) `references` |
| "what breaks if I change this?" | graph-explorer `impact` |
| "where is the string 'X' used?" | [search](../../search/SKILL.md) (grep) |

This skill reads code as prose (narrative understanding); graph-explorer queries
it as a graph (precise symbol relationships). They are complementary — start
conceptual, switch to the graph when you need exact call-sites.

## Build a mental model, write it down

After tracing, state the model in two sentences ("a request hits the router →
the service validates via the policy layer → the repository persists"). If you
can't, you haven't understood it yet — find the gap. A model written into a doc
([technical-writing](../../technical-writing/SKILL.md)) saves the next reader the
trace.

## Orientation moves

- `outline.py src/foo.py` — the file's classes/functions at a glance.
- Read the tests — they show intended usage and edge cases, often clearer than
  the implementation.
- `git log -p --follow <file>` — how it got this way; the *why* behind odd code.
- README / docs first — the author may have already explained it.
