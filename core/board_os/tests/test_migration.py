"""L.7 round-trip test — legacy 12-section → lean frontmatter migration.

Fixtures:
  - Builds a synthetic 50-task legacy repo in a tmp dir.
  - Runs `migrate(dry_run=False)`.
  - Verifies: (a) all 50 files have valid lean frontmatter after apply,
    (b) originals archived to docs/tasks/archive/pre-l/, (c) tar.gz
    backup exists, (d) running migrate() again is a no-op.

Also covers:
  - dry-run writes no files
  - single broken file aborts the whole run (Phase-1 abort test, R-L-27)
  - idempotent re-run on already-lean files
"""

from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from core.board_os.migration import migrate
from core.board_os.parser import is_lean_format, parse_task


_LEGACY_TEMPLATE = """<!-- domain:{domain} | layer:task | ssot:true | updated:2026-01-01 -->
# {task_id}: [{domain}] Legacy task {n}

Purpose: Synthetic migration fixture.
Read when: Legacy task migration test.

- Created: 2026-01-01

## Goal
Legacy goal for {task_id}.

## Read First
- REF:PLAYBOOK-{domain}

## Source of Truth
- docs/prd/{domain_lower}.md

## Scope
### In
- one thing
### Out
- other thing

## Requirements
- must work

## Dependencies
{deps_block}

## Open Questions
- none

## Rabbit Holes
- none

## Verification
- make test
"""


def _build_legacy_repo(
    root: Path, count: int, *, with_broken: bool = False,
) -> None:
    (root / "docs" / "tasks").mkdir(parents=True)
    for i in range(1, count + 1):
        task_id = f"TASK-{i:03d}"
        domain = "BACKEND" if i % 2 == 0 else "FRONTEND"
        deps_block = ""
        if i > 1:
            prev = f"TASK-{i-1:03d}"
            deps_block = f"- {prev}"
        content = _LEGACY_TEMPLATE.format(
            task_id=task_id, n=i, domain=domain,
            domain_lower=domain.lower(),
            deps_block=deps_block,
        )
        slug = f"legacy-task-{i}"
        (root / "docs" / "tasks" / f"{task_id}-{slug}.md").write_text(
            content, encoding="utf-8",
        )

    if with_broken:
        # Deliberately unparseable (no H1 match).
        (root / "docs" / "tasks" / "TASK-999-broken.md").write_text(
            "this file has no proper H1 and no frontmatter\n" * 3,
            encoding="utf-8",
        )


def test_dry_run_writes_nothing(tmp_path: Path):
    _build_legacy_repo(tmp_path, count=5)
    before = {
        p.read_text(encoding="utf-8")
        for p in (tmp_path / "docs" / "tasks").glob("TASK-*.md")
    }
    report = migrate(tmp_path, dry_run=True)
    after = {
        p.read_text(encoding="utf-8")
        for p in (tmp_path / "docs" / "tasks").glob("TASK-*.md")
    }
    assert before == after, "dry_run mutated files"
    assert report.scanned == 5
    assert report.migrated == 5  # would-migrate count
    # No archive / backup on dry-run.
    assert not (tmp_path / "docs" / "tasks" / "archive").exists()
    backups = list((tmp_path / ".coding-os").glob("migration-backup-*.tar.gz")) \
        if (tmp_path / ".coding-os").exists() else []
    assert not backups


def test_apply_round_trip_50_tasks(tmp_path: Path):
    _build_legacy_repo(tmp_path, count=50)

    report = migrate(tmp_path, dry_run=False)

    assert report.scanned == 50
    assert report.migrated == 50
    assert report.errors == []

    # Every file is now lean + parseable.
    for p in sorted((tmp_path / "docs" / "tasks").glob("TASK-*.md")):
        content = p.read_text(encoding="utf-8")
        assert is_lean_format(content), f"{p.name} not lean"
        parsed = parse_task(content, path=p)
        assert parsed is not None
        assert parsed.is_lean
        assert parsed.task_id == p.name.split("-")[0] + "-" + p.name.split("-")[1]

    # Archive has all 50 originals.
    archive = tmp_path / "docs" / "tasks" / "archive" / "pre-l"
    assert archive.exists()
    archived = list(archive.glob("TASK-*.md"))
    assert len(archived) == 50

    # Backup tar.gz exists.
    backups = list((tmp_path / ".coding-os").glob("migration-backup-*.tar.gz"))
    assert len(backups) == 1
    with tarfile.open(backups[0], "r:gz") as tf:
        members = tf.getnames()
        assert len([m for m in members if m.startswith("docs/tasks/")]) == 50


def test_idempotent_second_run_is_noop(tmp_path: Path):
    _build_legacy_repo(tmp_path, count=3)
    report1 = migrate(tmp_path, dry_run=False)
    assert report1.migrated == 3

    report2 = migrate(tmp_path, dry_run=False)
    # After a full apply, files are already lean → no migrations.
    assert report2.already_lean == 3
    assert report2.migrated == 0


def test_broken_file_aborts_phase_one(tmp_path: Path):
    """R-L-27: one broken file aborts the whole migration; no final writes."""
    _build_legacy_repo(tmp_path, count=5, with_broken=True)

    before_files = sorted(
        p.name for p in (tmp_path / "docs" / "tasks").glob("TASK-*.md")
    )
    report = migrate(tmp_path, dry_run=False)

    # At least one error reported.
    assert report.errors, "expected broken-file error"
    # No final writes — original files unchanged + no archive rename happened.
    after_files = sorted(
        p.name for p in (tmp_path / "docs" / "tasks").glob("TASK-*.md")
    )
    assert before_files == after_files
    # Verify the 5 real files are STILL in legacy format (not migrated).
    legacy_still = 0
    for p in (tmp_path / "docs" / "tasks").glob("TASK-*.md"):
        if p.name == "TASK-999-broken.md":
            continue
        content = p.read_text(encoding="utf-8")
        if not is_lean_format(content):
            legacy_still += 1
    assert legacy_still == 5


def test_empty_docs_tasks_dir(tmp_path: Path):
    (tmp_path / "docs" / "tasks").mkdir(parents=True)
    report = migrate(tmp_path, dry_run=False)
    assert report.scanned == 0
    assert report.migrated == 0


def test_missing_docs_tasks_dir(tmp_path: Path):
    report = migrate(tmp_path, dry_run=False)
    assert report.scanned == 0
    assert report.migrated == 0


@pytest.mark.parametrize("count", [1, 10, 50])
def test_round_trip_scales(tmp_path: Path, count: int):
    _build_legacy_repo(tmp_path, count=count)
    report = migrate(tmp_path, dry_run=False)
    assert report.migrated == count
    assert report.errors == []
