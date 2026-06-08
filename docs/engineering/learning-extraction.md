<!-- domain:CORE | layer:engineering | ssot:true | updated:2026-06-07 -->
# Learning Extraction

Purpose: Canonical contract for what `cos_learn_extract` produces — the
definition of a *learned pattern*, the signals it mines, and the rule that
keeps statistics from masquerading as lessons. The producer is
`src/core/thinking_os/tools/learning.py`; the consumers are the digest
(`thinking_os/digest.py`), recall (`cos_learn_suggest`), and the Hub Memory
page (`web/ui/src/pages/MemoryPage.tsx`).
Read when: editing `learning.py`, `digest.py`, the Memory page, or any code
that reads/writes `learned_patterns`.
Skip when: working on raw observation capture (see capture.py) or the cron
wiring (see [scheduled-jobs.md](scheduled-jobs.md)).
Read next: [scheduled-jobs.md](scheduled-jobs.md), [hub-architecture.md](hub-architecture.md)

> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)

## Why this contract exists

The learning loop was minting **statistics** and calling them **learnings**.
With a success-only task history (`task_outcomes` was 192/192 `success`), the
only patterns it could produce were tautologies — `INFRA domain succeeds at
100% (177/177) — reliable baseline`, `Skill set '…' correlates with success`.
After a year and millions of tokens the agent had "learned" four such rows,
none of which is a lesson. Meanwhile the genuinely useful signal — the
hook BLOCKs, tool failures, completion gaps, and rework→fix corrections every
session emits — was captured into `observations` but **never read** by
extraction.

A learned pattern must answer *"what did I do wrong, and what should I do
instead?"* — not *"what is my success rate?"*. A success rate is a metric; it
belongs on a dashboard, not in the agent's beliefs.

## Pattern classes

Every `learned_patterns` row has a **class** carried in `memory_type`. Only
the first three are *beliefs* (surfaced in the digest, returned by
`cos_learn_suggest`, ranked into the agent's working context). The fourth is
an **observability stat** — visible in the Hub, never injected as a belief.

| `memory_type` | Class | Source signal | Belief? |
|---|---|---|---|
| `lesson` | Friction → correction | `observations` rows with `memory_type IN ('hook_block','error')` + `completion_gap`; **`fix:`/`revert:` commit subjects** | ✅ |
| `anatomy` | Failure root cause + remedy | `backtrack_events` (`root_cause`, `corrective_action`) | ✅ |
| `breakthrough` | Rework → success narrative | `outcome_history` (`is_breakthrough=1`, narrative fields) | ✅ |
| `stat` | Success correlation / baseline | `task_outcomes` `GROUP BY domain/skill` | ❌ observability only |

`source` records provenance: `friction` (mined from observations),
`commit` (mined from `fix:`/`revert:` git history — the real engineering-lesson
signal), `learn_extract` (mined aggregate stat), `breakthrough`/`manual`/`import`.
The class is set at mint time and refreshed on re-mine; the success-baseline
and skill-correlation branches MUST write `memory_type='stat'`, never `pattern`.

## What `learn_extract` mines

### 1. Lessons from friction (primary)
The abundant, automatic signal. `_mine_friction_lessons` reads
`observations` where `memory_type IN ('hook_block','error')` plus
`completion_gap` rows, clusters them by a **normalized signature**, and emits
one `lesson` per cluster meeting the recurrence threshold.

Normalization (so a cluster is stable across sessions and projects):
- strip absolute paths → basename or `<path>`; strip line/col numbers, hex
  hashes, UUIDs, and TASK-NNN ids → placeholders;
- `hook_block` clusters on the **blocked rule / hook name** parsed from the
  message (e.g. "graph-explorer skill not loaded");
- generic `error` clusters on the **error class** (the stable leading clause).

Lesson text is plain language, e.g.
`Recurring block (5×): editing core Python without the graph-explorer skill
→ load it before the edit`. No jargon, no absolute paths, no ids.

Threshold: `min_occurrences` default **2** for lessons (a friction event seen
twice is already worth a rule), vs 3 for stats. One-offs are not minted; they
decay out of the corpus naturally.

**Noise filter (mandatory).** Not every captured `error` is a lesson. Agent
tool-fumbles and expected refusals carry zero learning value and would drown the
signal, so `_is_noise_failure` drops a cluster whose message matches any of:
`EISDIR` / "illegal operation on a directory", "file does not exist" / "no such
file or directory" (wrong-path Reads), "refusing to write through symlink"
(expected guard), and the workflow-internal `StructuredOutput` schema mismatch.
These are *the agent tripping over its own tooling*, never an engineering lesson.
The filter applies to both friction miners. Genuine `completion_gap` rows are
**kept** — forgetting to close a task IS a real behavioural lesson — but their
text is humanized (below).

**Humanized text (no model-jargon).** Per XAI guidance (Google PAIR / Microsoft
HAX), a lesson must speak the user's language, not the model's. `_humanize_signature`
rewrites the worst internal jargon into plain language before the lesson is
minted (e.g. `predicates_unsatisfied: no EvidenceBundle for predicates
['coverage_100']` → "ended a 'fix everything' task without recording proof every
case was handled"). The lesson leads with the **corrective action**; the raw
signature is preserved for the UI's opt-in detail layer.

> **Gotcha (one-time migration).** Humanizing at the *producer* changes the
> minted text, which changes `_pattern_identity`. A re-mine therefore `created`
> NEW rows beside the old jargon ones instead of updating them in place — the
> old rows must be deleted once (they are superseded; future re-mines match the
> humanized identity and update cleanly). This is why the relevance fix included
> a one-shot deletion of the legacy jargon `lesson` rows on the live DB.

### 2. Anatomy from backtracks
The v25 `backtrack_events` columns (`root_cause`, `corrective_action`) are
mined into `anatomy` lessons that pair the cause with the remedy — not a bare
`GROUP BY root_cause` count.

### 3. Breakthroughs from rework→success
When `outcome_history` carries `is_breakthrough=1` with narrative fields, the
loop mints a `breakthrough` belief. These remain populated by
`cos_learn_narrative`; the loop never fabricates a narrative.

### 4. Stats (observability only)
Domain/skill success correlations are still computed (a real project signal)
but written as `memory_type='stat'`. They are **excluded from beliefs**: the
digest and `cos_learn_suggest` filter them out; the Hub shows them in a
separate, clearly-labelled "Project Stats" section, never as "Lessons".

**Variance gate (mandatory).** A success-rate stat only *informs* when the
corpus has variance to explain. On a monotone-success corpus (e.g. 192/192
success) every "X succeeds at 100%" is a tautology that carries zero signal —
so the success-baseline and skill-correlation branches are skipped entirely
unless `task_outcomes` contains at least one non-`success` outcome. A real
project with reworks/failures still gets meaningful, differentiating stats;
a flawless corpus gets none (correct — nothing to explain).

### 5. Lessons from fix / revert commits (the real engineering signal)
Friction observations capture the agent tripping over *tooling*; the lessons a
human calls valuable ("FTS5 external-content corrupts — use own-content",
"resolve() before relative_to on macOS") are discovered by *reasoning* and
recorded in **git history**, not in any signal table. `_mine_commit_lessons`
closes that gap: it reads `git log` over `_LESSON_WINDOW_DAYS`, keeps only
`fix:` and `revert:` Conventional-Commit subjects (a commit that fixes/reverts
IS a "something was wrong → here is the correction"), strips the type prefix and
scope, normalises the subject to a stable cluster key (lowercase, digits→N,
TASK-ids and hashes → placeholders), and mints one `lesson` per subject that
recurs `≥ floor` times — or a single high-signal `revert:` immediately, since a
revert is always a real mistake. `source='commit'`. It is read-only (`git log`
only), bounded (window + `max_count`), and a no-op outside a git work-tree.
This is the highest-relevance source for a healthy project, where friction is
otherwise dominated by tooling noise.

## Confidence, decay, validation
- Lessons start at a recurrence-derived confidence and **decay** like any
  pattern (`decay.py`) — a trap that stops recurring fades.
- `times_validated` rises on re-mine (re-confirmation) and on explicit
  `cos_learn_validate`; `times_violated` rises on negative validation.
- Stats are never ranked into beliefs, so their confidence is informational.
- **Consolidation:** the nightly decay run merges semantically near-duplicate
  lessons (embeddings cosine ≥ `COS_CONSOLIDATION_THRESHOLD`, default 0.85) into
  the strongest survivor (highest confidence → times_validated → oldest), folding
  the loser's counts — so the corpus stays sharp instead of fragmenting into
  micro-variants. No-op when embeddings are unavailable.

## Digest & recall contract
- A **belief** is any pattern whose `memory_type` is NOT `stat`
  (`COALESCE(memory_type,'') != 'stat'`) — lessons, anatomy, breakthroughs,
  rework/complexity signals, and manual/user patterns all qualify; only
  success-rate baselines are excluded.
- `digest._collect_beliefs` selects beliefs at `confidence ≥ 0.5`, ranked by
  (confidence × impact) then recency, with a friendly empty state for new
  projects. A separate, lowest-priority "Project Stats" section renders the
  `stat` rows so success rates stay visible but never read as learnings.
- `cos_learn_suggest` excludes `stat` from both its active and fading queries.

## Drift contract
Memory is frozen at write time; code evolves ([memory.md](../../src/core/rules/memory.md)).
`cos_search` results carry `re_verify_recommended: true` when the record's
`created_at` predates the last modification time of the file it references —
an advisory surfaced to the agent so it Reads current code before trusting a
stale recall. Heavier decay-on-diff is a documented future option, not built
by default.

## UI contract (Hub Memory page)

Grounded in XAI/PAIR research (Google PAIR, Microsoft HAX, IBM Design-for-AI,
NIST AI-RMF); the page must teach a *novice* the memory system, not dump rows. Principles:
**speak human · 3-layer progressive disclosure · legible confidence · agency · honest empty state.**

- **Three-layer cards** (progressive disclosure — never dump everything):
  - **L1 (always visible):** the corrective action in one plain sentence — what
    the agent now avoids. No model-jargon.
  - **L2 (visible, secondary):** a plain meta line — `Seen N times · <tier>` where
    tier ∈ **Forming / Trusted / Fading** (derived from confidence × times_validated),
    NOT a bare percentage (a raw % is meaningless to users).
  - **L3 (opt-in, expandable "Technical detail"):** the raw signature, exact
    confidence %, provenance/source, occurrences. Power-user layer.
- **Agency — 👍/👎 per lesson** wired to `POST /api/patterns/{id}/validate`
  (→ `cos_learn_validate`). This both gives the user control AND closes the
  validation loop (which is otherwise empty). "Was this lesson useful?"
- **Lessons Learned** first; **Project Stats** clearly secondary, labelled as
  success rates, never as learnings.
- **Learning-loop runs**: execution log from `.coding-os/scheduled/last_run.json`
  + inline **Run learning loop now** button (`POST /api/scheduled/run/{slug}`).
- **Learning effectiveness**: friction-per-session sparkline (`GET
  /api/patterns/roi`) PLUS a one-sentence human read-out ("fewer repeated
  mistakes over the last N sessions" / "holding steady") — celebrate the win,
  don't just draw a slope. Computed on-the-fly, no new table.
- **Honest empty state**: when there are no real lessons yet, say so plainly
  ("The agent hasn't hit enough repeated friction to learn a lesson yet — that's
  healthy") instead of padding the list with stats dressed as lessons.
- A one-paragraph beginner explainer of how the agent learns.

### Confidence tier mapping (single source for digest + UI)
`pattern_tier(confidence, times_validated)`:
- **Trusted** — `confidence ≥ 0.7 AND times_validated ≥ 3` (confirmed repeatedly).
- **Fading** — `0.2 ≤ confidence ≤ 0.4 AND times_validated ≥ 1` (was learned, decaying — up for re-validation).
- **Forming** — everything else (seen, not yet confirmed).

## Hook BLOCK lessons (mined from the activity log)

The richest friction signal is a **hook BLOCK** (a PreToolUse hook exiting 2).
It never reaches the `observations` table: a PreToolUse block cancels the tool,
so no `PostToolUse` fires — and `PostToolUseFailure` is not reliably emitted on
Claude regardless (it renders into settings but `.hooks.log` shows zero
`capture-tool-failure` runs). A `PostToolUseFailure` hook also could not see a
*block* anyway — the tool never ran.

But every block IS recorded in the append-only activity log as
`[<ts>] [<hook>] [block] … rule=<rule>` (via `cos_log_hook <id> block`).
`_mine_hook_block_lessons` reads that log (`$COS_HOOK_LOG`, else
`<root>/.coding-os/.hooks.log`), clusters blocks from the last
`_LESSON_WINDOW_DAYS` (90) by `<hook>:<rule>`, and mints one `lesson` per
cluster that recurs ≥2×. Both friction miners share that recency window, so a
resolved or renamed-rule failure ages out (stops being re-confirmed) and
decays instead of lingering forever. This needs
no change to the hot path or to any safety hook, and works for every adapter
because the log is the agent-agnostic SSOT for block events. The log is
self-rotating (`COS_HOOK_LOG_MAX_LINES`), so the read is bounded.

## Active learning loop — auto-validation (closing learn→apply→confirm)

A lesson is only "learned" if its confidence reflects whether it actually
helped. Historically `pattern_validations` was empty — `cos_learn_validate`
was only ever called if the agent volunteered it, which it never did, so
confidence was frozen theater.

The loop now closes automatically at task completion, with **no new table and
no new hook**: the surfaced lesson ids already live in the per-panel
`.learn-suggestions` file (written by `auto_compose.py` at recall time), and the
existing `remind-learn-validate.sh` already fires on `cos task-done`. It now
calls `_helpers/auto_validate_lessons.py`:

1. read the surfaced `(pattern_id, text)` rows from `.learn-suggestions`;
2. read this session's friction observations (`memory_type IN
   ('hook_block','error')`) created at/after the recall (file mtime);
3. clean each failure narrative with `_clean_failure_text` and check
   containment against each surfaced lesson's text;
4. a lesson whose failure **recurred** → `cos_learn_validate(helpful=False)`
   (you saw the lesson and still hit it); a surfaced lesson with **no
   recurrence** → `helpful=True`.

`learn_validate`'s existing 1-hour throttle makes a manual agent validation win
over the auto one, and the LTP/LTD formulas + decay bound any over-boost.
Fire-and-forget: any error leaves the reminder behaviour intact.

## Just-in-time recall (at the moment of risk)

Recall isn't only at session start. `jit-recall.sh` (PreToolUse Write|Edit)
runs `_helpers/jit_recall.py` right before an edit and, if a `lesson` text names
the file's basename, warns with it (`🧠 [recall] …`) — the same warn surfacing
`enforce-graph-context` uses. Debounced once per (file, session), warn-only,
fail-open. Codex skips it (no Write|Edit PreToolUse matcher) — correct, not a gap.

## Generalization — episodic → semantic (human-gated)

When several lessons recur on a shared theme, `generalize_lessons` (called at the
end of `learn_extract`) greedily clusters them by embeddings cosine and, for a
cluster of ≥3, writes a **human-review draft** to `.coding-os/memory/drafts/`
suggesting one general rule. It NEVER calls an LLM and NEVER writes to
`src/core/rules/` or docs — abstraction is surfaced for a human to promote
(`cos_promote`), never auto-applied. Deduped by cluster signature; no-op without
embeddings.

## Anti-overengineering boundary
No new table, scheduler, or store. `memory_type` is free-text, so the
`lesson`/`stat` classes need no migration. The three existing triggers
(task-done every-10, nightly cron, session-end responsive) and the
`last_run.json` execution log are reused as-is.

## See also
- [src/core/rules/memory.md](../../src/core/rules/memory.md) — memory layer policy + four-layer model
- [scheduled-jobs.md](scheduled-jobs.md) — when the loop runs
- [src/core/thinking_os/tools/learning.py](../../src/core/thinking_os/tools/learning.py) — the producer
