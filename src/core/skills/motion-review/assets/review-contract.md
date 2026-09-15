# The Review Contract — what a recording must be audited for

Run this against the frames. A recording read only as "my change landed" is a review failure,
not a review.

## Before you judge a single duration

Find the project's motion standard — a motion document, a design-token file, an animation
section in its design docs. If one exists, **every number comes from there** and the defaults
below only fill its silences.

Open the review with one line so a wrong yield is visible instead of silent:

```
envelope: project(docs/design/tokens.md » Motion)
envelope: default (no project standard found)
```

A generic ceiling cited against a deliberate house choice is a false finding, not a catch.
Two shapes that generic reviewers get wrong almost every time: a spring/bounce on a sheet or
modal open is frequently a *deliberate* attention cue, and an indeterminate loading shimmer is
correctly linear and correctly long — both violate the usual advice on purpose.

## Pass 1 — the settled states (one frame each)

Everything a still-frame review would check, applied to each state in turn:

- **Typography** — one type system across the state; no orphaned size or weight.
- **Alignment** — shared edges and baselines actually shared.
- **Clipping** — nothing cut by an ancestor, nothing overflowing its container.
- **Contrast** — text and essential icons legible against what is actually behind them.
- **Balance** — the state has a focal point; whitespace is distributed, not pooled.
- **State correctness** — this is the state the flow was supposed to reach, fully loaded. If
  the frame shows a spinner or a skeleton, the real state never appeared in the recording and
  the recording does not cover it. Say so; do not judge the skeleton as the state.

## Pass 2 — the transitions (the frames a still cannot give you)

For each transition, from its labelled frames plus the timing profile:

- **Did it start at all?** A transition the engine found as a single frame is either
  instantaneous or was dropped — check which.
- **Trajectory** — what moves, what stays. Elements that should travel together but arrive
  separately read as broken even when every end state is correct.
- **Overshoot and settle** — does it land, or bounce past and come back? Is the bounce
  intentional here (see the envelope above)?
- **Direction** — does the motion agree with the navigation? Forward motion that animates
  backwards is disorienting even at the right duration.
- **Stutter** — the profile's stutter count and max-gap are the evidence. A median gap of
  16.7 ms is 60 fps; a max gap several times the median is a dropped frame you can point at.
- **Duration** — measured, from the profile, against the envelope in force.

## Pass 3 — the classes a still frame structurally cannot show

These are the reason the recording exists. Check each explicitly:

| Class | What it looks like |
|---|---|
| A control that renders correctly and does nothing | the frames after the tap are identical to the frames before |
| A stuck or never-started animation | a transition the profile never found between two states that clearly differ |
| A latched hover or pressed state | a visual state that begins and never ends |
| An element that flashes and disappears | present in one transition frame, absent in both neighbours |
| A mid-flight artifact mistaken for a defect | a contrast or layout "failure" visible only in transition frames and absent in both settled neighbours — this is the fade, not a bug |
| A transition interrupted by another | two transitions overlapping with no settled state between them |

The mid-flight class runs both ways: it is the one that manufactures **false** findings, so
always check whether a defect survives into the neighbouring settled state before reporting it.

## Pass 4 — reduce-motion, when the platform has it

If the project's accessibility stance covers it, capture a second recording with reduced
motion enabled and confirm the flow still resolves — that transitions become instant or
cross-fade rather than disappearing along with the state change they carried.

Note the authority level honestly. Reduced motion for interaction-triggered animation is a
**AAA**-level criterion in WCAG 2.2 (2.3.3), while auto-starting motion longer than five
seconds running in parallel with other content is **Level A** (2.2.2). Calling a AAA criterion
a blocker manufactures unarguable findings and devalues the word for the real ones.

## Default envelope — only when no project standard exists

| Guidance | Source | Authority |
|---|---|---|
| ~100 ms for micro-feedback; 200–300 ms for a substantial change; 500 ms reads as a drag | NN/g | guidance, not a standard |
| Entrances longer than exits; ease-out as the default; linear reads unnatural | NN/g | guidance |
| Pause/Stop/Hide for auto-starting motion over 5 s alongside other content | WCAG 2.2.2 | **Level A** |
| A reduced-motion path for interaction-triggered animation | WCAG 2.3.3 | **Level AAA** |
| Motion should clarify a relationship, not decorate | Apple HIG (principles only; it carries no durations) | principle |

## How to state a finding

Use the grammar the project already uses if it has one. Otherwise:

- **blocker** — pinnable to a criterion, a requirement, a spec, or a token that exists and was
  not used. Not a preference.
- **defect** — clearly wrong, but not pinnable to a written rule.
- **polish** — a real improvement that nobody would call a bug.

One root cause is **one** finding with a count, not one finding per affected frame. Report the
cause, not the symptom. A pass is claimed explicitly — never implied by silence. If a pass
could not be run (no reduced-motion capture, no project envelope found, a state never loaded),
name it as not covered rather than letting the reader infer coverage.

No score out of ten. A number invites arguing the number instead of fixing the screen.
