"""Branding compliance gate (T16.2).

PURPOSE:      Fail CI if "Claude Code" appears in user-visible coding-os
              copy (UI, banners, error messages, README banners). Anthropic's
              terms allow descriptive references but coding-os MUST NOT
              present itself as "Claude Code". The Q.deep audit (2026-05-05)
              confirmed only descriptive references remain — this test
              guards that state.
INPUT:        Source files under core/web/ui/src/, adapters/claude/install.sh,
              user-facing CLI banners.
OUTPUT:       pytest fail when forbidden strings appear in scanned files.
NOTES:        Allow-listed paths carry intentional descriptive references
              (adapter.yaml::label, install.sh comments, doc files). Add
              new paths only when the reference is genuinely descriptive.
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that MUST NOT contain "Claude Code" in user-visible strings.
GUARDED_GLOBS: list[str] = [
    "core/web/ui/src/**/*.ts",
    "core/web/ui/src/**/*.tsx",
    "cli/**/*.py",
]

# Files where "Claude Code" is intentional and descriptive (Anthropic's
# product reference, NOT coding-os branding). Skip these from the scan.
ALLOWED_PATHS: set[str] = {
    "cli/doctor.py",  # describes Claude Code CLI version checks
}

FORBIDDEN_TOKENS: tuple[str, ...] = (
    "Claude Code",
    "claude-code",
)


def _iter_guarded_files() -> list[Path]:
    files: list[Path] = []
    for pattern in GUARDED_GLOBS:
        files.extend(REPO_ROOT.glob(pattern))
    return [
        f for f in files
        if f.relative_to(REPO_ROOT).as_posix() not in ALLOWED_PATHS
    ]


@pytest.mark.parametrize("source_file", _iter_guarded_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_no_claude_code_branding(source_file: Path) -> None:
    text = source_file.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in text, (
            f"{source_file.relative_to(REPO_ROOT)}: forbidden branding token "
            f"{token!r} appears. coding-os MUST NOT present itself as Claude Code. "
            f"If the reference is descriptive (referring to Anthropic's product), "
            f"add the file path to ALLOWED_PATHS in tests/test_branding.py."
        )
