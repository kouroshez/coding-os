"""Parity gate: current `cos init` output must equal committed golden snapshots.

This test is the safety net for the Phase 1 refactor (data-driven stacks).
It fresh-scaffolds every (agent × stack) combination into a temp dir, then
compares the resulting file tree byte-for-byte against `tests/golden/`.

Any drift fails the test with a diff. If the drift is intentional
(template change, new stack, etc.), regenerate the goldens:

    uv run python scripts/capture_golden.py

Runtime files (SQLite DBs, session markers) are excluded on both sides.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"
FIXTURE_NAME = "cos-golden-fixture"
FROZEN_DATE = "2026-01-01"  # must match scripts/capture_golden.py

# Must match scripts/capture_golden.py
SECTIONS: list[tuple[str, str, list[str]]] = [
    ("claude_base", "claude", []),
    ("claude_django", "claude", ["django"]),
    ("claude_nextjs", "claude", ["nextjs"]),
    ("codex_base", "codex", []),
    ("codex_django", "codex", ["django"]),
    ("codex_nextjs", "codex", ["nextjs"]),
]

RUNTIME_PATHS = {
    ".coding-os/thinking_os.db",
    ".coding-os/thinking_os.db-shm",
    ".coding-os/thinking_os.db-wal",
    ".coding-os/session-id",
    ".coding-os/.thinking_os-gate",
    ".coding-os/.task-current",
    ".coding-os/.zoom-checkpoint",
    ".coding-os/.last-verify",
}
IGNORED_PREFIXES = (".git/", "node_modules/", ".venv/", ".build/")


def _scaffold(agent: str, templates: list[str], target: Path) -> None:
    cmd = [
        sys.executable, "-m", "cli.main", "init",
        "--agent", agent,
        "--project-dir", str(target.parent),
        "--name", target.name,
        "--no-git",
        "--force",
        "--today", FROZEN_DATE,
    ]
    for t in templates:
        cmd.extend(["--template", t])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(
        cmd, cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=180, check=True,
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
@pytest.mark.parametrize("section_id,agent,templates", SECTIONS,
                         ids=[s[0] for s in SECTIONS])
def test_parity(section_id: str, agent: str, templates: list[str], tmp_path: Path) -> None:
    golden = GOLDEN_DIR / section_id
    if not golden.exists():
        pytest.skip(
            f"golden {section_id} not captured yet — run "
            f"`uv run python scripts/capture_golden.py --section {section_id}`"
        )

    sandbox = tmp_path / section_id / FIXTURE_NAME
    sandbox.parent.mkdir(parents=True)
    _scaffold(agent, templates, sandbox)

    actual = _collect_tracked(sandbox)
    expected = _collect_tracked(golden)

    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    assert not missing, (
        f"[{section_id}] missing files (in golden, not in fresh scaffold): "
        f"{missing[:10]}"
    )
    assert not extra, (
        f"[{section_id}] extra files (in fresh scaffold, not in golden): "
        f"{extra[:10]} — if intentional, run "
        f"`uv run python scripts/capture_golden.py --section {section_id}`"
    )

    # Byte-identical check for every shared file. Some adapters (codex)
    # bake absolute install paths into generated configs; normalise any
    # absolute path ending in /cos-golden-fixture/... to a sandbox-root
    # placeholder so capture-time vs test-time tmp dirs match.
    anchor_re = re.compile(
        rb"/[^\s\"'`]*?/" + re.escape(FIXTURE_NAME.encode()) + rb"/"
    )

    def _normalise(path: Path) -> bytes:
        return anchor_re.sub(b"__SANDBOX__/", path.read_bytes())

    mismatches: list[str] = []
    for rel in sorted(expected):
        if _normalise(expected[rel]) != _normalise(actual[rel]):
            mismatches.append(rel)
    assert not mismatches, (
        f"[{section_id}] {len(mismatches)} file(s) drifted:\n  " +
        "\n  ".join(mismatches[:15])
    )
