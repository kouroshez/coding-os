"""Behavior tests for the warn-diff-size PreToolUse hook.

The hook nudges (never blocks) toward diff-minimal commits: it warns on stderr
when a `git commit` is about to run with a staged diff larger than the
threshold. Fail-open in every uncertain path.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks" / "warn-diff-size.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "base.txt").write_text("x\n")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-qm", "base")


def _run(repo: Path, command: str, env: dict | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, **(env or {})},
    )
    return proc.returncode, proc.stderr


def _stage_big(repo: Path) -> None:
    (repo / "big.txt").write_text("\n".join(str(i) for i in range(500)) + "\n")
    _git(repo, "add", "big.txt")


def test_warns_on_large_staged_commit(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    _init_repo(repo)
    _stage_big(repo)
    code, err = _run(repo, "git commit -m big")
    assert code == 0  # never blocks
    assert "diff-size" in err


def test_silent_on_small_commit(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    _init_repo(repo)
    (repo / "s.txt").write_text("one small line\n")
    _git(repo, "add", "s.txt")
    code, err = _run(repo, "git commit -m small")
    assert code == 0
    assert "diff-size" not in err


def test_silent_on_non_commit_command(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    _init_repo(repo)
    _stage_big(repo)
    code, err = _run(repo, "git status")
    assert code == 0
    assert "diff-size" not in err


def test_off_switch_silences(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    _init_repo(repo)
    _stage_big(repo)
    code, err = _run(repo, "git commit -m big", env={"COS_DIFF_SIZE_WARN": "off"})
    assert code == 0
    assert "diff-size" not in err


def test_warns_on_large_unstaged_path_commit(tmp_path: Path) -> None:
    # The trunk convention is `git commit <path>` on un-staged working-tree
    # changes; the staged diff is empty, so the hook must fall back to HEAD.
    repo = tmp_path / "r"
    _init_repo(repo)
    (repo / "base.txt").write_text("\n".join(str(i) for i in range(500)) + "\n")  # tracked, unstaged
    code, err = _run(repo, "git commit base.txt")
    assert code == 0
    assert "diff-size" in err
