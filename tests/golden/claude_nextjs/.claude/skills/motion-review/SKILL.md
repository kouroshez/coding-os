---
name: motion-review
tier: cross-cutting
domain: [universal]
description: Watch a screen recording or any video and judge what a screenshot cannot show — an animation, a transition, a flow, a gesture response, or simply what happens in a video someone handed you. Use when the question is temporal ("does this animation glitch?", "did the fix actually work?", "what happens in this clip?", "why does this screen feel wrong?"), when a UI change animates, or when a user supplies a video file, a screen recording or a video URL. A still frame shows a moment; only a recording shows a flow.
context: fork
allowed-tools:
  - Read
  - Bash
  - Glob
argument-hint: "Path or URL of a recording, plus what to judge (e.g. 'run.mp4 — does the sheet settle without overshoot?')"
last_reviewed: "2026-09-15"
---

A recording is useless until its frames are in your context. This skill turns one into the
small set of frames worth looking at, then tells you what to judge them for.

## The one fact that drives everything

**A UI recording is a step function, not a film.** Measured on real captures: ~84% of the
timeline is a settled state and ~16% is transition — but ~30% of the *frames* sit inside
those short transitions, because screen recorders are variable-rate and emit a frame only
when the picture changes. Every difference-based frame selector therefore spends the budget
backwards, and every cut-based one returns nothing at all.

So: **one frame per settled state, N frames per transition.** Why each ffmpeg built-in fails,
with numbers: [references/frame-selection.md](references/frame-selection.md).

## Process

1. **Get a recording.** Five sources, one output — a local video file. Exact commands and the
   trap each one carries: [references/capture-sources.md](references/capture-sources.md).
   If you are driving the app yourself, pick a rung and its claim tier first:
   [references/driving-ladder.md](references/driving-ladder.md).

2. **Select the frames.**

   ```bash
   python3 scripts/frames.py <recording> --out <frames-dir>
   ```

   Stdlib only; needs `ffmpeg`/`ffprobe` on PATH and nothing else. It prints a frame list,
   a per-transition timing profile, and a role label for every frame. `--json` for the
   machine-readable form. Preflight the host with `python3 scripts/doctor.py`.

3. **Read every frame it lists.** In one message, parallel calls. The labels are the map:
   `settled state 2 of 4` is judged for layout, type, contrast and state correctness;
   `transition 3 of 3, frame 4 of 7, t=+244ms` is judged for trajectory — what moves, what
   stays, whether it overshoots.

4. **Judge against the contract**, never "my change landed":
   [assets/review-contract.md](assets/review-contract.md). It carries the defect classes a
   still frame structurally cannot show, and the finding grammar.

5. **Report what you observed.** Cite frames by label. State the claim tier from step 1. If
   a pass could not be run, say which and why — silence reads as coverage.

## What the engine refuses to do

- **Return an empty set quietly.** A recording of a screen that never changed is a one-frame
  file; the engine fails with the frame count and says the UI was probably never driven.
- **Dedup in greyscale.** An enabled control and its luminance-matched disabled twin measure
  identical in grey and in a perceptual hash. Settled frames are compared in colour; transition
  frames are never deduped, since differing is their whole job.
- **Guess a frame rate.** It reads the real per-frame timings, so a variable-rate recording is
  measured as it actually is.

## Timing: what is measured and what is not

The engine measures, per transition: duration, frame count, median/max inter-frame gap,
implied fps, and stutter count. Those are facts.

**Pacing is not among them.** A simulator recording's timeline is not wall-clock — three idle
seconds produced 0.067 s of video in a measured capture — so "the after feels faster" is a
claim no simulator recording can support. Measure pacing from the driver's own log instead,
and say that is where it came from.

## Whose standard applies

This skill owns **how to watch and judge**. A project owns **what its motion is** — every
duration, easing, haptic mapping and deliberate exception — and wins on every conflict.

Before judging durations, look for a project motion standard (a motion or design-token doc in
the repo). If one exists, every number comes from there and the default envelope only fills
its silences. Open the review with one line naming which applied — `envelope: project(<path>)`
or `envelope: default` — so a wrong yield is visible instead of silent. The defaults and their
authority levels are in [assets/review-contract.md](assets/review-contract.md); a generic
ceiling cited against a deliberate house choice is a false finding, not a catch.

## Install

Nothing to build — the directory is the skill. Symlink it into whichever agent skill roots you
use: [references/installing.md](references/installing.md). It carries no dependency on this
repo, so it works the same inside a coding-os project and in one that has never heard of it.

## See also

- [end-to-end-testing](../end-to-end-testing/SKILL.md) — authoring the flow that drives the app while it records.
- [frontend-design](../frontend-design/SKILL.md) — the static half: layout, type, colour on a still frame.
- [a11y](../a11y/SKILL.md) — reduce-motion and the vestibular case, which a motion review is the right moment to check.
