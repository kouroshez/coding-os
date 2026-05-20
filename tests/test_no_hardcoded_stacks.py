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

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_DIR = REPO_ROOT / "src" / "cli"

# Stack/adapter names discovered from the registries — this is the set
# that must NOT appear as bare literals in cli/*.py.
FORBIDDEN_LITERALS = {"django", "nextjs", "claude", "codex", "python-django", "nextjs-react"}

# Substrings that indicate a legitimate non-hardcoded use (imports,
# comments referencing directory names, docstrings, URL paths).
# We allow a literal if the line matches any of these patterns.
CONTEXTUAL_ALLOW_RE = [
    re.compile(r"^\s*#"),  # whole-line comment
    re.compile(r'^\s*"""'),  # docstring marker line
    re.compile(r"^\s*'"),  # also docstring
    re.compile(r"^\s*\*"),  # markdown-in-docstring bullet
]


def _scan_cli_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (line_no, token, line) for every forbidden literal occurrence."""
    violations: list[tuple[int, str, str]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if any(rx.match(line) for rx in CONTEXTUAL_ALLOW_RE):
            continue
        for token in FORBIDDEN_LITERALS:
            # Match as a quoted string literal only — e.g. `"django"` or `'django'`
            # — not as a substring of some longer identifier.
            patt = re.compile(rf'(?<![A-Za-z0-9_])["\']({re.escape(token)})["\'](?![A-Za-z0-9_])')
            if patt.search(stripped):
                violations.append((i, token, stripped))
    return violations


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
