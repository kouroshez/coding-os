<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-08 -->
# Third-Party Token-Cost Benchmark — graph envelope vs grep + read

Reproducible, third-party-runnable measurement of the claim behind the
graph-first rule: answering a structural question through a `cos_graph_*`
envelope costs a fraction of the tokens an agent spends grepping the repo
and reading every matching file. The numbers published in the README come
from **this** harness run on **public repos**, not from coding-os itself.

## How to run (no coding-os setup beyond a clone)

```bash
git clone https://github.com/kouroshez/coding-os && cd coding-os
uv run --extra graph_os python src/core/graph_os/bench/third_party.py \
    --repo https://github.com/psf/requests --ref v2.32.3 --queries 10
# or any local checkout:
uv run --extra graph_os python src/core/graph_os/bench/third_party.py --repo ~/src/fastapi
```

Output: a JSON report (`--out FILE` or stdout) with raw per-probe numbers
plus a per-workflow summary, and a human-readable table on stderr.

## Methodology

1. **Corpus** — the target repo's tracked `*.py` files (skip `.git`,
   virtualenvs, `node_modules`). The repo is indexed with the same
   extractors + SQLite backend every coding-os consumer uses
   (`run_benchmark` → `bulk_upsert` → stub/import linking).
2. **Probes** — the `--queries N` highest-degree function/class symbols
   (most-referenced = the symbols an agent most plausibly asks about).
   Probe selection is deterministic for a given repo state.
3. **Graph cost** — for each probe and workflow the harness calls the real
   tool (`cos_graph_references`, `cos_graph_impact`,
   `cos_graph_rename_plan`) and takes the envelope's
   `meta.tokens_estimated` (chars/4 heuristic — the same estimator used
   in production envelopes; no second tokenizer).
4. **Baseline cost** — what a graph-less agent pays for the same
   question: substring-grep the symbol name across the corpus, then read
   **every file that matches** in full. Baseline tokens = chars/4 of the
   concatenated matching files. This mirrors the documented fallback
   workflow ("grep + read every matching file"), not a strawman: the
   agent cannot know which matches matter without reading them.
5. **Savings** — per probe/workflow: `1 − graph/naive`. The summary
   reports the median and mean across probes plus the min (worst case).

## Honest limits

- chars/4 is a heuristic, not a tokenizer; both sides use the same
  estimator so the *ratio* is meaningful even where absolutes drift.
- The baseline reads whole files; a skilled human might read fragments.
  Fragment-reading agents still pay for grep output + orientation reads —
  the baseline approximates the median agent, not the best human.
- `--ref` pins a tag/branch (shallow clone); record the ref alongside any
  published numbers so runs are comparable.
- Savings scale with repo size: tiny repos show smaller ratios because a
  full read is already cheap.

## Published runs (median savings across 10 highest-degree probes)

| Repo | Ref | .py files | Nodes/Edges | references | impact (d=3) | rename_plan |
| --- | --- | --- | --- | --- | --- | --- |
| psf/requests | v2.32.5 | 36 | 2,919 / 5,137 | 94.5% | 88.4% | 94.4% |
| fastapi/fastapi | 0.116.1 | 1,129 | 43,859 / 58,190 | 99.7% | 98.6% | 99.1% |
| django/django | 5.2 | 2,818 | 166,803 / 313,782 | 96.4% | 95.9% | 96.5% |

Worst single probe observed: 53.9% (impact on django). Median savings hold
above 95% on every repo measured, but Django shows the spread widening rather
than the median falling — its mean sits 5.5 points under its median, against
1 point on requests, because a 167k-node graph contains far more genuinely
hub-like symbols whose impact envelope is legitimately large. The rule still
holds (savings grow with corpus size: requests 94.5% → fastapi 99.7%); what
does not hold is reading the median as a floor. Index cost: 791 ms (requests),
10.5 s (fastapi), 52.2 s (django), one-off per checkout.

(Regenerate with the commands above; update this table + the ref column
in the same commit as any harness change that shifts the numbers.)

## See also

- [graph_os-queries.md](graph_os-queries.md) — query routing + freshness.
- `src/core/graph_os/bench/token_cost.py` — synthetic-corpus sibling
  (regression gate); this harness is the external-validity sibling.
- `.claude/rules/meta-graph-first.md` — the rule these numbers back.
