"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

The three git sources a task history draws commits from: commits that touched
the task file, commits whose message names the task id, and commits whose SHA
appears in the Work Log. Pure git plumbing — no DB, no envelope.
"""

from __future__ import annotations

from pathlib import Path

from ._mcp_shared import (
    _project_root,
    logger,
)


def _git_commits_for_path(rel_path: str, *, limit: int = 50) -> list[dict]:
    import subprocess

    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"-n{limit}",
                "--format=%H%x1f%ct%x1f%s",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log failed for %s: %s", rel_path, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


def _git_commits_by_task_id(task_id: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Actor-agnostic retroactive link: matches commits by message regardless of
    # source (Hub/terminal/human), without session state or a touch of the .md.
    # The `([^0-9]|$)` guard stops TASK-5 matching TASK-50.
    import subprocess

    if not task_id:
        return []
    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--all",
                "-E",
                f"-n{limit}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--format=%H%x1f%ct%x1f%s",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --grep failed for %s: %s", task_id, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        if sha[:10] in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


def _git_commits_from_worklog(rel_path: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Links work-log SHAs that never touched the .md. Validated in ONE indexed
    # `git cat-file` batch (only type `commit` survives) instead of a per-token
    # `git show` that can stall the loop and false-match a date↔short-sha collision.
    import re as _re
    import subprocess

    root = _project_root()
    try:
        text = (Path(root) / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    cands: list[str] = []
    seen: set[str] = set()
    for cand in _re.findall(r"\b[0-9a-f]{7,40}\b", text):
        if cand in seen:
            continue
        seen.add(cand)
        cands.append(cand)
        if len(cands) >= limit:
            break
    if not cands:
        return []

    try:
        batch = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch-check"],
            input="\n".join(cands),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git cat-file failed for %s: %s", rel_path, exc)
        return []
    if batch.returncode != 0:
        return []

    # Hit line: "<full-objectname> <type> <size>". Miss/ambiguous line:
    # "<input> missing" / "<input> ambiguous" — type slot is not "commit".
    commit_shas = [
        parts[0]
        for parts in (line.split() for line in batch.stdout.splitlines())
        if len(parts) >= 2 and parts[1] == "commit"
    ]
    if not commit_shas:
        return []

    try:
        res = subprocess.run(
            ["git", "-C", str(root), "log", "--no-walk", "--format=%H%x1f%ct%x1f%s", *commit_shas],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --no-walk failed for %s: %s", rel_path, exc)
        return []
    if res.returncode != 0:
        return []

    out: list[dict] = []
    for raw in res.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        full, ct, subject = parts
        short = full[:10]
        if short in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        out.append({"sha": short, "subject": subject, "at": at})
        exclude.add(short)
    return out
