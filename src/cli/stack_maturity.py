"""Which stacks CI actually builds, derived from the scaffold-verify matrix.

Advertised must mean CI-proven. Recording that per stack in `stack.yaml` would
make it a second hand-maintained fact that drifts from the workflow the moment
a job is added or removed — the exact failure this module exists to prevent.
So the workflow IS the source: a stack is `verified` when it appears in a
scaffold-verify job matrix, `experimental` otherwise.

When the workflow cannot be read (an installed wheel ships no .github/), every
stack reports `unknown` and callers render nothing — an absent claim, never a
false one.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

VERIFIED = "verified"
EXPERIMENTAL = "experimental"
UNKNOWN = "unknown"

_WORKFLOW = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows"


def _matrix_entries(job: dict) -> list:
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    entries: list = []
    for key, value in matrix.items():
        if key in {"include", "exclude", "fail-fast"} or not isinstance(value, list):
            continue
        entries.extend(value)
    entries.extend(matrix.get("include") or [])
    return entries


@lru_cache(maxsize=1)
def verified_stacks(workflow_dir: Path | None = None) -> frozenset[str]:
    """Stack ids that a scaffold-verify job really scaffolds and tests."""
    path = (workflow_dir or _WORKFLOW) / "scaffold-verify.yml"
    try:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return frozenset()

    found: set[str] = set()
    for job in (workflow or {}).get("jobs", {}).values():
        if not isinstance(job, dict):
            continue
        for entry in _matrix_entries(job):
            if isinstance(entry, str):
                found.add(entry)
            elif isinstance(entry, dict) and isinstance(entry.get("stack"), str):
                found.add(entry["stack"])
    return frozenset(found)


def maturity_of(stack_id: str, workflow_dir: Path | None = None) -> str:
    verified = verified_stacks(workflow_dir)
    if not verified:
        return UNKNOWN
    return VERIFIED if stack_id in verified else EXPERIMENTAL
