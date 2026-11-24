"""The security auditor runs where it can matter and re-runs only when that changed."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from board_os import review_gate
from board_os.review_security import AUDITOR, audit_digest, security_files


@pytest.mark.parametrize(
    "path",
    [
        "scripts/deploy.sh",
        "src/core/hooks/_helpers/auto_dispatch.py",
        ".github/workflows/ci.yml",
        "docker/Dockerfile.prod",
        "app/auth/views.py",
        "web/src/OAuthProvider.ts",
        "api/token_store.go",
        "pkg/crypto/keys.rs",
        "package.json",
        "services/api/requirements-dev.txt",
        ".env.local",
        ".claude/settings.local.json",
        ".mcp.json",
        "Makefile",
        ".pre-commit-config.yaml",
        ".husky/pre-commit",
        ".circleci/config.yml",
        "setup.py",
        "server/pom.xml",
    ],
)
def test_sensitive_paths_need_the_auditor(path: str) -> None:
    assert security_files([path]) == [path]


@pytest.mark.parametrize(
    "path",
    [
        "src/core/skills/hook-authoring/scripts/new_hook.py",
        "src/components/AuthorCard.tsx",
        "web/src/hooks/useAuthorName.ts",
        "docs/engineering/auth.md",
        "tests/test_auth.py",
        "src/core/board_os/tests/test_review_security.py",
        "README.md",
        "public/login.png",
        "uv.lock",
        "src/core/board_os/workflow.py",
    ],
)
def test_other_paths_do_not(path: str) -> None:
    assert security_files([path]) == []


def _repo(tmp_path: Path) -> tuple[Path, Callable[..., str]]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    return tmp_path, git


def _commit(git: Callable[..., str], root: Path, name: str, body: str) -> str:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    git("add", name)
    git("commit", "-qm", f"edit {name}")
    return git("rev-parse", "--short", "HEAD")


def _scope(root: Path, shas: list[str]) -> dict[str, object]:
    return review_gate._scope_of(root, shas)


def test_a_round_without_sensitive_files_needs_no_audit(tmp_path: Path) -> None:
    root, git = _repo(tmp_path)
    sha = _commit(git, root, "src/board.py", "x = 1\n")
    ledger = tmp_path / "ledger.jsonl"

    assert audit_digest("TASK-1", 1, root, _scope(root, [sha]), path=ledger) == ""
    assert audit_digest("TASK-1", 1, root, {}, path=ledger) == ""


def test_the_auditor_reruns_only_when_its_part_of_the_diff_changed(tmp_path: Path) -> None:
    root, git = _repo(tmp_path)
    shas = [_commit(git, root, "scripts/deploy.sh", "echo one\n")]
    shas.append(_commit(git, root, "src/board.py", "x = 1\n"))
    ledger = tmp_path / "ledger.jsonl"

    first = audit_digest("TASK-1", 1, root, _scope(root, shas), path=ledger)
    assert first
    review_gate.record(
        "TASK-1",
        1,
        AUDITOR,
        "claude",
        state="done",
        passed=True,
        findings=["low: quote the variable"],
        digest=first,
        path=ledger,
    )

    # The rework touched only a non-sensitive file: one review, not two.
    shas.append(_commit(git, root, "src/board.py", "x = 2\n"))
    assert audit_digest("TASK-1", 2, root, _scope(root, shas), path=ledger) == ""

    # The rework touched the script: the audit has to look again.
    shas.append(_commit(git, root, "scripts/deploy.sh", "echo two\n"))
    again = audit_digest("TASK-1", 3, root, _scope(root, shas), path=ledger)
    assert again and again != first


def test_a_blocking_finding_is_rechecked_even_on_an_unchanged_diff(tmp_path: Path) -> None:
    root, git = _repo(tmp_path)
    sha = _commit(git, root, "app/auth/login.py", "check = False\n")
    ledger = tmp_path / "ledger.jsonl"
    scope = _scope(root, [sha])
    digest = audit_digest("TASK-1", 1, root, scope, path=ledger)
    review_gate.record(
        "TASK-1",
        1,
        AUDITOR,
        "codex",
        state="done",
        passed=False,
        findings=["high: login skips the check"],
        digest=digest,
        path=ledger,
    )

    assert audit_digest("TASK-1", 2, root, scope, path=ledger) == digest


def test_an_audit_that_never_finished_runs_again(tmp_path: Path) -> None:
    root, git = _repo(tmp_path)
    sha = _commit(git, root, "scripts/deploy.sh", "echo one\n")
    ledger = tmp_path / "ledger.jsonl"
    scope = _scope(root, [sha])
    digest = audit_digest("TASK-1", 1, root, scope, path=ledger)
    review_gate.record("TASK-1", 1, AUDITOR, "codex", state="error", digest=digest, path=ledger)

    assert audit_digest("TASK-1", 2, root, scope, path=ledger) == digest


def test_a_non_ascii_path_is_still_recognised(tmp_path: Path) -> None:
    # git quotes and octal-escapes such names by default, which no path rule matches.
    root, git = _repo(tmp_path)
    sha = _commit(git, root, "café/auth.py", "check = True\n")

    scope = _scope(root, [sha])

    assert scope["files"] == ["café/auth.py"]
    assert audit_digest("TASK-1", 1, root, scope, path=tmp_path / "ledger.jsonl")


def test_an_unreadable_ledger_means_no_earlier_audit(tmp_path: Path) -> None:
    root, git = _repo(tmp_path)
    sha = _commit(git, root, "scripts/deploy.sh", "echo one\n")
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_bytes(b"\xff\xfe not utf-8\n")

    assert audit_digest("TASK-1", 2, root, _scope(root, [sha]), path=ledger)
    assert review_gate.ledger_rows("TASK-1", ledger) == []
