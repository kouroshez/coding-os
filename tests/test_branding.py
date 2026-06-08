"""Branding compliance gate (T16.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that MUST NOT contain "Claude Code" in user-visible strings.
GUARDED_GLOBS: list[str] = [
    "src/core/web/ui/src/**/*.ts",
    "src/core/web/ui/src/**/*.tsx",
    "src/cli/**/*.py",
]

# Files where "Claude Code" is intentional and descriptive (Anthropic's
# product reference, NOT coding-os branding). Skip these from the scan.
ALLOWED_PATHS: set[str] = {
    "src/cli/doctor.py",  # describes Claude Code CLI version checks
    # Descriptive references to Anthropic's product in code comments —
    # not self-branding. ChatView explains where the Claude Code IDE
    # writes session JSONL; DashboardPage explains a recycled-PID edge
    # case ("long-dead Claude Code process").
    "src/core/web/ui/src/features/cognition/ChatView.tsx",
    "src/core/web/ui/src/pages/DashboardPage.tsx",
    # ChatLanding's empty-state tells the user the chat feature needs Anthropic's
    # Claude Code / Claude Agent SDK installed — descriptive install guidance for
    # a genuinely Claude-SDK-gated feature, not coding-os self-branding.
    "src/core/web/ui/src/pages/ChatLanding.tsx",
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
        f
        for f in files
        if f.relative_to(REPO_ROOT).as_posix() not in ALLOWED_PATHS
        # Test/spec files assert against real product labels (e.g. a model-picker
        # option "Anthropic Claude Code") — they are test code, not user-visible
        # UI, which is what this branding gate guards.
        and not f.name.endswith((".test.tsx", ".test.ts", ".spec.tsx", ".spec.ts"))
    ]


def test_branding_globs_match_files() -> None:
    """Guard the guard: if GUARDED_GLOBS match zero files (repo restructure),
    the parametrized branding test silently collects nothing and the gate
    evaporates. Fail loud instead."""
    assert _iter_guarded_files(), "GUARDED_GLOBS matched no files — branding gate is dead"


@pytest.mark.parametrize(
    "source_file", _iter_guarded_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
def test_no_claude_code_branding(source_file: Path) -> None:
    text = source_file.read_text(encoding="utf-8")
    for token in FORBIDDEN_TOKENS:
        assert token not in text, (
            f"{source_file.relative_to(REPO_ROOT)}: forbidden branding token "
            f"{token!r} appears. coding-os MUST NOT present itself as Claude Code. "
            f"If the reference is descriptive (referring to Anthropic's product), "
            f"add the file path to ALLOWED_PATHS in tests/test_branding.py."
        )
