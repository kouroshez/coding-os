"""Parity gate: current `cos init` output must equal committed golden snapshots.

This test is the safety net for the Phase 1 refactor (data-driven stacks).
It fresh-scaffolds every (agent × stack) combination into a temp dir, then
compares the resulting file tree byte-for-byte against `tests/golden/`.

Any drift fails the test with a diff. If the drift is intentional
(template change, new stack, etc.), regenerate the goldens:

    uv run python src/scripts/capture_golden.py

Runtime files (SQLite DBs, session markers) are excluded on both sides.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_sections import SECTIONS

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
FIXTURE_NAME = "cos-golden-fixture"
FROZEN_DATE = "2026-01-01"  # must match src/scripts/capture_golden.py

RUNTIME_PATHS = {
    # Deterministic permission allowlist cos init writes, but .gitignore keeps
    # it out of the committed fixture; verified by the manifest/doctor layer
    # (scaffold.manifest_fresh), not by golden parity. (TASK-513)
    ".claude/settings.local.json",
}
IGNORED_PREFIXES = (
    ".git/",
    "node_modules/",
    ".venv/",
    ".build/",
    # Tool caches a scaffold-time lint/format pass may leave behind; gitignored
    # in the scaffold, so they never reach the committed golden tree.
    ".ruff_cache/",
    ".pytest_cache/",
    ".mypy_cache/",
    # The whole .coding-os/ project-state dir is gitignored (DBs, session
    # markers, the wall-clock core-version.json, plus deterministic config and
    # the local stack copy under .coding-os/src/). None of it lands in the
    # committed golden tree, so on a fresh clone it would false-fail parity as
    # "extra in fresh". Its config is verified instead by the manifest/doctor
    # layer; excluding it here keeps the path-set comparison clean. (TASK-513)
    ".coding-os/",
)


def _scaffold(agent: str, templates: list[str], target: Path) -> None:
    cmd = [
        sys.executable,
        "-m",
        "cli.main",
        "init",
        "--agent",
        agent,
        "--project-dir",
        str(target.parent),
        "--name",
        target.name,
        "--no-git",
        "--force",
        "--no-register",
        # Pin the full module surface to match capture_golden so a default-profile
        # flip never breaks parity (TASK-509); per-profile scaffolds tested apart.
        "--profile",
        "full",
        # Parity compares scaffold structure; the doc index lives in the
        # gitignored runtime DB. Skip it to match capture_golden + drop the
        # ~15s embedding load per section.
        "--no-index",
        "--today",
        FROZEN_DATE,
    ]
    for t in templates:
        cmd.extend(["--template", t])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )


def _collect_tracked(root: Path) -> dict[str, Path]:
    """Return {rel_path: abs_path} excluding runtime + ignored prefixes."""
    result: dict[str, Path] = {}
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(root).as_posix()
        if rel in RUNTIME_PATHS:
            continue
        if any(rel.startswith(p) for p in IGNORED_PREFIXES):
            continue
        result[rel] = f
    return result


@pytest.mark.slow
@pytest.mark.parametrize("section_id,agent,templates", SECTIONS, ids=[s[0] for s in SECTIONS])
def test_parity(section_id: str, agent: str, templates: list[str], tmp_path: Path) -> None:
    golden = GOLDEN_DIR / section_id
    if not golden.exists():
        pytest.skip(
            f"golden {section_id} not captured yet — run `make golden-capture SECTION={section_id}`"
        )

    sandbox = tmp_path / section_id / FIXTURE_NAME
    sandbox.parent.mkdir(parents=True)
    _scaffold(agent, templates, sandbox)

    actual = _collect_tracked(sandbox)
    expected = _collect_tracked(golden)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    assert not missing, (
        f"[{section_id}] missing files (in golden, not in fresh scaffold): {missing[:10]}"
    )
    assert not extra, (
        f"[{section_id}] extra files (in fresh scaffold, not in golden): "
        f"{extra[:10]} — if intentional, run "
        f"`make golden-capture SECTION={section_id}`"
    )

    # Byte-identical check for every shared file. Some adapters (codex)
    # bake absolute install paths into generated configs; normalise any
    # absolute path ending in /cos-golden-fixture/... to a sandbox-root
    # placeholder so capture-time vs test-time tmp dirs match.
    anchor_re = re.compile(rb"/[^\s\"'`]*?/" + re.escape(FIXTURE_NAME.encode()) + rb"/")

    def _normalise(path: Path) -> bytes:
        return anchor_re.sub(b"__SANDBOX__/", path.read_bytes())

    mismatches: list[str] = []
    for rel in sorted(expected):
        if _normalise(expected[rel]) != _normalise(actual[rel]):
            mismatches.append(rel)
    assert not mismatches, f"[{section_id}] {len(mismatches)} file(s) drifted:\n  " + "\n  ".join(
        mismatches[:15]
    )
