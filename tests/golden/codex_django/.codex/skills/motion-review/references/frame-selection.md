# Frame Selection — why the obvious approaches fail, and what to do instead

Every number here was measured on real screen recordings, not reasoned about.

## The shape of the problem

A UI recording is a **step function**: long settled states punctuated by short transitions.
On a measured 10.4 s iOS capture (243 frames): ~84% of the *timeline* is settled, ~16% is
transition — but ~30% of the *frames* land inside the transitions, because the recorder is
variable-rate and emits a frame only when the picture changes.

A reviewer needs two different things from those two regions:

| Region | Needs | Judged for |
|---|---|---|
| Settled state | exactly one frame, and never to miss a state | layout, spacing, type, contrast, state correctness |
| Transition | several frames across it | trajectory, easing, overshoot, what moves vs what stays |

No ffmpeg built-in expresses "one per settled run, N per moving run", because every one of
them is a **per-frame-pair** rule and this is a **per-segment** budget.

## Why each built-in fails

| Strategy | Result on the measured clip | Why |
|---|---|---|
| `select=gt(scene,0.3)` | **0 frames, exit 0** | The whole-clip maximum scene score was 0.2199. The conventional thresholds are unreachable on UI content, so it emits nothing *silently*. Tuned down to 0.02 it spent every frame mid-animation and captured 0 of 5 states — the filter fires at *maximum change*, which is by definition the middle of a transition. |
| `fps=1` | misses the final state entirely | Fixed-rate sampling stops at t=9.0 on a 10.415 s clip. It also re-photographs an unchanged screen: `fps=2` wasted 13 of its 21 frames on duplicates. |
| `-skip_frame nokey` | 9 frames, 5/5 states — but fragile | Works only because the encoder happened to place adaptive I-frames at the transitions. A forced fixed GOP destroys the correlation and degrades it to a worse `fps=N`, with no error. Usable only behind a keyframe-interval precheck. |
| `mpdecimate` | 133 frames, 81% inside transitions | It is a *motion* detector, not a *settle* detector: it keeps the first frame of every changed run, so it floods the output with transition frames and still spends ~15× redundancy on the settled ones. Its count also swings with the muxer and `fps_mode` (133 / 235 / 64 for one filter), so no budget can be built on it. |

## The algorithm

### 1. Profile — let ffmpeg compute the change series

```
ffmpeg -v error -i IN -an \
  -vf "scale=64:64:flags=area,format=yuv444p,tblend=all_mode=difference,signalstats,\
metadata=print:file=-" \
  -fps_mode passthrough -f null -
```

Each output record carries `pts_time` plus `YAVG`, `UAVG` and `VAVG` — the mean absolute
luma and chroma difference between consecutive frames. The change magnitude is
`YAVG + 0.5 × (UAVG + VAVG)`. The O(frames × pixels) work stays in C — measured **0.44 s for
243 frames of 1206×2622** — and the parse is a flat key/value scan, so the engine needs no
numpy and no Pillow.

- `-fps_mode passthrough` is **load-bearing**. The default resamples a variable-rate recording
  to a constant rate, so the series you then measure describes a frame sequence that never
  existed.
- `tblend` emits one frame per input frame after the first, so the *n*th delta describes the
  change **into** source frame *n+1*. Extraction addresses source indices, so the offset matters.
- **Chroma is not optional, and this is the trap that cost the most here.** Differencing a
  *greyscale* copy is the obvious design and it is wrong: a luminance-matched colour change —
  an enabled control against its greyed-out twin — scores **YAVG = 0**. Measured on a
  synthesised two-state clip (`#2E66EB` → `#646464`): luma 0, **chroma 67 and 34**. A
  greyscale detector reports one state where there are two, and no amount of care downstream
  recovers the state it never saw. Difference in YUV and read all three planes.
- 64×64 because mean-absolute-difference is area-weighted; resolution buys almost no
  sensitivity (a 2px rule scores 0.2578 at 16px and 0.2446 at 256px).

### 2. Segment

`moving = delta >= max(0.35, 3 × median(delta))`.

The adaptive term handles noisy encoders. The 0.35 floor exists because a genuinely still
recording has median 0, and a purely relative threshold would then fire on compression noise.

Merge any settled run shorter than 0.12 s that sits **between** two moving runs — that is one
hitch inside a single animation, not a state.

### 3. Allocate per segment

- **Settled run → exactly one frame, taken at the END of the run.** Not the start: easing
  tails, skeleton→content swaps and late image loads all resolve *after* the delta has already
  fallen below the threshold, so the first post-transition frame can still be mid-fade.
- **Transition run → N frames evenly spaced**, `N = clip(round(duration × 12) + 1, 3, 8)`,
  further clamped to the number of distinct frames the run actually contains. Floor of 3
  because judging an animation needs a start, a middle and an end; ceiling of 8 because past
  that you are paying for interpolation the reviewer can infer.

Because the neighbouring settled representatives sit either side, the reviewer reads a
contiguous *from-state → motion → to-state* strip for free.

### 4. Dedup settled representatives only, in colour

Compare each settled representative to the last kept one; drop below a mean RGB distance of 4.

**Never greyscale, never a perceptual hash** — the same rule as the detector in step 1, for
the same reason. A primary-blue CTA and its luminance-matched disabled grey twin measure
**Hamming 0** under pHash and **0.0000** under a greyscale mean-absolute-difference, while
their RGB distance is **12.5**. Both widely-copied reference implementations of this pipeline
delete every enabled/disabled and valid/error-red pair.

Transition frames are never deduped — differing is their entire job.

### 5. Extract in one pass, by index

```
ffmpeg -v error -y -i IN -an \
  -vf "select='eq(n\,I1)+eq(n\,I2)+…',scale=W:-2,setpts=N/TB" \
  -fps_mode passthrough -q:v 4 out/%03d.jpg
```

By **index**, not by time: a ±4 ms window over a 60 fps burst over-selects. The profile pass
already knows every index. One spawn measured **0.24 s** against **2.66 s** for eighteen.

`setpts=N/TB` is cheap insurance rather than a universal requirement — a sparse four-index
selection succeeded without it here, but a dense selection has been observed to make the
image2 muxer reject non-monotonic timestamps.

### 6. Ship the timing profile beside the images

Per transition: duration, frame count, median/max inter-frame gap, implied fps, stutter count.
On the measured clip both animations reported a 16.7 ms median gap (60 fps, no outliers) — a
smoothness verdict that is invisible in any set of stills and that the profile pass computed
for free.

## Token budget — spend it by role

Cost is `ceil(w/28) × ceil(h/28)` visual tokens, so it follows **aspect ratio**, not width: a
512px-wide portrait phone frame costs ~760 tokens; the same width at 16:9 costs ~209. Budget in
tokens, not frames.

- **Settled states at 512px** — this is where type, spacing and contrast are judged.
- **Transition frames at 320px** — trajectory and overshoot need no type-legible pixels.

Measured clip: 4 × 760 + 15 × 300 ≈ **7,540 tokens for full coverage**, against 133 mpdecimate
frames at 512px ≈ **101,080** for strictly less information.

Over budget? Shed transition frames first (drop each transition to N=3), then whole transitions
by ascending duration. **Never drop a settled state** — a missing state is a missing screen,
while a coarser transition is only a coarser judgement.

## Guards

| Condition | Response |
|---|---|
| Zero moving runs | The recording is one static state. Emit one frame, say so, spend nothing more. |
| Moving runs cover >60% of the timeline | This is not a UI recording (video content, a map, a continuous scroll). Fall back to uniform sampling and **label the fallback in the report**. |
| A settled run whose cumulative sub-threshold delta exceeds 8× the threshold | A slow cross-fade is hiding under the threshold. Split it and take a representative from each half. |

## Known limits

- The threshold was calibrated on an iOS simulator capture (variable-rate) and a Playwright
  recording (constant-rate). It is **not** validated on Android emulator capture, on physical
  devices, or on multi-minute recordings. The engine prints the chosen value and the segment
  table so a wrong call is visible rather than silent.
- A settle detector cannot see a change that never crosses the threshold. A five-second
  cross-fade or a shimmer loop reads as settled; the cumulative-drift guard is a mitigation,
  not a proof.
- One frame per settled state assumes the state finished loading. If the app was still
  fetching, the end-of-run frame is a spinner and the real state never appears in the
  recording at all — a recording-protocol problem no selector can fix.
