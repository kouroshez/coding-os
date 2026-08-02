"""Behavior tests for block-shared-tree-edit.sh — pr-mode worktree edit isolation (TASK-516).

In COS_GIT_WORKFLOW=pr, Write/Edit on a file inside the shared integration
checkout is BLOCKED (forces work into a worktree); worktree files and
out-of-repo files pass; in trunk mode the hook is inert.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = (
    Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "block-shared-tree-edit.sh"
)


def _run(
    file_path: str, *, workflow: str | None, state_dir: str, tool: str = "Write"
) -> tuple[int, str]:
    drop = {"COS_GIT_WORKFLOW", "COS_STATE_DIR", "COS_WORKTREE_ROOT"}
    env = {k: v for k, v in os.environ.items() if k not in drop}
    if workflow is not None:
        env["COS_GIT_WORKFLOW"] = workflow
    env["COS_STATE_DIR"] = state_dir
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_name": tool, "tool_input": {"file_path": file_path}}),
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    return proc.returncode, proc.stderr


def _repo(tmp_path: Path) -> tuple[str, str]:
    repo = tmp_path / "repo"
    state = repo / ".coding-os"
    state.mkdir(parents=True)
    return str(repo), str(state)


def test_blocks_edit_on_shared_checkout_in_pr_mode(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    code, err = _run(f"{repo}/src/app.py", workflow="pr", state_dir=state)
    assert code == 2
    assert "worktree" in err.lower()


def test_blocks_edit_via_symlinked_repo_path_in_pr_mode(tmp_path: Path) -> None:
    # finding 3 (Rule 5): REPO_ROOT resolves symlinks, so a file arriving via a
    # symlinked parent (macOS /tmp → /private/tmp) must still be blocked.
    real = tmp_path / "realrepo"
    (real / ".coding-os").mkdir(parents=True)
    (real / "src").mkdir(parents=True)
    link = tmp_path / "linkrepo"
    link.symlink_to(real)
    code, err = _run(f"{link}/src/app.py", workflow="pr", state_dir=str(real / ".coding-os"))
    assert code == 2
    assert "worktree" in err.lower()


def test_allows_edit_in_worktree_in_pr_mode(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    wt_file = f"{tmp_path}/.coding-os/worktrees/slug/wt/src/app.py"
    code, _ = _run(wt_file, workflow="pr", state_dir=state)
    assert code == 0


def test_allows_edit_outside_repo_in_pr_mode(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    other = tmp_path / "scratch" / "note.txt"
    other.parent.mkdir(parents=True)
    code, _ = _run(str(other), workflow="pr", state_dir=state)
    assert code == 0


def test_inert_in_trunk_mode(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    code, _ = _run(f"{repo}/src/app.py", workflow=None, state_dir=state)
    assert code == 0


def test_inert_for_non_write_tool(tmp_path: Path) -> None:
    repo, state = _repo(tmp_path)
    code, _ = _run(f"{repo}/src/app.py", workflow="pr", state_dir=state, tool="Bash")
    assert code == 0


def test_blocks_traversal_spoof_escaping_worktree_in_pr_mode(tmp_path: Path) -> None:
    # TASK-543: a path with `/.coding-os/worktrees/` followed by `..` segments that
    # escape back into the shared checkout must classify on the RESOLVED path, not
    # the raw string — the spoof that the worktree allow-case used to wave through.
    repo, state = _repo(tmp_path)
    (Path(repo) / "src").mkdir(parents=True)
    # The worktree dirs must exist for the `..` segments to resolve (cd -P walks them).
    (Path(repo) / ".coding-os" / "worktrees" / "slug" / "wt").mkdir(parents=True)
    spoof = f"{repo}/.coding-os/worktrees/slug/wt/../../../../src/app.py"
    code, err = _run(spoof, workflow="pr", state_dir=state)
    assert code == 2
    assert "worktree" in err.lower()


def test_allows_real_worktree_path_in_pr_mode(tmp_path: Path) -> None:
    # The genuine worktree path (no escape) still passes after the reorder.
    repo, state = _repo(tmp_path)
    wt = Path(repo) / ".coding-os" / "worktrees" / "slug" / "wt" / "src"
    wt.mkdir(parents=True)
    code, _ = _run(f"{wt}/app.py", workflow="pr", state_dir=state)
    assert code == 0
