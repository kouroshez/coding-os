"""Regression: enforce-commit-message.sh must resolve _helpers/ through the
hook's physical location so it works when invoked via the .claude/hooks/
symlink a consumer project installs — where .claude/hooks/_helpers does NOT
exist and there is no src/core/ tree to fall back to (TASK-211).

Before the fix, both the index.lock wait and the commit-message contract
silently no-op'd in every consumer; only the meta-repo (which has src/core/)
masked the bug via its fallback path.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "src" / "core" / "hooks" / "enforce-commit-message.sh"
COS_ENV = REPO / "src" / "core" / "hooks" / "cos-env.sh"


def _run(hook_path: Path, command: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        ["bash", str(hook_path)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
    )


def _consumer_hooks_dir(tmp_path: Path) -> Path:
    # Mimic a `cos init` consumer: each hook is an individual symlink into the
    # meta-repo; the _helpers/ subdir is never symlinked alongside it.
    hooks_dir = tmp_path / "consumer" / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "enforce-commit-message.sh").symlink_to(HOOK)
    (hooks_dir / "cos-env.sh").symlink_to(COS_ENV)
    assert not (hooks_dir / "_helpers").exists()
    return hooks_dir


def test_blocks_noncompliant_message_through_symlink(tmp_path: Path) -> None:
    hooks_dir = _consumer_hooks_dir(tmp_path)
    proc = _run(hooks_dir / "enforce-commit-message.sh", 'git commit -m "not a conventional commit message"')
    assert proc.returncode == 2, (
        "expected the commit-message contract to BLOCK via symlink-resolved helper; "
        f"got rc={proc.returncode} stderr={proc.stderr!r}"
    )


def test_allows_compliant_message_through_symlink(tmp_path: Path) -> None:
    hooks_dir = _consumer_hooks_dir(tmp_path)
    proc = _run(hooks_dir / "enforce-commit-message.sh", 'git commit -m "fix(hooks): resolve helpers through symlink"')
    assert proc.returncode == 0, (
        f"a compliant conventional-commit title should pass; got rc={proc.returncode} stderr={proc.stderr!r}"
    )


def test_meta_repo_direct_invocation_still_blocks(tmp_path: Path) -> None:
    # Direct (non-symlink) invocation in the meta-repo must remain unchanged.
    proc = _run(HOOK, 'git commit -m "garbage message with no type"')
    assert proc.returncode == 2, f"meta-repo behavior must be unchanged; got rc={proc.returncode} stderr={proc.stderr!r}"
