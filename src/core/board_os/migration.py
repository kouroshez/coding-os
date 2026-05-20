"""Phase L.7 — One-shot migration from legacy 12-section to lean frontmatter.

Two-phase atomic (R-L-27):
  Phase 0 — backup all docs/tasks/*.md → tar.gz
  Phase 1 — parse all files into staging dir; abort on any failure
  Phase 2 — atomic rename staging → final; originals → archive/pre-l/
  Phase 3 — git add + commit (optional)

Idempotent: files with lean frontmatter are skipped.
Resumable: --resume picks up a partially-validated staging dir.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tarfile
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from board_os.parser import ParsedTask, is_lean_format, parse_task

logger = logging.getLogger("coding_os.board_os.migration")


_LEGACY_STATUS_MAP = {
    "open": "ready",
    "wip": "in_progress",
    "done": "complete",
    "blocked": "blocked",
}


@dataclass
class MigrationReport:
    scanned: int = 0
    already_lean: int = 0
    migrated: int = 0
    skipped_unparseable: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        self.errors = self.errors or []


def _render_lean_from_legacy(legacy: ParsedTask, domain_map: dict | None) -> str:
    """Convert a legacy ParsedTask into a Phase L lean MD file string."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    swimlane = legacy.swimlane or "core"
    kind = "chore"  # safe default; user tunes after migration
    priority = "P2"
    appetite = "1d"

    fm_lines = [
        "---",
        f"id: {legacy.task_id}",
        f'title: "{legacy.title}"',
        f"swimlane: {swimlane}",
        f"kind: {kind}",
        "epic: null",
        "labels: [migrated-from-legacy]",
        f"status: {legacy.status}",
        f"priority: {priority}",
        f'appetite: "{appetite}"',
        f"created: {today}",
        "started: null",
        "completed: null",
        "agent_session: null",
        f"depends_on: [{', '.join(legacy.depends_on)}]",
        "blocked_by: []",
        "references: []",
        "---",
    ]
    body = [
        "",
        f"# {legacy.task_id}: {legacy.title}",
        "",
        "**Outcome (one sentence):** (migrated from legacy format — review and refine)",
        "",
        "## Read First",
        "- (no doc yet — see archive/pre-l/ for original content)",
        "",
        "## Acceptance (G/W/T) — *this IS the Definition of Done*",
        "- **Given** ... (fill in from original Verification section)",
        "- **When** ...",
        "- **Then** ...",
        "",
        "## Work Log",
        "",
        "## Rollback",
        "Revert commit. Original content preserved in docs/tasks/archive/pre-l/.",
        "",
    ]
    return "\n".join(fm_lines) + "\n".join(body)


def migrate(
    project_root: Path,
    *,
    dry_run: bool = True,
    resume: bool = False,
) -> MigrationReport:
    report = MigrationReport()
    tasks_dir = (project_root / "docs" / "tasks").resolve()
    if not tasks_dir.exists():
        return report

    staging_dir = project_root / ".coding-os" / "migration-staging"
    archive_dir = project_root / "docs" / "tasks" / "archive" / "pre-l"

    if not resume and staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    # Phase 0: backup (skip on dry-run).
    if not dry_run:
        ts = time.strftime("%Y-%m-%d-%H%M%S")
        backup_path = project_root / ".coding-os" / f"migration-backup-{ts}.tar.gz"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(backup_path, "w:gz") as tar:
            for p in tasks_dir.glob("TASK-*.md"):
                tar.add(p, arcname=f"docs/tasks/{p.name}")
        logger.info("backup written: %s", backup_path)

    # Phase 1: validate all → staging.
    files = sorted(tasks_dir.glob("TASK-*.md"))
    for src in files:
        report.scanned += 1
        content = src.read_text(encoding="utf-8")
        if is_lean_format(content):
            report.already_lean += 1
            continue
        parsed = parse_task(content, path=src)
        if parsed is None:
            report.skipped_unparseable += 1
            report.errors.append(f"{src.name}: unparseable (legacy + lean both failed)")
            continue

        lean = _render_lean_from_legacy(parsed, domain_map=None)
        (staging_dir / src.name).write_text(lean, encoding="utf-8")
        report.migrated += 1

    if dry_run:
        return report

    if report.errors:
        # Abort — Phase 1 failure means no writes to final paths.
        shutil.rmtree(staging_dir, ignore_errors=True)
        logger.warning("migration aborted: %d errors", len(report.errors))
        return report

    # Phase 2: atomic rename staging → final.
    archive_dir.mkdir(parents=True, exist_ok=True)
    for src in files:
        staged = staging_dir / src.name
        if not staged.exists():
            continue  # already-lean or unparseable → skipped
        # Move original to archive/pre-l/ first.
        dest_archive = archive_dir / src.name
        if dest_archive.exists():
            dest_archive.unlink()
        shutil.copy2(src, dest_archive)
        # Atomic rename: staging → final.
        os.replace(staged, src)

    # Cleanup staging.
    shutil.rmtree(staging_dir, ignore_errors=True)
    return report
