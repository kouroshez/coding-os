"""Change-analysis tools: impact, detect_changes, rename_plan, diff, contracts.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import re
from typing import Any

from . import graph as _kernel
from ._analysis_contracts import (
    _is_test_source as _is_test_source,
    cos_graph_contracts as cos_graph_contracts,
)
from ._analysis_impact import (
    _file_contained_symbols as _file_contained_symbols,
    cos_graph_detect_changes as cos_graph_detect_changes,
    cos_graph_impact as cos_graph_impact,
)
from ._analysis_rename import (
    _grep_string_literals as _grep_string_literals,
    cos_graph_rename_plan as cos_graph_rename_plan,
)
from .graph import (
    _fail,
    _ok,
)


def cos_graph_diff(
    *,
    base: str = "HEAD~1",
    head: str = "HEAD",
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Graph blast-radius of a git range — base..head changed files → affected symbols + downstream."""
    import subprocess

    base = str(base).strip()
    head = str(head).strip() or "HEAD"
    if not base:
        return _fail("validation", "base ref required")
    # Validate refs are plain git revisions (no shell-injection metachars).
    if not all(re.match(r"^[\w./~^@{}-]+$", r) for r in (base, head)):
        return _fail("validation", "base/head must be plain git revisions")
    root = _kernel._repo_root_for_paths()
    rng = f"{base}..{head}"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", rng],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return _fail("internal", f"git diff failed: {exc}")
    if out.returncode != 0:
        return _fail("not_found", f"git diff {rng}: {out.stderr.strip()[:200]}", retryable=False)
    files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    if not files:
        return _ok(
            {
                "range": rng,
                "file_count": 0,
                "files": [],
                "symbols": [],
                "downstream_consumers": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"layer": "graph", "range": rng, "file_count": 0},
        )
    # DRY: delegate to detect_changes for the blast-radius. Its data already
    # carries scope=range + files; downstream_consumers/risk come for free.
    return cos_graph_detect_changes(
        files=files,
        scope=rng,
        analyze_downstream=analyze_downstream,
        backend=backend,
    )
