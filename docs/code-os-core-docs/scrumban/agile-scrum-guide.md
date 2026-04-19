<!-- domain:DOCS | layer:reference | ssot:ref | updated:2026-08-05 -->
# Agile, Scrum, Kanban and Scrumban — the methodology behind `board_os`

> Background reference for the Scrumban model that `src/core/board_os/`
> implements. Read it to understand *why* the board has swimlanes, WIP
> limits and a `ready` gate rather than sprints. The enforced lifecycle
> itself lives in [task-lifecycle.md](../../governance/task-lifecycle.md).

---

## Table of contents

1. [Why a work-management model at all](#1-why-a-work-management-model-at-all)
2. [Agile — the philosophy](#2-agile--the-philosophy)
3. [Scrum — timeboxed iteration](#3-scrum--timeboxed-iteration)
4. [Kanban — continuous flow](#4-kanban--continuous-flow)
5. [Scrumban — the hybrid `board_os` implements](#5-scrumban--the-hybrid-board_os-implements)
6. [Adjacent models worth knowing](#6-adjacent-models-worth-knowing)
7. [Waterfall — and when it is still right](#7-waterfall--and-when-it-is-still-right)
8. [Single-maintainer and agent-driven adaptations](#8-single-maintainer-and-agent-driven-adaptations)
9. [Model comparison](#9-model-comparison)

---

## 1. Why a work-management model at all

A work-management model answers three questions continuously: **what is
being worked on right now, what comes next, and what is left.**

Without one, three failure modes recur — and all three are amplified when
the "team" is one maintainer plus autonomous agents:

- **Unbounded work in progress.** Everything is started, nothing is
  finished. Each context switch costs real re-orientation time.
- **No definition of finished.** Work is perpetually 90% done because
  "done" was never written down.
- **Invisible state.** Nobody — human or agent — can answer "what is in
  flight?" without reading the whole repository.

`board_os` targets exactly these three: a WIP limit, a per-kind
Definition of Ready/Done, and a single queryable board.

---

## 2. Agile — the philosophy

The Agile Manifesto (2001) states four preferences:

```
1. Individuals and interactions   >  processes and tools
2. Working software               >  comprehensive documentation
3. Customer collaboration         >  contract negotiation
4. Responding to change           >  following a fixed plan
```

**Agile is not a methodology.** It is a set of value preferences.
Scrum, Kanban, XP and SAFe are concrete implementations of it. The
practical core: build a small slice, put it in front of someone, take
the feedback, correct, repeat — instead of planning for six months and
discovering the plan was wrong at the end.

> Note the tension with this repository's own Rule 0 (docs-first) and
> Rule 19 (docs are the contract). Preference 2 ranks *working software*
> above *comprehensive documentation* — it does not rank it above
> *specification*. coding-os writes the spec before the code precisely so
> the software keeps working after its author forgets why.

---

## 3. Scrum — timeboxed iteration

Scrum divides work into fixed-length **Sprints** (1–4 weeks). A Sprint
has a goal, a committed scope, and an increment at the end.

### Roles

| Role | Responsibility |
|---|---|
| Product Owner | Owns priority — decides what matters most |
| Scrum Master | Owns process — removes blockers, protects the timebox |
| Developer | Owns delivery — builds the increment |

### Events

| Event | Purpose |
|---|---|
| Sprint Planning | Select scope from the backlog, set the Sprint goal |
| Daily Scrum | 15 min: done yesterday / doing today / blocked by |
| Sprint Review | Demonstrate the increment, gather feedback |
| Sprint Retrospective | Inspect the *process*, commit to one improvement |
| Backlog Refinement | Clarify, estimate and split upcoming items |

The Retrospective is the most frequently skipped and the highest-value
event: it is the only one that improves the system rather than the
output. `cos retro` exists for this reason.

### Artifacts

- **Product Backlog** — every known desirable change, ordered by value.
- **Sprint Backlog** — the slice committed to the current Sprint.
- **Increment** — the shippable result, satisfying the Definition of Done.

### Story points

Points estimate *relative complexity*, not hours. Absolute time
estimates are reliably wrong; relative comparisons ("this is roughly
twice that") are much less so. The usual scale is Fibonacci — 1, 2, 3,
5, 8, 13 — where a large number is a signal to **split the item**, not
to schedule a long stretch of work.

---

## 4. Kanban — continuous flow

Kanban originates in Toyota's production system. Instead of fixed
iterations, work flows continuously through explicit stages:

```
BACKLOG → READY → IN PROGRESS → REVIEW → TESTING → DONE
```

### The core constraint: WIP limits

**WIP = Work In Progress.** A column carries a hard cap on how many
items may occupy it at once. At the cap, no new work may start — an
item must leave the column first.

This inverts the default incentive. Starting work feels productive and
is free; finishing work is what actually delivers value. A WIP limit
prices starting, so the queue drains instead of growing. `cos wip`
enforces this, and `cos_task_move` refuses a transition that would
breach the cap.

### Scrum compared with Kanban

| Dimension | Scrum | Kanban |
|---|---|---|
| Cadence | Fixed Sprint (1–4 weeks) | Continuous |
| Mid-flight change | Discouraged inside a Sprint | Always allowed |
| Roles | Prescribed | None prescribed |
| Primary metric | Velocity | Cycle time |
| Best fit | New feature work, team commitment | Maintenance, support, interrupt-driven work |

---

## 5. Scrumban — the hybrid `board_os` implements

Scrumban keeps Kanban's flow model and borrows the parts of Scrum that
create rhythm and reflection:

- **From Kanban:** WIP limits, explicit columns, swimlanes, pull-based
  scheduling, cycle-time measurement.
- **From Scrum:** an explicit Definition of Ready and Definition of
  Done, periodic review, and the retrospective.

This is the right shape for a repository where work arrives
unpredictably (a bug report, a dependency advisory, a user request) and
where the executing agent needs an unambiguous, machine-readable answer
to "what may I pull next?"

`board_os` maps the model as follows:

| Scrumban concept | `board_os` implementation |
|---|---|
| Column | `status`: `icebox` → `ready` → `in_progress` → `testing` → `complete` |
| Swimlane | `swimlane`: `core`, `cli`, `adapters`, `templates`, `docs`, … |
| WIP limit | `cos wip`, enforced on every `cos_task_move` |
| Definition of Ready | Outcome + Read First + Acceptance, per-kind (`cos task-validate`) |
| Definition of Done | Acceptance criteria as Given/When/Then |
| Pull | `cos_task_claim_next` / `cos task-start` |
| Retrospective | `cos retro` |
| Cycle time | Task history timestamps, surfaced in `cos daily` |

---

## 6. Adjacent models worth knowing

### Shape Up

Work is organised into fixed six-week **cycles**, each a *bet*. Two
ideas transfer well:

- **Appetite instead of estimate.** Not "how long will this take?" but
  "how much time is this worth?" — the timebox constrains the scope
  rather than the scope determining the timebox.
- **No automatic rollover.** An unfinished bet is dropped rather than
  carried, forcing a fresh decision about whether it still deserves
  time. This is what `icebox` is for.

### OKR

Objectives (qualitative direction) with Key Results (measurable
outcomes). OKRs and a board are complementary, not competing: OKRs
express *where* to go, the board expresses *how* the next step happens.
Keep them separate — an OKR is not a task.

### DORA metrics

Four measures of delivery health: deployment frequency, lead time for
changes, change failure rate, and time to restore service. They measure
the *pipeline*, not the people, and stay meaningful for a single
maintainer.

### Extreme Programming (XP)

Team-oriented overall, but several practices apply directly here:
test-driven development, continuous refactoring, small frequent
releases, and review of every change by a second party — which for an
agent-driven repository means a review pass distinct from the author.

---

## 7. Waterfall — and when it is still right

Waterfall runs each phase once, in sequence:

```
requirements → design → implementation → testing → deployment → maintenance
```

Its failure mode is well known: nothing is usable until the end, and a
requirements error discovered during testing invalidates everything
built on it.

It remains the correct choice where iteration is genuinely impossible
or prohibited: hardware and embedded firmware fixed at fabrication,
fixed-scope contractual work, and regulated domains — aerospace,
medical devices — where each phase must be certified before the next
may begin.

---

## 8. Single-maintainer and agent-driven adaptations

A single-maintainer repository loses the social pressure that keeps a
team's process honest, and an agent-driven one loses the shared context
a standing team carries in its head. Two consequences shape `board_os`:

**The process must be enforced by tooling, not by discipline.** A
convention nobody checks is a convention that decays. This is why the
lifecycle is hook-enforced rather than documented and hoped for.

**State must be external and explicit.** A human teammate can be asked
what they meant; an agent that ends its session cannot. Every task
therefore carries its own Outcome, Read First list and Acceptance
criteria, so the next session — human or agent — inherits intent rather
than reconstructing it.

The practical loop:

```
Weekly   — review what closed, pull the next few items to `ready`
Daily    — `cos daily`: what is in flight, what is blocked
Per task — one item in progress; finish before starting
Per close— run the verification matrix, then `cos task-done`
```

**On "done".** Done means the Acceptance criteria are met and verified
by execution — not that the work is beyond improvement. Anything better
than the accepted bar is a new task, not a reason to hold the current
one open. This is the single most useful thing the Definition of Done
buys a perfectionist maintainer.

---

## 9. Model comparison

| Model | In one line | Best fit |
|---|---|---|
| **Agile** | Value preferences favouring iteration and feedback | Everything below derives from it |
| **Scrum** | Fixed-length sprints with prescribed roles and events | Teams, committed scope |
| **Kanban** | Continuous flow bounded by WIP limits | Maintenance, interrupt-driven work |
| **Scrumban** | Kanban flow plus Scrum's Ready/Done and retrospective | Small teams, solo maintainers, agent-driven repos |
| **Shape Up** | Six-week bets sized by appetite | Product work with a real deadline |
| **OKR** | Measurable objectives | Direction, never task tracking |
| **XP** | Engineering practices for code quality | Any codebase, at any team size |
| **Waterfall** | Sequential, single-pass phases | Hardware, regulated and fixed-contract work |

---

> **The operative rule:** the best process is the one that is actually
> followed. A simple board consulted daily beats an elaborate one
> abandoned in a week. Start minimal, and add ceremony only where a real
> failure demanded it.
