#!/usr/bin/env python3
"""Report whether this host can capture and read a recording. Installs nothing."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REQUIRED = ("ffmpeg", "ffprobe")
OPTIONAL = {
    "yt-dlp": "fetch a video by URL",
    "xcrun": "record an iOS simulator",
    "adb": "record an Android emulator",
}


def _version(binary: str) -> str:
    flag = "--version" if binary != "xcrun" else "--help"
    try:
        result = subprocess.run(
            [binary, flag],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "present"
    first = (result.stdout or b"").decode(errors="replace").splitlines()
    return first[0].strip()[:60] if first else "present"


def _playwright_recorder() -> tuple[bool, str]:
    # Playwright records video with its OWN bundled ffmpeg; the system one does
    # not satisfy it, and its absence surfaces as a page-creation failure.
    root = Path.home() / "Library" / "Caches" / "ms-playwright"
    if not root.exists():
        root = Path.home() / ".cache" / "ms-playwright"
    if not root.exists():
        return False, "no playwright browser cache on this host"
    found = sorted(root.glob("ffmpeg-*"))
    if not found:
        return False, "run: python -m playwright install ffmpeg"
    return True, found[-1].name


def check() -> dict:
    report: dict = {"required": {}, "optional": {}, "capabilities": {}}
    for binary in REQUIRED:
        path = shutil.which(binary)
        report["required"][binary] = {
            "present": bool(path),
            "detail": _version(binary) if path else "missing",
        }
    for binary, purpose in OPTIONAL.items():
        path = shutil.which(binary)
        report["optional"][binary] = {
            "present": bool(path),
            "purpose": purpose,
            "detail": _version(binary) if path else "missing",
        }

    playwright_ok, playwright_detail = _playwright_recorder()
    report["optional"]["playwright-ffmpeg"] = {
        "present": playwright_ok,
        "purpose": "record a web page",
        "detail": playwright_detail,
    }

    engine = all(entry["present"] for entry in report["required"].values())
    report["capabilities"] = {
        "read a recording": engine,
        "record iOS": report["optional"]["xcrun"]["present"],
        "record Android": report["optional"]["adb"]["present"],
        "record web": playwright_ok,
        "fetch by URL": report["optional"]["yt-dlp"]["present"],
    }
    report["can_proceed"] = engine
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight the host for motion-review.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--quiet", action="store_true", help="print nothing; the exit code is the answer"
    )
    args = parser.parse_args(argv)

    report = check()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["can_proceed"] else 2
    if args.quiet:
        return 0 if report["can_proceed"] else 2

    print("motion-review — host check\n")
    for binary, entry in report["required"].items():
        mark = "ok  " if entry["present"] else "MISSING"
        print(f"  [{mark}] {binary:18} {entry['detail']}")
    print()
    for binary, entry in report["optional"].items():
        mark = "ok  " if entry["present"] else "--  "
        print(f"  [{mark}] {binary:18} {entry['purpose']:26} {entry['detail']}")
    print("\n  what this host can do:")
    for name, able in report["capabilities"].items():
        print(f"    {'yes' if able else 'no '}  {name}")

    if not report["can_proceed"]:
        print("\n  ffmpeg is required. macOS: brew install ffmpeg", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
