"""cos_graph_rename_plan and the source-literal grep that backs its warnings."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from .graph import (
    _BEHAVIOURAL_EDGE_TYPES,
    _count_edges_for,
    _edge_to_dict,
    _fail,
    _fail_uid_not_found,
    _ok,
    _resolve_uid,
    _write_consult_marker,
    logger,
)


def cos_graph_rename_plan(
    uid: str,
    new_name: str,
    *,
    check_strings: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Produce a rename plan — call-sites, docs, tests, strings."""
    if not new_name or not new_name.strip():
        return _fail("validation", "new_name must be non-empty")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)
    # R4-18: reject no-op rename (new_name equals current label)
    if new_name.strip() == (root.label or ""):
        return _fail(
            "validation",
            f"new_name {new_name!r} equals current label — no-op rename",
        )
    uid = root.uid

    # Rename plans MUST be exhaustive — a missed call-site leaves
    # broken code after rename. Counter each bucket separately so the
    # caller can see if the in-line slice was incomplete. Bucket pulls
    # from the same SSOT (`_BEHAVIOURAL_EDGE_TYPES`) impact uses,
    # minus `references_doc` which is counted under doc_edge_types
    # below to avoid double-counting.
    _RENAME_BUCKET_LIMIT = 500
    call_edge_types = tuple(sorted(_BEHAVIOURAL_EDGE_TYPES - {"references_doc"}))
    doc_edge_types = ("links_to", "cites_heading", "references_doc")
    test_edge_types = ("tested_by",)
    call_sites = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=call_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    doc_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=doc_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    test_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=test_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    call_total = _count_edges_for(be, target_uid=uid, edge_types=call_edge_types)
    doc_total = _count_edges_for(be, target_uid=uid, edge_types=doc_edge_types)
    test_total = _count_edges_for(be, target_uid=uid, edge_types=test_edge_types)
    result_truncated = (
        call_total > len(call_sites) or doc_total > len(doc_refs) or test_total > len(test_refs)
    )
    risk = "high" if len(call_sites) > 20 else "medium" if call_sites else "low"

    if root.label:
        _write_consult_marker(
            f"plan-{root.label}",
            {
                "identifier": root.label,
                "uid": root.uid,
                "new_name": new_name,
                "tool": "cos_graph_rename_plan",
            },
        )
    return _ok(
        {
            "old_name": root.label,
            "new_name": new_name,
            "uid": root.uid,
            "call_sites": call_sites,
            "call_sites_total_count": call_total,
            "doc_references": doc_refs,
            "doc_references_total_count": doc_total,
            "test_references": test_refs,
            "test_references_total_count": test_total,
            "string_literals": [] if not check_strings else _grep_string_literals(root.label or ""),
            "risk": risk,
            "suggested_order": [
                "tests first",
                "implementation",
                "docs",
                "string literals last",
            ],
            "confidence": 0.9 if call_sites else 0.6,
        },
        meta={
            "backend": be.backend_id,
            "bucket_limit": _RENAME_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "resolved_from": resolved_from,
        },
    )


def _grep_string_literals(name: str, *, limit: int = 100) -> list[dict[str, Any]]:
    # check_strings path: find the symbol name INSIDE a string literal — the
    # rename targets an AST pass misses (getattr(o, "name"), config keys,
    # dynamic dispatch). ripgrep when present (respects .gitignore), bounded
    # Python walk otherwise. Quote-scoped regex keeps precision; capped at
    # `limit`. Was a permanent [] stub → check_strings was a no-op.
    if not name or len(name) < 3:
        return []  # too short → only noise
    root = _kernel._repo_root_for_paths()
    pattern = rf"""("[^"]*\b{re.escape(name)}\b[^"]*"|'[^']*\b{re.escape(name)}\b[^']*')"""
    hits: list[dict[str, Any]] = []

    import subprocess

    try:
        proc = subprocess.run(
            ["rg", "--line-number", "--no-heading", "--color", "never", "-e", pattern, str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        for raw in proc.stdout.splitlines():
            parts = raw.split(":", 2)  # <path>:<line>:<text>
            if len(parts) < 3:
                continue
            fp, ln, text = parts
            try:
                rel = Path(fp).resolve().relative_to(root).as_posix()
            except ValueError:
                rel = fp
            hits.append(
                {"file": rel, "line": int(ln) if ln.isdigit() else None, "text": text.strip()[:200]}
            )
            if len(hits) >= limit:
                break
        return hits
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        logger.debug("rg string-scan unavailable, walking instead: %s", exc)

    # Fallback — bounded Python walk with the same filters as the indexer.
    try:
        import fnmatch

        from ..ingest.base import (
            DEFAULT_EXCLUDE,
            DEFAULT_EXCLUDE_PATHS,
            DEFAULT_INCLUDE,
        )

        rx = re.compile(pattern)
        scanned = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE]
            # Prune path-segment excludes (tests/golden scaffold mirrors) the
            # same way walk_local does, so the fallback doesn't surface string
            # hits from duplicate-spine fixtures.
            rel_dir = Path(dirpath).resolve().relative_to(root).as_posix()
            if any(rel_dir == p or rel_dir.startswith(p + "/") for p in DEFAULT_EXCLUDE_PATHS):
                dirnames[:] = []
                continue
            for fn in filenames:
                if not any(fnmatch.fnmatchcase(fn, p) for p in DEFAULT_INCLUDE):
                    continue
                full = Path(dirpath) / fn
                if full.is_symlink():
                    continue
                scanned += 1
                if scanned > 5000:
                    return hits
                try:
                    if full.stat().st_size > 1_000_000:
                        continue
                    with full.open(encoding="utf-8", errors="ignore") as fh:
                        for i, line in enumerate(fh, 1):
                            if name in line and rx.search(line):
                                hits.append(
                                    {
                                        "file": full.resolve().relative_to(root).as_posix(),
                                        "line": i,
                                        "text": line.strip()[:200],
                                    }
                                )
                                if len(hits) >= limit:
                                    return hits
                except OSError:
                    continue
    except Exception as exc:  # fail-open — string scan is best-effort
        logger.debug("string-literal walk failed: %s", exc)
    return hits
