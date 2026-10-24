#!/usr/bin/env python3
"""Every call out to ffmpeg, and the parsing of what it says back."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

PROFILE_SIZE = 64
CHROMA_WEIGHT = 0.5

_META = re.compile(r"^frame:(\d+)\s+pts:\S+\s+pts_time:([0-9.]+)")
_STAT = re.compile(r"lavfi\.signalstats\.([YUV]AVG)=([0-9.]+)")


class EngineError(RuntimeError):
    pass


def _run(cmd: list[str], *, capture_stdout: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )


def require_binaries() -> None:
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


def sample_rgb(video: Path, indices: list[int], size: int) -> list[bytes]:
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


def extract_indices(video: Path, indices: list[int], width: int, pattern: Path) -> None:
    selector = "+".join(rf"eq(n\,{index})" for index in indices)
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
