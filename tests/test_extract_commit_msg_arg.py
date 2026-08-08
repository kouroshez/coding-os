"""extract_commit_msg_arg.py must defer (not mis-validate) heredoc /
command-substitution `-m` values (TASK-757) while leaving the documented
plain and multi-`-m` forms unaffected — end to end through
enforce-commit-message.sh, since that is what actually gates a commit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "src" / "core" / "hooks" / "_helpers"
HOOK = REPO / "src" / "core" / "hooks" / "enforce-commit-message.sh"

sys.path.insert(0, str(HELPERS))
import extract_commit_msg_arg as extractor


def _extract(command: str) -> str:
    proc = subprocess.run(
        ["python3", str(HELPERS / "extract_commit_msg_arg.py")],
        input=command,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.stdout


def _run_hook(command: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
    )


HEREDOC_COMMIT = (
    "git commit -m \"$(cat <<'EOF'\n"
    "fix(adapters): add Sonnet 5 to Claude model catalogue\n"
    "\n"
    "adapter.yaml drifted from the current lineup.\n"
    "EOF\n"
    ')" -- pyproject.toml'
)


def test_looks_unexpanded_flags_command_substitution_and_heredoc() -> None:
    assert extractor._looks_unexpanded("$(cat <<'EOF'")
    assert extractor._looks_unexpanded("<<EOF")
    assert extractor._looks_unexpanded("`git log -1`")
    assert not extractor._looks_unexpanded("fix(adapters): a normal title")


def test_extractor_defers_heredoc_form() -> None:
    """The exact TASK-757 repro: must return empty, never the garbled blob."""
    out = _extract(HEREDOC_COMMIT)
    assert out == ""


def test_extractor_unaffected_for_plain_multi_m() -> None:
    out = _extract('git commit -m "fix: a title" -m "a body line" -- foo.txt')
    assert out == "fix: a title\n\na body line"


def test_extractor_unaffected_for_single_plain_m() -> None:
    out = _extract('git commit -m "fix(hooks): a compliant title" -- foo.txt')
    assert out == "fix(hooks): a compliant title"


def test_hook_does_not_block_heredoc_form() -> None:
    """Before the fix this BLOCKed on a 400+ char garbled pseudo-title even
    though the real (shell-expanded) message would have been compliant."""
    proc = _run_hook(HEREDOC_COMMIT)
    assert proc.returncode == 0, (
        f"heredoc commit must defer to the git-level hook, not BLOCK; "
        f"got rc={proc.returncode} stderr={proc.stderr!r}"
    )


def test_hook_still_blocks_plain_noncompliant_message() -> None:
    """No regression: the documented, cleanly-parseable form still validates."""
    proc = _run_hook('git commit -m "not a conventional commit message"')
    assert proc.returncode == 2


def test_hook_still_allows_plain_compliant_message() -> None:
    proc = _run_hook('git commit -m "fix(hooks): a compliant title"')
    assert proc.returncode == 0
