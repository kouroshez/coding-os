"""The auto-reindex hook's suffix pre-filter admits every suffix the dispatcher routes."""

from __future__ import annotations

import re
from pathlib import Path

from graph_os.tools._reindex_routing import _EXT_MAP

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "auto-reindex-docs.sh"


def test_hook_prefilter_admits_every_routed_suffix():
    # The hook keeps its own case list so it can skip a Python spawn for an
    # unrelated file; it fell behind `_EXT_MAP` and silently dropped edits to
    # every suffix added since.
    match = re.search(r'case "\$FILE_PATH" in\s*\n\s*([^)\n]*)\)', HOOK.read_text(encoding="utf-8"))
    assert match is not None
    admitted = {pattern.strip().lstrip("*") for pattern in match.group(1).split("|")}

    assert set(_EXT_MAP) | {".md", ".mdx"} <= admitted
