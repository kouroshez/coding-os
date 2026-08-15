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

**Registered, not yet run.** No arm has executed, and therefore no result appears
here or anywhere else. When a run happens, its numbers land in this file and
nowhere earlier in the pipeline.

Revised 2026-08-15: the substrate moved from this repo's mined task history to
SWE-bench Verified, after measuring that the mined acceptance commands cannot
discriminate. Nothing had run under the old design, so nothing is retracted —
this is a pre-registration replacing a pre-registration.

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
version, sampling settings, tool allow-list, container image, and starting commit
are identical across arms.

| Arm | Instruction layer | Graph tools | What it isolates |
|---|---|---|---|
| `raw` | none — stock mini-SWE-agent | no | the floor |
| `graph` | none | yes | retrieval alone |
| `rules` | full `CLAUDE.md` + `.claude/rules/` | no | instruction discipline alone |
| `full` | full | yes | the shipped product |

`raw` vs `graph` isolates the graph. `raw` vs `rules` isolates the rules. If
`full` does not beat both single-lever arms, the levers interfere and that is a
finding worth publishing.

`raw` is [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) on its
published bash-only configuration, unmodified — the same control the Verified
leaderboard uses to compare language models, whose maintainers state they do not
tune it for score. Adopting someone else's floor is the point: a floor this
project defines is a floor this project can flatter.

## What may and may not be published

Verified is saturated and contamination-prone; an absolute score on it ranks
nothing. **The only defensible statistic is the between-arm delta on one model,
run in one window, with its spread.** "coding-os scores X%" is not a claim this
protocol can support and must not be made from its output. "With model M on date
D, `full` resolved N more instances than `raw`, 95% CI [a, b]" is.

## Pilot before fleet

Run **50 instances × 2 arms (`raw`, `full`) × 3 repetitions = 300 runs** first.
The middle arms only earn their cost if the endpoints separate: if `full` − `raw`
sits inside the noise at n=50, decomposing that null into `graph` and `rules` will
not find a signal either, and the null is the result. Publish it either way — a
pre-registration whose negative outcome goes unpublished is not a
pre-registration.

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

## The task set — SWE-bench Verified, not this repo's history

**Substrate: [SWE-bench Verified](https://www.swebench.com/verified.html)** — 500
human-filtered instances, each carrying `FAIL_TO_PASS` and `PASS_TO_PASS` test
sets written by the upstream maintainers in the same PR that fixed the issue, and
each running in its own container. Four properties this repo's own history cannot
supply:

| Requirement | Why mining this repo fails it |
|---|---|
| The scorer must discriminate | see the measurement below |
| Task author ≠ instruction author | the same person wrote the rules and the tasks |
| Arms must not fight the git guards | replaying a commit needs a checkout `branch-guard` blocks |
| A published floor | mini-SWE-agent is the community's accepted control |

### Why the home-grown set was abandoned — the measurement

`src/scripts/eval_taskset.py` mined **148 candidates from 978 closed tasks** on
2026-08-15. Those 148 carry only **58 distinct acceptance commands**, and the head
of the distribution is fatal:

| Count | Command |
|---:|---|
| 27 | `make ui-build` |
| 15 | `uv run pytest tests/test_cli.py -q` |
| 11 | `cos init` |
| 10 | `cos doctor` |
| 7 | `make regen-rules` |

70 of 148 (**47%**) are suite-level or idempotent tool invocations that pass at the
starting commit, so they cannot separate a solved task from an untouched one. The
remainder mostly name a test that the task's own commit *added* — so the scorer
reduces to "did the agent guess the author's test-file name", which is not a
measure of correctness either. No amount of validation rescues a set whose
acceptance criteria are not independent of the solution.

The miner and its output stay in the repo as evidence for that conclusion, not as
an input to a run.

### The one finding worth keeping from it

A *Then* clause that names a command is strictly more useful than one describing a
feeling of doneness — the "verify by executing" rule applied to the task template
itself. It will not retroactively fix 978 closed tasks, and after this measurement
it is a task-hygiene improvement, not an eval strategy.

## Execution environment (non-negotiable)

Every arm runs against a **throwaway clone**, never this working tree. Replaying a
historical commit requires `git checkout <sha>`, which `branch-guard.sh` BLOCKs in
trunk mode, and Rule 21 forbids worktrees — a protocol that ignores that is a
protocol that cannot run. SWE-bench's per-instance containers satisfy this by
construction; any local arm must clone to a temp dir and be deleted after.

## Threats to validity, stated up front

- **Verified is contaminated and saturated.** Its instances predate most current
  models' training cutoffs. This is survivable only because every arm shares the
  contamination equally — it inflates the floor, not the delta — and it is exactly
  why no absolute score may be quoted.
- **Verified is Python, and mostly library code.** A gain here does not transfer
  to the WordPress or Next.js consumers this kernel also ships to. Reporting it as
  a general result would repeat the strawman-baseline error in a new place.
- **The instruction layer was written for this repo, not for django or sympy.**
  Stack rules that carry the most specific guidance will be absent or irrelevant,
  so the measured delta is a *lower* bound on a matched-stack project and says
  nothing about the upper one.
- **Cost of a full run is real** — 4 arms × N instances × 3 repetitions, each a
  container plus a model session. Sample size will be reported, and an
  underpowered result will be labelled directional.
- **`n=50` detects only a large effect.** A null at pilot scale is "no effect this
  design can see", not "no effect".

## See also

- [third-party-token-bench.md](third-party-token-bench.md) — retrieval cost.
- [context-budget.md](context-budget.md) — instruction cost.
- `src/cli/doctor_tokens.py` — the weighting used for cost per task.
