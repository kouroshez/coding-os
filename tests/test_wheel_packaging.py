"""Regression guard for the H1 wheel-data class: the installed `cos` reads
non-Python data trees at runtime (role/preset/situation chains, hook registry,
…). If a tree is not declared in [tool.setuptools.package-data], a pip/uvx wheel
omits it and the feature degrades SILENTLY (empty compose-chain, no situations).
CI only runs an editable `uv sync`, so it never catches this — this test does.

Text-based assertions (no tomllib — the project targets py3.10 where it is absent).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _ROOT / "pyproject.toml"

# Globs the installed runtime resolves relative to the `core` package. Each MUST
# appear in [tool.setuptools.package-data].core or a wheel drops it.
_REQUIRED_CORE_GLOBS = [
    "hooks/*.sh",
    "hooks/_helpers/*.py",
    "hooks/registry.yaml",
    "rules/*.md",
    "schemas/*.json",
    "thinking_os/agents/**/*",
    "thinking_os/presets/*.yaml",
    "thinking_os/situations/*.yaml",
    "thinking_os/roles/*.yaml",
    "board_os/*.yaml",
]

# (glob → a representative source file that proves the tree is non-empty, so the
#  glob is not silently matching nothing.)
_RUNTIME_DATA_SENTINELS = {
    "thinking_os/presets/*.yaml": "src/core/thinking_os/presets/registry.yaml",
    "thinking_os/situations/*.yaml": "src/core/thinking_os/situations/registry.yaml",
    "thinking_os/roles/*.yaml": "src/core/thinking_os/roles/reviewer.yaml",
    "hooks/registry.yaml": "src/core/hooks/registry.yaml",
}


def _core_package_data() -> str:
    """Return the raw text of the `core = [ ... ]` block in package-data."""
    text = _PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"\[tool\.setuptools\.package-data\](.*?)(\n\[|\Z)", text, re.S)
    assert block, "pyproject.toml has no [tool.setuptools.package-data] section"
    core = re.search(r"\bcore\s*=\s*\[(.*?)\]", block.group(1), re.S)
    assert core, "package-data has no `core = [...]` list"
    return core.group(1)


@pytest.mark.parametrize("glob", _REQUIRED_CORE_GLOBS)
def test_runtime_data_tree_is_declared_in_package_data(glob: str) -> None:
    assert glob in _core_package_data(), (
        f"package-data.core is missing {glob!r} — a wheel install will omit this "
        f"runtime data tree and the feature will degrade silently (H1 class)."
    )


@pytest.mark.parametrize("glob,sentinel", sorted(_RUNTIME_DATA_SENTINELS.items()))
def test_runtime_data_source_exists(glob: str, sentinel: str) -> None:
    assert (_ROOT / sentinel).is_file(), (
        f"{sentinel} is gone — the {glob!r} package-data glob now matches nothing; "
        f"update the sentinel or restore the data."
    )
