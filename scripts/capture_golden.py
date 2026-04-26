#!/usr/bin/env python3
"""Capture golden snapshots of `cos init` output for every (agent × stack).

Writes to `tests/golden/<section_id>/` where section_id mirrors the
manifest naming (claude_base, claude_django, claude_nextjs, codex_*).

Runtime state files (listed below) are excluded so that repeated captures
produce byte-identical output.

Usage:
    uv run python scripts/capture_golden.py           # refresh all sections
    uv run python scripts/capture_golden.py --section claude_base
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

# Mirrors generate_manifest.SECTIONS for now (Phase 1 will make both dynamic).
SECTIONS: list[tuple[str, str, list[str]]] = [
    ("claude_base", "claude", []),
    ("claude_django", "claude", ["django"]),
    ("claude_nextjs", "claude", ["nextjs"]),
    ("claude_go-fiber", "claude", ["go-fiber"]),
    ("codex_base", "codex", []),
    ("codex_django", "codex", ["django"]),
    ("codex_nextjs", "codex", ["nextjs"]),
    ("codex_go-fiber", "codex", ["go-fiber"]),
]

# Files created at runtime — never tracked in golden.
# Must match cli/doctor.py::RUNTIME_PATHS.
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

FIXTURE_NAME = "cos-golden-fixture"
FROZEN_DATE = "2026-01-01"  # passed to `cos init --today` for determinism


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
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )


def _copy_filtered(src_root: Path, dst_root: Path) -> int:
    """Copy files from src to dst, skipping runtime/ignored paths. Return count."""
    if dst_root.exists():
        shutil.rmtree(dst_root)
    dst_root.mkdir(parents=True)
    count = 0
    for f in sorted(src_root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(src_root).as_posix()
        if rel in RUNTIME_PATHS:
            continue
        if any(rel.startswith(p) for p in IGNORED_PREFIXES):
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dst)
        count += 1
    return count


@click.command()
@click.option("--section", default=None, help="Only capture a specific section id.")
def main(section: str | None) -> None:
    targets = [s for s in SECTIONS if section is None or s[0] == section]
    if not targets:
        click.echo(f"No matching section: {section}", err=True)
        sys.exit(2)

    with tempfile.TemporaryDirectory(prefix="cos-golden-") as tmp:
        tmp_dir = Path(tmp)
        for section_id, agent, templates in targets:
            sandbox_parent = tmp_dir / section_id
            sandbox_parent.mkdir(parents=True)
            sandbox = sandbox_parent / FIXTURE_NAME
            try:
                _scaffold(agent, templates, sandbox)
            except subprocess.CalledProcessError as exc:
                click.echo(
                    f"[golden] {section_id}: init failed\n{exc.stderr}",
                    err=True,
                )
                sys.exit(1)
            dst = GOLDEN_DIR / section_id
            count = _copy_filtered(sandbox, dst)
            click.echo(f"[golden] {section_id}: {count} files → {dst.relative_to(REPO_ROOT)}")

    click.echo(f"\n[golden] wrote {len(targets)} section(s) to {GOLDEN_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
