"""cos_graph_doctor — graph health diagnosis and repair.

Its own module because it changes when the *integrity invariants* change
(dangling edges, phantom orphans, stale extraction), while graph.py changes when
the query surface does. They share only the backend accessor and the envelope.
"""

from __future__ import annotations

import logging
from typing import Any

from ._doctor_edges import _check_edges, _check_self_loops
from ._doctor_orphans import (
    _SLOW_EXTRACTION_FLOOR_MS as _SLOW_EXTRACTION_FLOOR_MS,
    _check_orphans,
    _current_extractor_ids as _current_extractor_ids,
    _is_phantom_orphan as _is_phantom_orphan,
)
from ._doctor_paths import _check_extraction_telemetry, _check_paths
from .graph import (
    BackendUnavailable,
    _backend,
    _fail,
    _ok,
    _repo_root_for_paths,
    _server_stale,
)

logger = logging.getLogger("graph_os.tools")

# W7.6 / R4-N9: informational categories (orphaned_external_unresolved)
# do NOT trip healthy=false. Real issues = anything else.
_INFORMATIONAL_CATEGORIES = {
    "orphaned_external_unresolved",
    "files_with_parse_errors",
    "slowest_extractions",
}


def cos_graph_doctor(
    *,
    fix: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Graph health check — orphans, dangling edges, duplicates."""
    try:
        be = _backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    sqlite_conn = getattr(be, "_conn", None)
    issues: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    fixed_count = 0

    if sqlite_conn is not None:
        try:
            stats["node_count"] = sqlite_conn.execute(
                "SELECT COUNT(*) FROM graph_nodes"
            ).fetchone()[0]
            stats["edge_count"] = sqlite_conn.execute(
                "SELECT COUNT(*) FROM graph_edges_v12"
            ).fetchone()[0]

            edge_issues, edge_fixed = _check_edges(sqlite_conn, fix=fix)
            issues.extend(edge_issues)
            fixed_count += edge_fixed

            orphan_issues, orphan_stats, orphan_fixed = _check_orphans(sqlite_conn, fix=fix)
            issues.extend(orphan_issues)
            stats.update(orphan_stats)
            fixed_count += orphan_fixed

            issues.extend(_check_self_loops(sqlite_conn))

            path_issues, path_fixed = _check_paths(sqlite_conn, _repo_root_for_paths(), fix=fix)
            issues.extend(path_issues)
            fixed_count += path_fixed

            telemetry_issues, telemetry_stats = _check_extraction_telemetry(sqlite_conn)
            issues.extend(telemetry_issues)
            stats.update(telemetry_stats)

            if fix:
                stats["fixed_edge_count"] = fixed_count

        except Exception as exc:
            logger.debug("doctor SQL suppressed: %s", exc)
            return _ok(
                {"healthy": None, "issues": [], "stats": {}, "error": str(exc)},
                meta={"backend": be.backend_id},
            )
    else:
        # Non-SQLite backend: basic edge-endpoint check only
        seen_uids: set[str] = set()
        edge_list = be.list_edges(limit=5000)
        for edge in edge_list:
            seen_uids.add(edge.source_uid)
            seen_uids.add(edge.target_uid)
        missing = 0
        for u in list(seen_uids)[:500]:
            if be.get_node(u) is None:
                missing += 1
        if missing:
            issues.append({"category": "dangling_endpoints", "count": missing, "sample": []})
        stats["edge_count"] = len(edge_list)

    real_issues = [i for i in issues if i.get("category") not in _INFORMATIONAL_CATEGORIES]
    healthy = len(real_issues) == 0
    # issue_count drives the Hub ISSUES badge — count what `healthy` counts
    # (real categories), so badge and health never disagree; the
    # all-inclusive number stays available as issue_count_total.
    stats["issue_count"] = len(real_issues)
    stats["issue_count_total"] = len(issues)
    return _ok(
        {"healthy": healthy, "issues": issues, "stats": stats},
        meta={
            "backend": be.backend_id,
            "fix_applied": fix and fixed_count > 0,
            "fixed_count": fixed_count,
            # W7.6 / R4-13: list what fix=true actually deletes today.
            # orphaned_external_unresolved deletes its zero-edge (dead)
            # stubs only — re-extraction re-mints live references.
            "fixable_categories": [
                "stale_paths",
                "malformed_uid_path",
                "dangling_source",
                "dangling_target",
                "duplicate_contains",
                "orphaned_phantom",
                "orphaned_external_unresolved",
            ],
            "informational_categories": list(_INFORMATIONAL_CATEGORIES),
            # F5: warn when the running server is older than graph.py on disk.
            "server_stale": _server_stale(),
        },
    )
