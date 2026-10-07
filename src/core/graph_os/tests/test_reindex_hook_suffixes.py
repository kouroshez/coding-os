"""The graph reindex hook's suffix pre-filter admits every suffix the dispatcher routes."""

from __future__ import annotations

import re
from pathlib import Path

from graph_os.tools._reindex_routing import _EXT_MAP

HOOK = Path(__file__).resolve().parents[2] / "hooks" / "auto-reindex-graph.sh"


def test_hook_prefilter_admits_every_routed_suffix():
    # The hook keeps its own case list so it can skip a Python spawn for an
    # unrelated file; it fell behind `_EXT_MAP` and silently dropped edits to
    # every suffix added since.
    match = re.search(r'case "\$FILE_PATH" in\s*\n\s*([^)\n]*)\)', HOOK.read_text(encoding="utf-8"))
    assert match is not None
    admitted = {pattern.strip().lstrip("*") for pattern in match.group(1).split("|")}

    assert set(_EXT_MAP) | {".md", ".mdx"} <= admitted


def test_the_shell_reconcile_hook_watches_every_routed_suffix():
    # Its own list read `py|ts|tsx|md|sh|…`, so an `rm` of a `.js`, `.astro`
    # or `.php` file never reached the graph.
    reconcile = HOOK.with_name("auto-graph-reconcile-shell.sh").read_text(encoding="utf-8")
    match = re.search(r"^ROUTED_SUFFIXES='([^']*)'", reconcile, re.MULTILINE)
    assert match is not None
    watched = {f".{suffix}" for suffix in match.group(1).split("|")}

    assert set(_EXT_MAP) | {".md", ".mdx"} <= watched
