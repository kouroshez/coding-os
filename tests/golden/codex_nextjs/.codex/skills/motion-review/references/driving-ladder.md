# The Driving Ladder — what your comparison is allowed to claim

A before/after is only honest if the same input was replayed. Most of the time you cannot
guarantee that. The answer is **not** to refuse the recording — an after-only demonstration is
genuinely useful, and a refusal is the kind of rule an agent narrates past. The answer is to
**downgrade the claim** and say so.

## Three claim tiers

| Tier | Means | You may |
|---|---|---|
| `CONTROLLED` | the same input artifact was replayed, start state and environment pinned and stated, executed-step logs identical | attribute the difference to the change |
| `MATCHED-INPUT` | the same input artifact was replayed, but something was not held constant — and the report **names what** | describe the difference, not attribute it |
| `UNMATCHED` | improvised or hand-driven | present one recording as a demonstration; it is not a comparison |

**The tier is a floor set by the rung, and evidence can only push it DOWN, never up.** A
convincing-looking video is not evidence. Every artifact opens with a provenance line naming
its tier.

## The rungs, best first

### Rung 1 — a committed flow file, recorder inside the flow

Highest available when the project already has UI flows and stable test identifiers. The
recorder is a step in the flow, so start/stop boundaries are replayed too.

- **Gains:** the input is a file, so "the same input" is a hash rather than a promise.
  Identifier-based selectors survive copy, locale and layout changes. The run log proves after
  the fact what actually executed.
- **Loses:** needs a device and a live backend; exists only where the project already invested.
- **Rules:** hash the flow *and* every subflow before each run; both runs must show an
  identical hash set. A comparison-grade flow bans self-healing retries, conditionals and
  random or time-derived identities — run a branch-free copy, not the committed flow, which is
  usually written to survive flakiness rather than to be reproducible. Pin and record the
  environment: device, theme, locale, build, app version. Diff the executed-step logs
  afterwards; any difference demotes the claim one tier.

### Rung 2 — a flow authored for this comparison, saved then replayed

Same property set as rung 1 at authoring cost, for a project with an installable app but no
flows covering this path.

- **Loses:** without stable test identifiers you fall back to text selectors, which are
  locale-bound. If the change under test *is* a copy change, the selector that made the before
  run work is exactly what the after run breaks on — or worse, still matches something else.
- **Rules:** prefer identifier selectors. Where text is unavoidable, assert the same string is
  present in both runs before acting on it; if the copy changed, that step's comparison is
  void — say so. Never author the second run's flow from a fresh look at the screen: run the
  same file.

### Rung 3 — a saved action script against semantic targets (web)

The only zero-setup rung that is still semantic. Works in every project, since a browser needs
no build and no device.

- **Loses:** browser automation has no video tool of its own, so "recording" here means an
  ordered screenshot series; element handles are resolved per run, so what is replayed is your
  *intent*, not a byte-identical input.
- **Rules:** write the action list to a file **before** the first run and execute it verbatim
  in both. Improvising the second run from a fresh page snapshot is the exact defect this rung
  exists to avoid. Capture at identical step boundaries so the series are index-comparable. If
  a step's target cannot be resolved in the after run, stop — do not substitute a nearby
  control.

### Rung 4 — deep link first, coordinates only where a link cannot reach

Zero project setup on an already-installed app, with an external recorder.

- **Gains:** a deep link is a stable semantic address — it lands on the same screen in both
  runs regardless of layout. Lead with links; spend as few coordinate taps as possible.
- **Loses:** coordinates are not semantic. **This is the most dangerous rung**: the same x,y in
  the after run hits whatever the new layout put there, nothing errors, the run completes
  green, and the comparison is a lie.
- **Rules:** write every coordinate step to a script file and replay from it. **Mandatory
  layout guard** — before each coordinate tap in the after run, resolve what is under that
  point and confirm it is the same control; any mismatch voids that step and must be reported,
  not absorbed. Own the recorder's PID. Text input on these paths is often ASCII-only, so
  accented, RTL and emoji strings cannot be driven at all.

### Rung 5 — a human drives, the agent records

- **Gains:** crosses walls nothing else can — a real one-time code, a real payment sheet, a
  physical device, a login the agent must not perform.
- **Loses:** reproducibility, entirely. Two hand-driven runs differ in timing, path and dwell.
- **Rule — the single refusal on the whole ladder:** **never present two hand-driven runs as a
  before/after.** Offer the honest alternatives instead: record only the after and state the
  before is absent, or have the human perform one run per condition and label it hand-driven.

## Picking a rung is evidence-based, not name-based

"Does this project have an e2e directory" is the wrong question. These are four separate
probes with four separate answers:

1. Is the flow runner on PATH?
2. Is a device or emulator booted?
3. Does a flow file already cover this path?
4. Does the app carry stable test identifiers?

Answer them, take the highest rung all four support, and write the tier into the report.
