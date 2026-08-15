<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-08-15 -->
# Ablation Protocol — does the kernel improve output, or only token count?

Purpose: Pre-register the experiment that answers the one question the token
benchmarks cannot: whether an agent running coding-os produces *better work*, not
just cheaper retrieval. Registering the arms, the metrics, and the scoring rule
**before** any arm executes is what stops the result being chosen after the fact.
Read when: running, changing, or citing the ablation.
Skip when: the change touches only token accounting.

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Status

**Registered, not yet run.** The task-set miner and this protocol exist; no arm
has executed, and therefore no result appears here or anywhere else. When a run
happens, its numbers land in this file and nowhere earlier in the pipeline.

That order is the point. A published quality claim with no executed run is the
same defect as a savings claim measured against a strawman — the thing this whole
line of work exists to stop.

## Why the existing benchmarks cannot answer it

[third-party-token-bench.md](third-party-token-bench.md) measures the cost of one
retrieval call against the cost of grepping. [context-budget.md](context-budget.md)
measures the toll the instruction layer charges. Neither observes whether the
delivered change was *correct*. An agent can spend fewer tokens and produce worse
code; the token ledger would call that a win.

## The four arms

Each arm differs **only** in the instruction and retrieval layer. Model, model
version, sampling settings, tool allow-list, working directory, and starting
commit are identical across arms.

| Arm | Instruction layer | Graph tools | What it isolates |
|---|---|---|---|
| `raw` | none (bare agent runtime) | no | the floor |
| `graph` | none | yes | retrieval alone |
| `rules` | full `CLAUDE.md` + `.claude/rules/` | no | instruction discipline alone |
| `full` | full | yes | the shipped product |

`raw` vs `graph` isolates the graph. `raw` vs `rules` isolates the rules. If
`full` does not beat both single-lever arms, the levers interfere and that is a
finding worth publishing.

## Metrics — fixed before the first run

Primary:

1. **Completion rate** — the task's own acceptance command exits 0, run in a
   clean environment the agent never saw.
2. **Weighted cost per task** — `input + 1.25×cache_write + 0.1×cache_read +
   5×output`, the same weighting `cos doctor --tokens` uses. Read from the
   transcript, not estimated.

Secondary, reported always, never used to pick a winner:

3. Tokens per task (raw, unweighted).
4. Wall-clock per task.
5. Turns per task.
6. **Quality per dollar** — completion rate ÷ weighted cost.
7. **Completions per million tokens.**

Rules that bind the run:

- **N = 3 runs per (task, arm).** Report the median and the full spread; a single
  run of a stochastic agent is an anecdote.
- **No metric may be added after the first arm executes.** Adding one is a new
  pre-registration and a new run.
- **The acceptance command is the scorer.** No model-judged quality score, because
  a model judging an agent's output is a second uncontrolled variable.
- **Failures count.** A task the agent abandons is a completion-rate 0, not an
  excluded outlier.

## The task set

Mined from this repo's own closed tasks by `src/scripts/eval_taskset.py`, which
keeps only tasks whose acceptance criterion contains a runnable command. Each
candidate carries:

- `task_id`, and the `Outcome` line as the prompt the agent receives;
- the extracted acceptance command;
- the closing commit, and its parent as the starting state.

Mining is not selection. The emitted YAML is a **candidate list for review**: an
entry only enters the locked set once a human has confirmed the prompt is
answerable from the starting state and the command genuinely fails there. A
mined-but-unvalidated set would score tasks that were already done, which is the
eval equivalent of the truncated-envelope defect.

```bash
uv run python src/scripts/eval_taskset.py --out docs/_meta/eval-candidates.yaml
```

### What the miner actually found — and why that is its own finding

Run on 2026-08-15: **148 candidates out of 978 closed tasks** — where "closed"
means `status: complete` *or* `status: archive`, the state a completed task lands
in when it leaves the active board. (An earlier run of this miner read only
`complete` and reported 9 out of 150; it was sampling 15% of the corpus, and the
conclusion it supported was an artifact of that filter.) The 830 rejections are
tasks whose acceptance criterion is prose, plus a few with no traceable commit:
this repo's G/W/T discipline produces a *Then* clause a human can judge and a
script cannot roughly 85% of the time.

Two consequences, both worth stating plainly rather than working around:

1. **148 mined is not 148 usable.** Every entry still needs the validation step,
   and the commands that recur most (`cos doctor`, `cos init --help`, `make
   docs-lint`-adjacent checks) are exactly the ones that already pass at the
   starting commit and will be rejected. The honest expectation is that the
   validated set is a fraction of the mined one, and the number that survives is
   itself a result worth reporting.
2. **The template is the fixable half.** A *Then* that names a command is strictly
   more useful than one that describes a feeling of doneness — it is the same
   "verify by executing" rule the kernel enforces on agents, applied to the task
   template itself. Tightening it will not retroactively fix 978 closed tasks, but
   it makes the next 978 minable.

## Threats to validity, stated up front

- **The task set is this repo's own history.** It measures the kernel on the kind
  of work the kernel's author does. External validity needs someone else's repo,
  and that is a design-partner problem, not a scripting one.
- **`rules` and `full` see instructions written by the same person who wrote the
  tasks.** Some of the lift may be familiarity rather than discipline.
- **Starting-state contamination.** If the parent commit already contains part of
  the work, the task is too easy; the human validation step exists to catch that.
- **Cost of a full run is real** — 4 arms × N tasks × 3 repetitions. Sample size
  will be reported, and an underpowered result will be labelled directional.

## See also

- [third-party-token-bench.md](third-party-token-bench.md) — retrieval cost.
- [context-budget.md](context-budget.md) — instruction cost.
- `src/cli/doctor_tokens.py` — the weighting used for cost per task.
