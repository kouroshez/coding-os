"""board↔git coherence detection (TASK-436).

Every DB task row's `docs/tasks/*.md` must be git-tracked & committed, else the
board (DB) and the filesystem/git have silently diverged. This pure detector is
shared by three persona-independent surfaces (TASK-432 only covered the first):
the `cos doctor` board check (P1/P3 agent), the nightly cron task-filer (P4/P5/P7
human/chat), and the CI gate (P6). Lives in core/ with no cli import so all three
can consume it without a core→cli dependency.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitDriftResult:
    is_git_root: bool
    checked: int
    untracked: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    skip_reason: str | None = None
    git_unavailable: bool = False

    @property
    def has_drift(self) -> bool:
        return bool(self.untracked or self.modified or self.missing)

    def summary(self) -> str:
        return (
            f"board↔git drift — {len(self.untracked)} untracked, "
            f"{len(self.modified)} modified, {len(self.missing)} missing .md "
            "(DB row without a committed file)"
        )


def detect_board_git_drift(project: Path, rows: list[tuple[str, str]]) -> GitDriftResult:
    """Compute board↔git drift for (task_id, file_path) rows — git is the only I/O."""
    project = Path(project)
    try:
        top = subprocess.run(
            ["git", "-C", str(project), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GitDriftResult(
            is_git_root=False, checked=0, skip_reason=f"git unavailable ({exc})", git_unavailable=True
        )
    if top.returncode != 0 or Path(top.stdout.strip() or ".").resolve() != project.resolve():
        return GitDriftResult(is_git_root=False, checked=0, skip_reason="not a git work-tree root")

    if not rows:
        return GitDriftResult(is_git_root=True, checked=0)

    try:
        proc = subprocess.run(
            # --untracked-files=all so a fully-untracked docs/tasks/ lists each
            # file (git collapses an all-untracked dir to one "?? docs/tasks/" line).
            ["git", "-C", str(project), "status", "--porcelain", "--untracked-files=all", "-z", "--", "docs/tasks"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return GitDriftResult(
            is_git_root=True, checked=len(rows), skip_reason=f"git status failed ({exc})"
        )

    status_by_path = {rec[3:]: rec[:2] for rec in proc.stdout.split("\0") if len(rec) > 3}
    result = GitDriftResult(is_git_root=True, checked=len(rows))
    for task_id, file_path in rows:
        if not (project / file_path).exists():
            result.missing.append(task_id)
            continue
        code = status_by_path.get(file_path)
        if code is None:
            continue  # tracked & clean
        (result.untracked if code == "??" else result.modified).append(task_id)
    return result


def task_rows_from_db(conn) -> list[tuple[str, str]]:
    """(task_id, file_path) for every DB task row that names a file — shared query."""
    return [
        (r[0], r[1])
        for r in conn.execute(
            "SELECT task_id, file_path FROM tasks WHERE file_path IS NOT NULL AND file_path != ''"
        ).fetchall()
    ]
