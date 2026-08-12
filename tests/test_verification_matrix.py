"""Every Verification-Matrix row must name suites that actually exist.

Three rows drifted silently after their suites were split: pytest exits
"no tests ran" on a missing path, which reads exactly like a pass to an agent
skimming output. This parses AGENTS.md and resolves each pytest target, so a
future split fails here instead of hollowing out the matrix.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = REPO_ROOT / "AGENTS.md"

# A matrix row is `| <changed globs> | <command> |` under the "## Verification Matrix"
# heading; the command cell holds one or more backtick-quoted shell commands.
_ROW_RE = re.compile(r"^\|\s*(?P<changed>`[^|]+)\|\s*(?P<command>.+?)\s*\|\s*$")
_BACKTICKED_RE = re.compile(r"`([^`]+)`")
# pytest targets are the bare path-like words: they contain a separator or end
# in .py, which excludes flags, `-m 'not slow'` values, and the tool names.
_TARGET_RE = re.compile(r"(?:^|\s)((?:[\w./*-]+/)[\w./*-]*|[\w.*-]+\.py)(?=\s|$)")


def _matrix_commands() -> list[tuple[str, str]]:
    lines = AGENTS_MD.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Verification Matrix"))
    rows: list[tuple[str, str]] = []
    for line in lines[start:]:
        if line.startswith("## ") and not line.startswith("## Verification Matrix"):
            break
        match = _ROW_RE.match(line)
        if not match or match.group("changed").startswith("`Changed`"):
            continue
        for command in _BACKTICKED_RE.findall(match.group("command")):
            rows.append((match.group("changed").strip(), command.strip()))
    return rows


def test_the_matrix_section_is_parseable() -> None:
    assert len(_matrix_commands()) >= 9


@pytest.mark.parametrize("changed,command", _matrix_commands())
def test_every_pytest_target_in_the_matrix_resolves(changed: str, command: str) -> None:
    if "pytest" not in command:
        return
    targets = [
        target
        for target in _TARGET_RE.findall(command.split("pytest", 1)[1])
        if not target.startswith("-")
    ]
    assert targets, f"row {changed}: no pytest target parsed from {command!r}"
    for target in targets:
        matches = list(REPO_ROOT.glob(target))
        assert matches, (
            f"row {changed}: pytest target {target!r} matches nothing — the row is a no-op"
        )


@pytest.mark.parametrize("changed,command", _matrix_commands())
def test_no_matrix_command_invokes_a_bare_python(changed: str, command: str) -> None:
    # `python` is absent on a stock macOS shell (only `python3`), so a bare
    # `python …` row dies with "command not found" and verifies nothing.
    for match in re.finditer(r"(?<![\w.-])python(?![\w.-])", command):
        preceding = command[: match.start()].rstrip()
        assert preceding.endswith("uv run"), (
            f"row {changed}: {command!r} calls bare `python` — use `uv run python`"
        )
