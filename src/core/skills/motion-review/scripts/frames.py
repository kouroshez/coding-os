#!/usr/bin/env python3
"""Turn a screen recording into the frames a reviewer actually needs."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import subprocess
import sys
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path

PROFILE_SIZE = 64
MOVE_FLOOR = 0.35
MOVE_MEDIAN_MULT = 3.0
MERGE_SETTLED_SECONDS = 0.12
TRANSITION_HZ = 12.0
TRANSITION_MIN_FRAMES = 3
TRANSITION_MAX_FRAMES = 8
DEDUP_RGB_DISTANCE = 4.0
DEDUP_SIZE = 32
SETTLED_WIDTH = 512
TRANSITION_WIDTH = 320
DRIFT_MULTIPLE = 8.0
CONTINUOUS_MOTION_RATIO = 0.60
FALLBACK_FPS = 2.0

_META = re.compile(r"^frame:(\d+)\s+pts:\S+\s+pts_time:([0-9.]+)")
_STAT = re.compile(r"lavfi\.signalstats\.([YUV]AVG)=([0-9.]+)")
CHROMA_WEIGHT = 0.5


class EngineError(RuntimeError):
    pass


@dataclass
class Segment:
    kind: str
    first: int
    last: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Pick:
    index: int
    time: float
    role: str
    group: int
    offset_ms: int
    width: int
    label: str = ""


def _run(cmd: list[str], *, capture_stdout: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )


def _require_binaries() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise EngineError(
            f"missing required binary: {', '.join(missing)}. "
            "Install ffmpeg (macOS: brew install ffmpeg) and re-run."
        )


def probe(video: Path) -> dict:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames",
            "-show_entries",
            "format=duration",
            "-count_frames",
            "-of",
            "json",
            str(video),
        ],
        capture_stdout=True,
    )
    if result.returncode != 0:
        raise EngineError(f"ffprobe could not read {video}: {result.stderr.decode()[:200]}")
    payload = json.loads(result.stdout or b"{}")
    streams = payload.get("streams") or []
    if not streams:
        raise EngineError(f"{video} carries no video stream")
    stream = streams[0]
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "frames": int(stream.get("nb_read_frames") or 0),
        "duration": float((payload.get("format") or {}).get("duration") or 0.0),
        "r_frame_rate": stream.get("r_frame_rate", ""),
        "avg_frame_rate": stream.get("avg_frame_rate", ""),
    }


def delta_series(video: Path) -> list[tuple[int, float, float]]:
    """Per-frame change, computed inside ffmpeg so the cost stays in C."""
    chain = (
        f"scale={PROFILE_SIZE}:{PROFILE_SIZE}:flags=area,format=yuv444p,"
        "tblend=all_mode=difference,signalstats,metadata=print:file=-"
    )
    # passthrough is load-bearing: the default resamples a variable-rate recording
    # to a constant rate, so the series would describe frames that never existed.
    result = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-an",
            "-vf",
            chain,
            "-fps_mode",
            "passthrough",
            "-f",
            "null",
            "-",
        ],
        capture_stdout=True,
    )
    if result.returncode != 0:
        raise EngineError(f"ffmpeg could not profile {video}: {result.stderr.decode()[:200]}")

    series: list[tuple[int, float, float]] = []
    pending: float | None = None
    stats: dict[str, float] = {}

    def flush() -> None:
        if pending is not None and "YAVG" in stats:
            # A luminance-matched colour change — an enabled control against its
            # greyed-out twin — moves only chroma, so luma alone would score it 0.
            magnitude = stats["YAVG"] + CHROMA_WEIGHT * (
                stats.get("UAVG", 0.0) + stats.get("VAVG", 0.0)
            )
            # tblend emits one frame per input frame after the first, so the
            # nth delta describes the change INTO source frame n+1.
            series.append((len(series) + 1, pending, magnitude))

    for line in (result.stdout or b"").decode(errors="replace").splitlines():
        meta = _META.match(line)
        if meta:
            flush()
            pending = float(meta.group(2))
            stats = {}
            continue
        stat = _STAT.search(line)
        if stat:
            stats[stat.group(1)] = float(stat.group(2))
    flush()

    if not series:
        raise EngineError(
            f"{video} produced no frame-to-frame deltas — it is a single still frame. "
            "Screen recorders emit frames only when the picture changes, so this "
            "usually means the UI was never driven while recording."
        )
    return series


def move_threshold(series: list[tuple[int, float, float]]) -> float:
    median = statistics.median(value for _, _, value in series)
    return max(MOVE_FLOOR, MOVE_MEDIAN_MULT * median)


def segment(series: list[tuple[int, float, float]], threshold: float) -> list[Segment]:
    segments: list[Segment] = []
    n = len(series)
    start = 0
    while start < n:
        moving = series[start][2] >= threshold
        end = start
        while end + 1 < n and (series[end + 1][2] >= threshold) == moving:
            end += 1
        segments.append(
            Segment(
                kind="transition" if moving else "settled",
                first=series[start][0],
                last=series[end][0],
                start=series[start][1],
                end=series[end][1],
            )
        )
        start = end + 1
    return _merge_hitches(segments)


def _merge_hitches(segments: list[Segment]) -> list[Segment]:
    # A brief quiet run BETWEEN two moving runs is one hitch inside a single
    # animation, not a state the reviewer needs a frame of.
    merged: list[Segment] = []
    n = len(segments)
    for i, current in enumerate(segments):
        bridged = (
            current.kind == "settled"
            and 0 < i < n - 1
            and current.duration < MERGE_SETTLED_SECONDS
            and segments[i - 1].kind == "transition"
            and segments[i + 1].kind == "transition"
        )
        if bridged and merged:
            merged[-1] = Segment(
                "transition", merged[-1].first, current.last, merged[-1].start, current.end
            )
            continue
        if merged and merged[-1].kind == current.kind:
            merged[-1] = Segment(
                current.kind, merged[-1].first, current.last, merged[-1].start, current.end
            )
            continue
        merged.append(current)
    return merged


def _split_drifting(
    seg: Segment, series: list[tuple[int, float, float]], threshold: float
) -> list[Segment]:
    # A slow cross-fade can sit under the threshold for its whole length and
    # still change the screen completely; the accumulated change gives it away.
    window = [row for row in series if seg.first <= row[0] <= seg.last]
    if sum(value for _, _, value in window) < threshold * DRIFT_MULTIPLE or len(window) < 4:
        return [seg]
    middle = len(window) // 2
    left, right = window[:middle], window[middle:]
    return [
        Segment("settled", left[0][0], left[-1][0], left[0][1], left[-1][1]),
        Segment("settled", right[0][0], right[-1][0], right[0][1], right[-1][1]),
    ]


def allocate(
    segments: list[Segment], series: list[tuple[int, float, float]], threshold: float
) -> list[Pick]:
    expanded: list[Segment] = []
    for seg in segments:
        expanded.extend(_split_drifting(seg, series, threshold) if seg.kind == "settled" else [seg])

    picks: list[Pick] = []
    settled_seen = transition_seen = 0

    for seg in expanded:
        if seg.kind == "settled":
            settled_seen += 1
            # The END of a quiet run, never the start: easing tails, skeleton
            # swaps and late images all resolve after the change has died down.
            picks.append(Pick(seg.last, seg.end, "settled", settled_seen, 0, SETTLED_WIDTH))
            continue
        transition_seen += 1
        span = seg.last - seg.first
        count = round(seg.duration * TRANSITION_HZ) + 1
        count = max(TRANSITION_MIN_FRAMES, min(TRANSITION_MAX_FRAMES, count))
        count = max(1, min(count, span + 1))
        for step in range(count):
            offset = 0 if count == 1 else round(span * step / (count - 1))
            at = seg.start + (seg.duration * step / max(1, count - 1))
            picks.append(
                Pick(
                    seg.first + offset,
                    at,
                    "transition",
                    transition_seen,
                    int((at - seg.start) * 1000),
                    TRANSITION_WIDTH,
                )
            )
    return _dedupe_indices(picks)


def relabel(picks: list[Pick]) -> list[Pick]:
    settled = [p for p in picks if p.role == "settled"]
    n_settled = len(settled)
    per_group: dict[int, list[Pick]] = {}
    n = len(picks)
    for pick in picks:
        if pick.role == "transition":
            per_group.setdefault(pick.group, []).append(pick)
    n_groups = len(per_group)

    for position, pick in enumerate(settled, start=1):
        pick.label = f"settled state {position} of {n_settled}"
    for order, (_, group) in enumerate(sorted(per_group.items()), start=1):
        total = len(group)
        for step, pick in enumerate(group, start=1):
            pick.label = (
                f"transition {order} of {n_groups}, frame {step} of {total}, t=+{pick.offset_ms}ms"
            )
    for pick in picks:
        if not pick.label:
            pick.label = f"uniform sample of {n}"
    return picks


def _dedupe_indices(picks: list[Pick]) -> list[Pick]:
    seen: set[int] = set()
    unique: list[Pick] = []
    for pick in sorted(picks, key=lambda p: (p.index, p.role != "settled")):
        if pick.index in seen:
            continue
        seen.add(pick.index)
        unique.append(pick)
    return sorted(unique, key=lambda p: p.index)


def _raw_frames(video: Path, indices: list[int], size: int) -> list[bytes]:
    if not indices:
        return []
    selector = "+".join(rf"eq(n\,{index})" for index in indices)
    result = _run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(video),
            "-an",
            "-vf",
            f"select='{selector}',scale={size}:{size},format=rgb24,setpts=N/TB",
            "-fps_mode",
            "passthrough",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_stdout=True,
    )
    if result.returncode != 0:
        raise EngineError(f"ffmpeg could not sample frames: {result.stderr.decode()[:200]}")
    stride = size * size * 3
    blob = result.stdout or b""
    return [blob[i : i + stride] for i in range(0, len(blob) - stride + 1, stride)]


def dedupe_settled(video: Path, picks: list[Pick]) -> tuple[list[Pick], int]:
    settled = [p for p in picks if p.role == "settled"]
    if len(settled) < 2:
        return picks, 0
    # Colour, never luminance: an enabled control and its greyed-out twin can be
    # luminance-identical, so a grey or perceptual-hash compare deletes the pair.
    samples = _raw_frames(video, [p.index for p in settled], DEDUP_SIZE)
    if len(samples) != len(settled):
        return picks, 0

    drop: set[int] = set()
    keep = samples[0]
    n = len(settled)
    for i in range(1, n):
        distance = sum(abs(a - b) for a, b in zip(keep, samples[i], strict=True)) / len(keep)
        if distance < DEDUP_RGB_DISTANCE:
            drop.add(settled[i].index)
            continue
        keep = samples[i]
    return [p for p in picks if p.index not in drop], len(drop)


def extract(video: Path, picks: list[Pick], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for width in sorted({p.width for p in picks}):
        group = [p for p in picks if p.width == width]
        selector = "+".join(rf"eq(n\,{p.index})" for p in group)
        pattern = out_dir / f"w{width}_%03d.jpg"
        result = _run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(video),
                "-an",
                "-vf",
                f"select='{selector}',scale={width}:-2,setpts=N/TB",
                "-fps_mode",
                "passthrough",
                "-q:v",
                "4",
                str(pattern),
            ],
        )
        if result.returncode != 0:
            raise EngineError(f"ffmpeg could not extract frames: {result.stderr.decode()[:200]}")
        produced = sorted(out_dir.glob(f"w{width}_*.jpg"))
        if len(produced) != len(group):
            raise EngineError(
                f"asked ffmpeg for {len(group)} frames at {width}px and got {len(produced)}"
            )
        for pick, path in zip(group, produced, strict=True):
            target = out_dir / f"{pick.index:04d}_{pick.role}.jpg"
            path.replace(target)
            written.append(target)
    return sorted(written)


def timing_profile(segments: list[Segment], series: list[tuple[int, float, float]]) -> list[dict]:
    profile: list[dict] = []
    for seg in segments:
        if seg.kind != "transition":
            continue
        stamps = [row[1] for row in series if seg.first <= row[0] <= seg.last]
        gaps = [b - a for a, b in pairwise(stamps)] or [0.0]
        median = statistics.median(gaps)
        profile.append(
            {
                "start": round(seg.start, 3),
                "duration_ms": round(seg.duration * 1000),
                "frames": len(stamps),
                "median_gap_ms": round(median * 1000, 1),
                "max_gap_ms": round(max(gaps) * 1000, 1),
                "implied_fps": round(1 / median, 1) if median > 0 else None,
                "stutters": sum(1 for gap in gaps if median > 0 and gap > 2 * median),
            }
        )
    return profile


def _fallback_picks(meta: dict) -> list[Pick]:
    step = max(1.0, (meta["frames"] or 1) / max(1.0, meta["duration"] * FALLBACK_FPS))
    n = int((meta["frames"] or 1) / step)
    return [
        Pick(
            int(i * step),
            (i * step) / max(1, meta["frames"]) * meta["duration"],
            "sampled",
            0,
            0,
            SETTLED_WIDTH,
            f"uniform sample {i + 1} of {n}",
        )
        for i in range(n)
    ]


def review(video: Path, out_dir: Path) -> dict:
    _require_binaries()
    meta = probe(video)
    series = delta_series(video)
    threshold = move_threshold(series)
    segments = segment(series, threshold)

    moving = sum(s.duration for s in segments if s.kind == "transition")
    span = max(1e-6, sum(s.duration for s in segments))
    continuous = moving / span > CONTINUOUS_MOTION_RATIO

    if continuous:
        picks, dropped = _fallback_picks(meta), 0
    else:
        picks, dropped = dedupe_settled(video, allocate(segments, series, threshold))
    picks = relabel(picks)

    frames = extract(video, picks, out_dir)
    return {
        "source": str(video.resolve()),
        "media": meta,
        "threshold": round(threshold, 4),
        "mode": "uniform-fallback" if continuous else "settle-detection",
        "fallback_reason": (
            "motion covers more than 60% of the timeline — this is not a UI recording"
            if continuous
            else None
        ),
        "settled_states": sum(1 for p in picks if p.role == "settled"),
        "transitions": len({p.group for p in picks if p.role == "transition"}),
        "deduped_settled": dropped,
        "timing": timing_profile(segments, series),
        "frames": [
            {"path": str(path), **asdict(pick)} for pick, path in zip(picks, frames, strict=True)
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the frames worth reviewing from a screen recording."
    )
    parser.add_argument("video", type=Path)
    parser.add_argument(
        "--out", type=Path, required=True, help="directory for the extracted frames"
    )
    parser.add_argument(
        "--json", action="store_true", help="print the report as JSON instead of markdown"
    )
    args = parser.parse_args(argv)

    try:
        report = review(args.video.expanduser().resolve(), args.out.expanduser().resolve())
    except EngineError as exc:
        print(f"motion-review: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print(f"# {Path(report['source']).name}")
    print(
        f"\n{report['media']['frames']} frames · {report['media']['duration']:.2f}s · "
        f"{report['media']['width']}x{report['media']['height']} · mode: {report['mode']}"
    )
    if report["fallback_reason"]:
        print(f"\n> fallback: {report['fallback_reason']}")
    print(
        f"\n{report['settled_states']} settled states · {report['transitions']} transitions"
        f" · {report['deduped_settled']} duplicate states dropped"
    )
    if report["timing"]:
        print("\n## Transition timing")
        for entry in report["timing"]:
            rate = f"{entry['implied_fps']}fps" if entry["implied_fps"] else "rate unknown"
            print(
                f"- t={entry['start']}s · {entry['duration_ms']}ms · {entry['frames']} frames · "
                f"{rate} · {entry['stutters']} stutters"
            )
    print("\n## Frames — Read every path below\n")
    for frame in report["frames"]:
        print(f"- `{frame['path']}` — {frame['label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
