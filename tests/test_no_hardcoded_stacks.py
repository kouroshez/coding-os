"""Guard: no stack/adapter name is hardcoded in cli/*.py.

If this test fails, it means someone added a reference like `"django"` or
`"nextjs"` directly in Python code — which defeats the data-driven design.
The correct fix is to add a field to stack.yaml / adapter.yaml and read it
via the registry.

Allowed locations for literals:
  - tests/ (anywhere)
  - scripts/ (capture_golden, generate_manifest — they need fixture names)
  - templates/ and adapters/ (data files, obviously)

Not allowed:
  - cli/*.py (the data-driven layer)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DIR = REPO_ROOT / "src" / "cli"

# Single source for Rule-11 enforcement (R11/F12, TASK-441): this rear-guard
# test and the PreToolUse front-guard (block-hardcoded-literals.sh) share the
# SAME narrowed forbidden set + scan logic, so they can never diverge.
sys.path.insert(0, str(REPO_ROOT / "src" / "core" / "scripts"))
from check_hardcoded_literals import discover_literals, scan  # noqa: E402

FORBIDDEN_LITERALS = discover_literals()


def _scan_cli_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_no, token, line) for every forbidden literal occurrence."""
    return scan(path.read_text(encoding="utf-8"), FORBIDDEN_LITERALS)


@pytest.mark.parametrize(
    "cli_file",
    sorted(p for p in CLI_DIR.glob("*.py") if not p.name.startswith("_test_")),
    ids=lambda p: p.name,
)
def test_no_hardcoded_stack_names(cli_file: Path) -> None:
    """No cli/*.py file should contain literal stack/adapter names."""
    violations = _scan_cli_file(cli_file)
    assert not violations, (
        f"{cli_file.name} contains hardcoded stack/adapter literals:\n"
        + "\n".join(f"  line {i}: {token!r} → {line}" for i, token, line in violations)
        + "\n\nMove the metadata to templates/<stack>/stack.yaml or "
        "src/adapters/<agent>/adapter.yaml and read it via the registry."
    )


def test_forbidden_set_stays_narrowed() -> None:
    """R11/F12: the shared set must stay false-positive-free. Re-adding the skills
    loop or dropping the AMBIGUOUS_IDS filter in discover_literals would silently
    re-break every cli/*.py edit through the live front-guard hook."""
    forbidden = discover_literals()
    for skill in ("thinking_os", "observability", "clean-code", "graph-explorer"):
        assert skill not in forbidden, f"{skill!r} is a skill — collides with code"
    for ambiguous in ("go", "python", "meta", "fastapi"):
        assert ambiguous not in forbidden, f"{ambiguous!r} doubles as an ordinary code token"
    for real in ("django", "nextjs", "claude", "codex"):
        assert real in forbidden, f"{real!r} must stay enforced (over-narrowed otherwise)"
