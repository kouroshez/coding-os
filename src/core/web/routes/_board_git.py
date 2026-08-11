"""core.web.routes._board_git — read-only commit and diff views for a task's history."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import Depends, Query
from fastapi.responses import JSONResponse

from .._deps import make_metrics_dep, make_rate_limit_dep
from ._board_shared import router

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_TASK_FILE_RE = re.compile(r"docs/tasks/(TASK-\d+)-")


def _is_other_task_file(path: str, for_task: str) -> bool:
    # A docs/tasks/TASK-NNN-*.md belonging to a DIFFERENT task than for_task — so
    # one task's HISTORY never shows a batched commit's sibling-task files.
    m = _TASK_FILE_RE.search(path)
    return bool(m) and m.group(1) != for_task


def _run_git(args: list[str], cwd: Path, timeout: float = 8.0) -> tuple[int, str]:
    """Run a read-only git command; fail-open to (1, '') — never 500 the panel."""
    import subprocess

    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout or ""
    except Exception as exc:
        logging.getLogger("coding_os.web.board").debug("git %s failed: %s", args[:2], exc)
        return 1, ""


@router.get("/commit/{sha}")
def board_commit(
    sha: str,
    for_task: str | None = Query(None),
    _rl=Depends(make_rate_limit_dep("board.commit")),
    _m=Depends(make_metrics_dep("board.commit")),
):
    """List the files changed in one commit (numstat) — read-only."""
    if not _SHA_RE.match(sha):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid sha"}},
        )
    from web._project_context import current_project_root

    root = current_project_root()
    rc, out = _run_git(
        ["show", "--no-color", "--numstat", "--format=%H%x00%an%x00%aI%x00%s", sha], root
    )
    if rc != 0 or not out.strip():
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"commit {sha} not found"}},
        )
    header, _, body = out.partition("\n")
    parts = ([*header.split("\x00"), "", "", "", ""])[:4]
    full_sha, author, date, subject = parts
    files = []
    for line in body.splitlines():
        cols = line.strip().split("\t")
        if len(cols) != 3:
            continue
        added, removed, path = cols
        files.append(
            {
                "path": path,
                "added": None if added == "-" else int(added),
                "removed": None if removed == "-" else int(removed),
                "binary": added == "-" and removed == "-",
            }
        )
    # Under one task's HISTORY, drop OTHER tasks' TASK-*.md so a batched commit
    # doesn't leak sibling-task files into this task's view (keeps own + code).
    if for_task and re.fullmatch(r"TASK-\d+", for_task):
        files = [f for f in files if not _is_other_task_file(f["path"], for_task)]
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "sha": full_sha or sha,
                "subject": subject,
                "author": author,
                "date": date,
                "files": files,
            },
            "meta": {"layer": "tasks", "source": "web.board_commit"},
        },
    )


@router.get("/diff")
def board_diff(
    sha: str = Query(...),
    file: str = Query(...),
    _rl=Depends(make_rate_limit_dep("board.diff")),
    _m=Depends(make_metrics_dep("board.diff")),
):
    """Unified diff for one file at one commit — read-only, repo-sandboxed."""
    if not _SHA_RE.match(sha):
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "invalid sha"}},
        )
    from web._project_context import current_project_root

    root = current_project_root().resolve()
    try:
        rel = (root / file).resolve().relative_to(root)
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": {"category": "validation", "message": "file outside repo"}},
        )
    rc, out = _run_git(["show", "--no-color", "--format=", sha, "--", str(rel)], root)
    if rc != 0:
        return JSONResponse(
            status_code=404,
            content={"error": {"category": "not_found", "message": f"commit {sha} not found"}},
        )
    max_bytes = 200 * 1024
    truncated = len(out) > max_bytes
    diff_text = out[:max_bytes] if truncated else out
    lines = diff_text.splitlines()
    added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
    removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
    return JSONResponse(
        status_code=200,
        content={
            "data": {
                "sha": sha,
                "file": str(rel),
                "diff": diff_text,
                "added": added,
                "removed": removed,
                "truncated": truncated,
            },
            "meta": {"layer": "tasks", "source": "web.board_diff"},
        },
    )
