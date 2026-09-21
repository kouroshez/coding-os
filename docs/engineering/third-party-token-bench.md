<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-15 -->
# Third-Party Token-Cost Benchmark — graph envelope vs a graph-less agent

Purpose: Measure, reproducibly and on public repos, what a `cos_graph_*` envelope
costs against what an agent without the graph would spend answering the same
structural question — and publish the result including the cases where the graph
loses.
Read when: quoting a token number, changing the harness, or evaluating whether the
graph layer is worth its context cost.
Skip when: the change touches neither the bench nor a published figure.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## How to run (no coding-os setup beyond a clone)

```bash
git clone https://github.com/kouroshez/coding-os && cd coding-os
uv run --extra graph_os python src/core/graph_os/bench/third_party.py \
    --repo https://github.com/psf/requests --ref v2.32.5 --queries 10
# any local checkout, and any of the three baselines:
uv run --extra graph_os python src/core/graph_os/bench/third_party.py \
    --repo ~/src/fastapi --baseline read-all
# add jedi and the same run also grades accuracy (see below):
uv run --extra graph_os --with jedi python src/core/graph_os/bench/third_party.py \
    --repo ~/src/fastapi --queries 6
```

Output: a JSON report (`--out FILE` or stdout) with raw per-probe numbers plus a
per-workflow summary, and a marker-prefixed summary on stderr.

## Choosing a baseline is the whole ballgame

A savings percentage is meaningless without naming what it is measured against, and
an earlier version of this document quoted only the most flattering option. The
harness now implements three and defaults to the middle one:

| `--baseline` | What the graph-less agent does | Role |
|---|---|---|
| `grep-only` | one grep; act on the match lines | **floor** — under-counts; match lines rarely settle "does this caller break" |
| `grep-windows` *(default)* | grep, then ±40 lines around the matches in the 5 highest-hit files | **what a competent agent actually does** |
| `read-all` | grep, then read every matching file end to end | **ceiling** — quoting this alone is how a benchmark produces a number nobody believes |

`grep-windows` is the number to quote. `read-all` is kept because it bounds the
worst case an agent can talk itself into, not because it is representative.

## Never score a truncated envelope

The graph reports its own incompleteness, and the first version of this harness
ignored it. That produced the defect this section exists to prevent: the README
published "`init_db` — 508 impacted, 7,962 tokens, 98.3% saved". At the default
`visit_limit=500` that envelope carries `walk_truncated=true`, and 508 is an
artifact of the cap. Raising the budget gives the real figure: **1,494**. The
published row compared a *partial* graph answer against a *complete* manual one.

The harness now decides completeness empirically rather than from a flag, because
the flags cannot distinguish the two causes on their own:

1. Call the tool at `visit_limit`/`limit` 500, then 2,000, 10,000, 50,000.
2. Stop when the reported total stops growing **and** `walk_truncated` is false.
3. Classify the settled answer:
   - **complete** — every row returned;
   - **count+sample** — the count is trustworthy and the rows are a ranked subset
     ("1,494 impacted, here are the 60 riskiest"), which is a legitimate answer as
     long as the report says so;
   - **incomplete** — still growing or still capped at the widest budget. **Never
     scored**; counted separately in the summary.

`tests/…/test_bench_honesty.py` pins both behaviours, and the widening test is red
against the pre-fix single-call code.

## Methodology

1. **Corpus** — every `*.py` file under the repo root except a denylist of
   directory names (`.git`, `.hg`, virtualenvs, `node_modules`, `__pycache__`,
   `.tox`, `.mypy_cache`, `build`, `dist`), read once into memory. Indexed with
   the same extractors and SQLite backend every consumer uses.

   This is a **denylist walk, not `git ls-files`** — the distinction matters
   and this doc used to get it wrong. A gitignored directory the denylist does
   not name is indexed: this repo carries 938 build artefacts under
   `build/lib/` that are byte-copies of its own source, and until `build` was
   added they were 27% of the corpus. A class defined twice splits its own
   degree, so the highest-degree probes — the ones §2 selects — resolved into
   the copy. Any repo you point this at should be checked for the same shape
   before its numbers are published.
2. **Probes** — the `--queries N` highest-degree function/class symbols,
   deduplicated by label so one symbol cannot be double-weighted in the median.
   Selection is deterministic for a given repo state.
3. **Graph cost** — the settled envelope's `meta.tokens_estimated` (chars/4, the
   same estimator production envelopes report).
4. **Baseline cost** — chars/4 of whatever the chosen baseline reads.
5. **Savings** — per probe, `1 − graph/baseline`; the summary reports median, mean
   and **min**, plus how many probes were skipped as incomplete.
6. **Break-even** — how many structural queries it takes for the median per-query
   saving to repay the always-on instruction cost
   ([context-budget.md](context-budget.md), default 13,158 tokens). This is a
   deliberately harsh test: it charges the graph for the entire rules layer, most
   of which does other things.

## Accuracy — precision is sound, recall is a lower bound

A cheaper retrieval is only better if it is still right, and until 2026-09-20 the
harness could not tell the difference. It now grades the `references` workflow
against [jedi](https://github.com/davidhalter/jedi), which infers types rather
than walking syntax, so it is not blind in the same places the extractor is.
Grading a syntax walk against a second syntax walk would have measured agreement
and called it accuracy.

The unit is a **reference location**, `(repo-relative path, line)` — the only
unit both sides express. Wherever the two name the same file their line numbers
agree exactly, measured, so a miss is a real miss and not an off-by-one.

### jedi adjudicates; it does not enumerate

`get_references(scope="project")` is **not symmetric**, measured on this repo:
asked from the definition of `GraphNode` it returned 155 references across 31
files and omitted `extractors/_php_symbols.py` entirely; asked from line 79 of
that omitted file it returned 163 across 32 files, the definition included. An
enumerator that misses locations it can itself resolve is not ground truth, and
scoring against it directly bills jedi's blind spots to the graph.

So each location the graph claims is resolved individually with
`goto(follow_imports=True)` and checked against the probe's definition — a
per-site decision with no enumeration in it, at roughly 32 ms per site.

- **Precision is sound.** Every claimed site is adjudicated one at a time.
- **Recall is a lower bound.** Its denominator is jedi's definition-seeded
  enumeration unioned with the graph's confirmed sites, and that enumeration is
  known to be incomplete. A location neither side names is counted by neither,
  so true recall can only be higher than the figure reported.

### Grade the graph's knowledge, not the token trimmer's page

The first version of this measurement reported a median recall of 0.297. It was
wrong, and wrong in the direction that matters: the envelope had returned 60 of
a known 185 references for `GraphNode` because the token-budget trimmer cut the
row list, so the number described the page size rather than the extractor — and
a *tighter* budget would have read as a worse graph, which is the exact
"cheaper looks better" confusion this section exists to remove. Grading now
reads every edge the graph holds under the tool's own kind defaults. The token
columns still come from the trimmed envelope, because that is what an agent
actually pays.

### Measured 2026-09-20 — coding-os, 6 probes, 2,483 files

| Figure | Value |
|---|---|
| precision | **1.00** — every location the graph claimed resolved to the probe's definition |
| recall (median) | 0.50 |
| recall (min) | 0.04 — `DoctorReport`, where the graph holds 5 of 121 known locations |

The 474 locations the graph missed across those six probes break down as 215
type annotations (45%), 139 imports (29%), 93 calls or constructions (20%) and
27 other. Annotations are a class the extractor does not model at all; the
imports and calls are a genuine gap and the reason the min column is worth
reading before the median.

Precision at 1.00 says the graph invents nothing. Recall at 0.50 says it sees
about half of what a type-inferring tool sees. Both belong next to a savings
figure, because only the pair of them answers whether a cheaper answer was also
a correct one.

There is deliberately **no dynamic-dispatch bucket**, though the design called
for one on the theory that dispatch defeats the oracle as well as the graph. Two
measurements sent it back: the probe selector samples module-level functions and
classes, never methods, so no probe in a run is dispatch-bound to begin with; and
the gap that does exist is annotations, imports and direct calls, none of which
dispatch explains. The confound worth bucketing turned out to be jedi's own
enumeration asymmetry, which `no_oracle` and the adjudication step already
handle. Add the bucket if methods ever enter probe selection — not before.

## Published runs

<!-- BEGIN bench-results -->
Measured 2026-08-15, `coding-os` 0.3.19. Median savings over the highest-degree
symbols, with the **worst single probe** in brackets. Public repos ran
`--queries 10`; this repo ran `--queries 8`.

### `grep-windows` — the number to quote

| Repo | `.py` files | `references` | `impact` (d=3) | `rename_plan` |
|---|---:|---:|---:|---:|
| psf/requests @ v2.32.5 | 36 | 77.7% (42) | 24.2% (−54) | 74.8% (44) |
| fastapi/fastapi @ 0.116.1 | 1,129 | 79.5% (−3) | **−6.8%** (−86) | 82.4% (11) |
| django/django @ 5.2 | 2,818 | 76.8% (50) | 70.8% (18) | 77.1% (51) |
| coding-os (this repo) ⚠️ | 3,317 | 79.7% (66) | 74.0% (65) | 79.7% (66) |

> ⚠️ **The coding-os row is measured on a contaminated corpus and has not been
> re-run.** Its 3,317 files included ~940 gitignored copies of the repo's own
> source under `build/lib/`, so its probes were selected from a tree that was
> partly a duplicate of itself. `build`/`dist` are now excluded (the same walk
> counts 2,483 files today), which changes both the probe selection and the
> grep baseline — so the row cannot simply be scaled. Re-run all three
> baselines for this repo before quoting it. The three third-party rows are
> unaffected: none of them ships a `build/` tree.

### `read-all` — the ceiling, published so nobody has to guess what we cherry-picked

| Repo | `references` | `impact` (d=3) | `rename_plan` |
|---|---:|---:|---:|
| psf/requests | 95.1% (92) | 89.4% (80) | 95.0% (92) |
| fastapi/fastapi | 99.0% (−3) | 92.7% (−86) | 98.0% (11) |
| django/django | 96.8% (76) | 96.2% (60) | 96.8% (76) |
| coding-os | 97.5% (88) | 95.9% (90) | 97.5% (88) |

### `grep-only` — the floor, where the graph mostly loses

| Repo | `references` | `impact` (d=3) | `rename_plan` |
|---|---:|---:|---:|
| psf/requests | −169.3% | −462.8% | −173.3% |
| fastapi/fastapi | 5.3% | −273.3% | 18.4% |
| django/django | −67.6% | −90.3% | −65.4% |
| coding-os | 50.2% | 32.5% | 53.1% |

### What the three tables say together

1. **`references` and `rename_plan` are a consistent 75–82% cheaper** than a
   competent grep-then-read, across repos spanning two orders of magnitude in
   size. This is the robust result and the one the graph-first rule rests on.
2. **A 3-hop `impact` is size-dependent and can lose.** +71–74% on django and
   this repo, +24% on requests, **−6.8% on fastapi** — a wide transitive envelope
   is not free. Reach for `depth=3` when the codebase is large enough that reading
   is worse; on a mid-size repo, narrow the depth or ask `references` instead.
3. **Against bare grep output the graph usually costs more.** If match lines
   answer the question, they are the cheaper tool. What the extra tokens buy is a
   `total_count` and typed edges — grep never tells you what it missed, and the
   agent cannot tell a complete grep from a partial one.

The honest one-line version: *the graph is not the cheapest way to get some
callers; it is a much cheaper way to get **all** of them.*
<!-- END bench-results -->

## Honest limits

- **Accuracy is measured for `references` only, and only with jedi installed.**
  `impact` and `rename_plan` carry no accuracy figure at all: one walks
  transitively and the other includes docs and string literals, so neither
  answers the question the oracle answers, and grading them against it would
  manufacture a low recall out of a definitional mismatch. The savings tables
  for those two workflows still answer only *what does the envelope cost*.
  The harness has never been run against CodeRAG-Bench, CoIR-Retrieval,
  ContextBench or SWE-Explore-Bench — all four score a chunk, and a caller is a
  node, so none of them answers this question either.
- chars/4 is a heuristic, not a tokenizer. Both sides use the same estimator, so the
  *ratio* is meaningful even where absolutes drift.
- **Probe selection favours the graph.** The highest-degree symbols are exactly the
  ones grep handles worst. A question about a two-caller helper saves far less, and
  the `min` column is the honest view of that spread.
- The `grep-windows` window (±40 lines, 5 files) is a model of agent behaviour, not
  a recording of it. A more disciplined agent reads less and the savings shrink
  toward the `grep-only` row; a less disciplined one drifts toward `read-all`.
- Savings scale with corpus size. On a small repo a full read is already cheap, so
  the graph has less to beat.
- `--ref` pins a tag/branch; record the ref alongside any published number.

## See also

- [context-budget.md](context-budget.md) — the cost side of the ledger.
- [graph_os-queries.md](graph_os-queries.md) — query routing + freshness.
- `src/core/graph_os/bench/_baselines.py` · `_coverage.py` — the two guards.
- `.claude/rules/meta-graph-first.md` — the rule these numbers back.
