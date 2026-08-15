"""Every `graph.enforce_context_on` glob must match a file that exists.

A glob naming a path that was since renamed matches nothing, and matching
nothing is indistinguishable from "this file is not load-bearing" — three hooks
(`enforce-graph-context`, `enforce-graph-first-read`, `enforce-skill`) then guard
it into silence. Two shipped that way: `thinking_os/db.py` (the file is
`database.py`) and `graph_os/reindex_dispatch.py` (it lives under `tools/`), so
the repo's most-edited module had no graph guard at all.

Same defect shape as tests/test_verification_matrix.py: a self-referential
config whose failure mode reads exactly like a pass.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG = REPO_ROOT / ".coding-os" / "rag-config.yaml"
GIT_TIMEOUT_SECONDS = 30

sys.path.insert(0, str(REPO_ROOT / "src" / "core" / "hooks" / "_helpers"))


def _patterns() -> list[str]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return list((data.get("graph") or {}).get("enforce_context_on") or [])


def _tracked_absolute_paths() -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files"],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        pytest.skip("git ls-files unavailable")
    return [str(REPO_ROOT / line) for line in result.stdout.splitlines() if line]


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    return _tracked_absolute_paths()


def test_config_declares_globs() -> None:
    """An empty list would make the dead-glob test vacuously green."""
    assert _patterns(), f"{CONFIG} declares no enforce_context_on globs"


def test_no_glob_matches_nothing(tracked: list[str]) -> None:
    dead = [
        pattern
        for pattern in _patterns()
        if not any(fnmatch.fnmatchcase(path, pattern) for path in tracked)
    ]
    assert not dead, (
        f"enforce_context_on globs matching no tracked file: {dead} — "
        "a renamed target silently disables the graph guard on it"
    )


def test_matcher_agrees_with_the_hook(tracked: list[str]) -> None:
    """Bind this test to the hook's own matcher, not a re-implementation."""
    from graph_context_match import matches

    for pattern in _patterns():
        hit = next(
            (path for path in tracked if fnmatch.fnmatchcase(path, pattern)),
            None,
        )
        assert hit is not None, f"no tracked file for {pattern}"
        assert matches(str(CONFIG), hit), f"hook matcher rejects {hit} for {pattern}"
