"""File-size ratchet: no tracked Python file may exceed the current ceiling.

The ceiling is the largest file at gate-introduction time (tests/test_cli.py
5652 lines; graph.py 5572). It only goes DOWN: after splitting a god-file,
lower MAX_LINES to the new largest file. Raising it is a review-rejected
change by policy (docs/governance/release-process.md § quality gates).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_LINES = 5700

EXCLUDED_PREFIXES = (
    "src/templates/",  # consumer-shipped scaffold; downstream owns style
    "tests/golden/",  # generated snapshots
    "archive/",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return [
        REPO_ROOT / line
        for line in out.stdout.splitlines()
        if line and not line.startswith(EXCLUDED_PREFIXES)
    ]


def test_no_python_file_exceeds_line_budget() -> None:
    offenders: list[str] = []
    for path in _tracked_python_files():
        try:
            line_count = sum(1 for _ in path.open("rb"))
        except OSError:
            continue  # deleted-but-still-tracked during a rebase; git owns it
        if line_count > MAX_LINES:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: {line_count} lines")
    assert not offenders, (
        f"Files exceed the {MAX_LINES}-line ratchet (split them, never raise the cap):\n"
        + "\n".join(offenders)
    )
