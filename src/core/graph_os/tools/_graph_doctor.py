"""cos_graph_doctor — graph health diagnosis and repair.

Its own module because it changes when the *integrity invariants* change
(dangling edges, phantom orphans, stale extraction), while graph.py changes when
the query surface does. They share only the backend accessor and the envelope.
"""

from __future__ import annotations

import logging
from typing import Any

from ._doctor_orphans import (
    _SLOW_EXTRACTION_FLOOR_MS,
    _current_extractor_ids as _current_extractor_ids,
    _is_phantom_orphan,
)
from .graph import (
    BackendUnavailable,
    _backend,
    _fail,
    _ok,
    _repo_root_for_paths,
    _server_stale,
)

logger = logging.getLogger("graph_os.tools")


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
            node_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            edge_count = sqlite_conn.execute("SELECT COUNT(*) FROM graph_edges_v12").fetchone()[0]
            stats["node_count"] = node_count
            stats["edge_count"] = edge_count

            # 1. Dangling source edges (source_id FK points to deleted node)
            dangling_src_rows = sqlite_conn.execute(
                """
                SELECT e.id, ns.uid, nt.uid
                FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE ns.id IS NULL
                LIMIT 100
                """
            ).fetchall()
            dangling_src_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                WHERE ns.id IS NULL
                """
            ).fetchone()[0]
            if dangling_src_count:
                issues.append(
                    {
                        "category": "dangling_source",
                        "count": dangling_src_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_src_rows[:5]
                        ],
                    }
                )
                if fix:
                    ids_to_del = [r[0] for r in dangling_src_rows]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 2. Dangling target edges (target_id FK points to deleted node)
            dangling_tgt_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM graph_edges_v12 e
                LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                WHERE nt.id IS NULL
                """
            ).fetchone()[0]
            if dangling_tgt_count:
                dangling_tgt_rows = sqlite_conn.execute(
                    """
                    SELECT e.id, ns.uid, nt.uid
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    WHERE nt.id IS NULL
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "dangling_target",
                        "count": dangling_tgt_count,
                        "sample": [
                            {"edge_id": r[0], "source_uid": r[1], "target_uid": r[2]}
                            for r in dangling_tgt_rows
                        ],
                    }
                )
                if fix:
                    all_dangling_tgt = sqlite_conn.execute(
                        """
                        SELECT e.id FROM graph_edges_v12 e
                        LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                        WHERE nt.id IS NULL
                        """
                    ).fetchall()
                    ids_to_del = [r[0] for r in all_dangling_tgt]
                    if ids_to_del:
                        placeholders = ",".join("?" * len(ids_to_del))
                        sqlite_conn.execute(
                            f"DELETE FROM graph_edges_v12 WHERE id IN ({placeholders})",
                            ids_to_del,
                        )
                        sqlite_conn.commit()
                        fixed_count += len(ids_to_del)

            # 3. Duplicate edges (same source_id/target_id/edge_type/extractor)
            dup_count = sqlite_conn.execute(
                """
                SELECT COUNT(*) FROM (
                  SELECT source_id, target_id, edge_type, extractor,
                         COUNT(*) AS cnt
                  FROM graph_edges_v12
                  GROUP BY source_id, target_id, edge_type, extractor
                  HAVING cnt > 1
                )
                """
            ).fetchone()[0]
            if dup_count:
                dup_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, nt.uid, e.edge_type, e.extractor,
                           COUNT(*) AS cnt
                    FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    LEFT JOIN graph_nodes nt ON nt.id = e.target_id
                    GROUP BY e.source_id, e.target_id, e.edge_type, e.extractor
                    HAVING cnt > 1
                    ORDER BY cnt DESC
                    LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "duplicate_edges",
                        "count": dup_count,
                        "sample": [
                            {
                                "source_uid": r[0],
                                "target_uid": r[1],
                                "edge_type": r[2],
                                "extractor": r[3],
                                "count": r[4],
                            }
                            for r in dup_sample
                        ],
                    }
                )

            # 3b. W6.10: cross-extractor `contains` duplication. The folder
            # spine is re-emitted by every extractor that touches a file, so
            # the rows differ only by `extractor` and slip past the
            # (…, extractor) check above — yet they inflate degree centrality
            # (which counts COUNT(e.id), not DISTINCT). Collapse to one row
            # per (folder, file) pair.
            contains_dup_rows = sqlite_conn.execute(
                """
                SELECT source_id, target_id, COUNT(*) AS cnt
                FROM graph_edges_v12
                WHERE edge_type='contains'
                GROUP BY source_id, target_id
                HAVING cnt > 1
                """
            ).fetchall()
            contains_extra = sum(int(r[2]) - 1 for r in contains_dup_rows)
            if contains_extra:
                issues.append(
                    {
                        "category": "duplicate_contains",
                        "count": contains_extra,
                        "pair_count": len(contains_dup_rows),
                    }
                )
                if fix:
                    cur = sqlite_conn.execute(
                        """
                        DELETE FROM graph_edges_v12
                        WHERE edge_type='contains' AND id NOT IN (
                          SELECT MIN(id) FROM graph_edges_v12
                          WHERE edge_type='contains'
                          GROUP BY source_id, target_id
                        )
                        """
                    )
                    fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()

            # 4. Orphans — split into expected-noise vs real-bug categories.
            # W7.6 / R4-N9: `code:external:unresolved:*` and `cos:identifier:*`
            # are stub-surface, not bugs. Count separately so `healthy=true`
            # is achievable when only stubs are unconnected.
            orphan_rows = sqlite_conn.execute(
                """
                SELECT n.uid, n.kind, n.label, n.file_path, n.metadata_json
                FROM graph_nodes n
                LEFT JOIN graph_edges_v12 src ON src.source_id = n.id
                LEFT JOIN graph_edges_v12 tgt ON tgt.target_id = n.id
                WHERE src.id IS NULL AND tgt.id IS NULL
                """
            ).fetchall()
            real_orphans: list[tuple[str, str, str]] = []
            stub_orphans: list[tuple[str, str, str]] = []
            phantom_orphans: list[tuple[str, str, str]] = []
            for uid_, kind_, label_, fp_, meta_ in orphan_rows:
                # W7.6: `code:external:*` (all sub-patterns) are stubs by
                # definition — they reference symbols outside the indexed
                # graph, so being unconnected is expected, not a bug.
                # Same for `cos:identifier:*` (skill/adapter reference
                # singletons that the extractor emits for completeness).
                uid_str = uid_ or ""
                if uid_str.startswith("code:external:") or uid_str.startswith("cos:identifier:"):
                    stub_orphans.append((uid_, kind_, label_))
                elif _is_phantom_orphan(kind_, fp_, uid_, meta_):
                    # Fixable junk: zero-edge stub / legacy-extractor row /
                    # dir-phantom.
                    phantom_orphans.append((uid_, kind_, label_))
                else:
                    real_orphans.append((uid_, kind_, label_))
            stats["orphaned_nodes"] = len(orphan_rows)
            stats["orphaned_inrepo"] = len(real_orphans)
            stats["orphaned_external_unresolved"] = len(stub_orphans)
            stats["orphaned_phantom"] = len(phantom_orphans)
            if real_orphans:
                issues.append(
                    {
                        "category": "orphaned_inrepo",
                        "count": len(real_orphans),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]} for r in real_orphans[:5]
                        ],
                    }
                )
            if phantom_orphans:
                issues.append(
                    {
                        "category": "orphaned_phantom",
                        "count": len(phantom_orphans),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]} for r in phantom_orphans[:5]
                        ],
                    }
                )
                if fix:
                    p_uids = [r[0] for r in phantom_orphans]
                    chunk = 500
                    for i in range(0, len(p_uids), chunk):
                        batch = p_uids[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()
            if stub_orphans:
                # Informational only — never trips healthy=false. The
                # aggregate `count` lumps three distinct stub kinds; the
                # `breakdown` reports the accurate per-prefix split so the
                # label isn't misread as "all external:unresolved".
                breakdown = {"external_unresolved": 0, "external_other": 0, "identifier_stub": 0}
                for uid_, _kind, _label in stub_orphans:
                    u = uid_ or ""
                    if u.startswith("code:external:unresolved:"):
                        breakdown["external_unresolved"] += 1
                    elif u.startswith("code:external:"):
                        breakdown["external_other"] += 1
                    else:  # cos:identifier:*
                        breakdown["identifier_stub"] += 1
                issues.append(
                    {
                        "category": "orphaned_external_unresolved",
                        "count": len(stub_orphans),
                        "severity": "info",
                        "breakdown": breakdown,
                        "sample": [
                            {"uid": r[0], "kind": r[1], "label": r[2]} for r in stub_orphans[:5]
                        ],
                    }
                )
                if fix:
                    # A stub exists only to anchor edges; zero edges = dead
                    # (its source file was deleted — stubs carry
                    # file_path=NULL, so no path-keyed prune ever reaches
                    # them). Re-extraction re-mints any still referenced.
                    s_uids = [r[0] for r in stub_orphans]
                    chunk = 500
                    for i in range(0, len(s_uids), chunk):
                        batch = s_uids[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()

            # 5. Self-loop edges (source_id == target_id — extractor bugs)
            self_loop_count = sqlite_conn.execute(
                "SELECT COUNT(*) FROM graph_edges_v12 WHERE source_id = target_id"
            ).fetchone()[0]
            if self_loop_count:
                sl_sample = sqlite_conn.execute(
                    """
                    SELECT ns.uid, e.edge_type FROM graph_edges_v12 e
                    LEFT JOIN graph_nodes ns ON ns.id = e.source_id
                    WHERE e.source_id = e.target_id LIMIT 5
                    """
                ).fetchall()
                issues.append(
                    {
                        "category": "self_loops",
                        "count": self_loop_count,
                        "sample": [{"uid": r[0], "edge_type": r[1]} for r in sl_sample],
                    }
                )

            # 6. Stale-path nodes — file_path points to a file that no
            # longer exists on disk. Accumulates when files move (e.g.
            # the `core/` → `src/core/` reorg left 3.7K ghost nodes
            # invisible to the dangling/orphan/self_loop checks because
            # ghosts had their own internal contains-children tree).
            distinct_paths = [
                r[0]
                for r in sqlite_conn.execute(
                    "SELECT DISTINCT file_path FROM graph_nodes "
                    "WHERE file_path IS NOT NULL AND file_path != ''"
                ).fetchall()
            ]
            repo_root = _repo_root_for_paths()

            # W7.6 / R4-25 + R4-X7-residual: split malformed paths from
            # genuine stale paths. Malformed paths are extractor bugs —
            # they can never resolve from repo root regardless of fs state.
            # Patterns:
            #   - contains `../` (relative-from-wrong-cwd)
            #   - contains backtick (markdown link regex over-captured
            #     `[text](path)` syntax including trailing backtick)
            #   - contains newline / control char (raw prose fragment)
            # NOTE: a plain space is NOT malformed — legitimate doc files
            # have spaces in their names. Flagging space caused a
            # delete↔reindex churn of 475 real nodes.
            def _is_malformed(p: str) -> bool:
                return (
                    ("../" in p)
                    or ("`" in p)
                    or any(c == "\n" or c == "\r" or c == "\t" or ord(c) < 32 for c in p)
                )

            malformed_paths = [p for p in distinct_paths if _is_malformed(p)]
            # Also catch nodes with malformed UIDs but NULL file_path —
            # the markdown link extractor sometimes emits a code:file:* uid
            # whose path is captured in the uid suffix only.
            malformed_uid_rows = sqlite_conn.execute(
                "SELECT uid FROM graph_nodes WHERE "
                "(uid LIKE '%`%' OR uid LIKE 'doc:file:../%' OR uid LIKE 'code:file:../%')"
            ).fetchall()
            malformed_uids = [r[0] for r in malformed_uid_rows]
            # Symlink-backed file nodes — the target is indexed on its own
            # pass, so the symlink node (e.g. CLAUDE.md -> AGENTS.md) is an
            # orphan duplicate. walk_local now skips symlinks; this catches
            # rows from before that fix landed.
            symlink_paths = [
                p
                for p in distinct_paths
                if not _is_malformed(p)
                and (repo_root / p).exists()
                and (repo_root / p).is_symlink()
            ]
            real_stale_paths = [
                p
                for p in distinct_paths
                if not _is_malformed(p) and p not in symlink_paths and not (repo_root / p).exists()
            ]
            # Stub doc nodes (doc:heading / doc:file) created only as edge
            # TARGETS carry their path in the uid, not file_path (NULL), so
            # the file_path-based stale check above misses them. Parse the
            # uid path-part and flag stale when the file is gone — fossil
            # cites_heading / links_to targets (e.g. a pre-F17
            # `doc:heading:src/docs/...#x` whose source link now resolves to
            # the real `docs/...`). file_path-bearing real headings are
            # excluded by the NULL filter, so no false positives.
            stale_uid_stubs: list[str] = []
            for (su,) in sqlite_conn.execute(
                "SELECT uid FROM graph_nodes WHERE (file_path IS NULL OR file_path = '') "
                "AND (uid LIKE 'doc:heading:%' OR uid LIKE 'doc:file:%')"
            ).fetchall():
                pp = su.split(":", 2)[2].split("#", 1)[0] if su.count(":") >= 2 else ""
                if pp and not _is_malformed(pp) and not (repo_root / pp).exists():
                    stale_uid_stubs.append(su)
            # Fold symlink paths into the malformed bucket (same fix=True
            # delete path, same "extractor should not have emitted this").
            malformed_paths = malformed_paths + symlink_paths
            if malformed_paths or malformed_uids:
                mp_count = 0
                if malformed_paths:
                    mp_count += sqlite_conn.execute(
                        f"SELECT COUNT(*) FROM graph_nodes WHERE file_path IN ({','.join('?' * len(malformed_paths))})",
                        malformed_paths,
                    ).fetchone()[0]
                if malformed_uids:
                    mp_count += len(malformed_uids)
                mp_sample_rows: list = []
                if malformed_paths:
                    mp_sample_rows.extend(
                        sqlite_conn.execute(
                            f"SELECT uid, kind, file_path FROM graph_nodes WHERE file_path IN ({','.join('?' * len(malformed_paths))}) LIMIT 5",
                            malformed_paths,
                        ).fetchall()
                    )
                if malformed_uids and len(mp_sample_rows) < 5:
                    mp_sample_rows.extend(
                        sqlite_conn.execute(
                            f"SELECT uid, kind, file_path FROM graph_nodes WHERE uid IN ({','.join('?' * len(malformed_uids[:5]))}) LIMIT ?",
                            (*malformed_uids[:5], 5 - len(mp_sample_rows)),
                        ).fetchall()
                    )
                issues.append(
                    {
                        "category": "malformed_uid_path",
                        "count": mp_count,
                        "path_count": len(malformed_paths) + len(malformed_uids),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "file_path": r[2]}
                            for r in mp_sample_rows[:5]
                        ],
                    }
                )
                if fix:
                    chunk = 500
                    for i in range(0, len(malformed_paths), chunk):
                        batch = malformed_paths[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE file_path IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    for i in range(0, len(malformed_uids), chunk):
                        batch = malformed_uids[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()
            stale_paths = real_stale_paths
            if stale_paths or stale_uid_stubs:
                stale_node_count = len(stale_uid_stubs)
                sp_sample: list = []
                if stale_paths:
                    stale_node_count += sqlite_conn.execute(
                        f"SELECT COUNT(*) FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))})",
                        stale_paths,
                    ).fetchone()[0]
                    sp_sample = sqlite_conn.execute(
                        f"SELECT uid, kind, file_path FROM graph_nodes WHERE file_path IN ({','.join('?' * len(stale_paths))}) LIMIT 5",
                        stale_paths,
                    ).fetchall()
                if len(sp_sample) < 5 and stale_uid_stubs:
                    sp_sample = (
                        list(sp_sample)
                        + sqlite_conn.execute(
                            f"SELECT uid, kind, file_path FROM graph_nodes WHERE uid IN ({','.join('?' * len(stale_uid_stubs[:5]))}) LIMIT ?",
                            (*stale_uid_stubs[:5], 5 - len(sp_sample)),
                        ).fetchall()
                    )
                issues.append(
                    {
                        "category": "stale_paths",
                        "count": stale_node_count,
                        "path_count": len(stale_paths) + len(stale_uid_stubs),
                        "sample": [
                            {"uid": r[0], "kind": r[1], "file_path": r[2]} for r in sp_sample[:5]
                        ],
                    }
                )
                if fix:
                    chunk = 500
                    for i in range(0, len(stale_paths), chunk):
                        batch = stale_paths[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE file_path IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    for i in range(0, len(stale_uid_stubs), chunk):
                        batch = stale_uid_stubs[i : i + chunk]
                        cur = sqlite_conn.execute(
                            f"DELETE FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                            batch,
                        )
                        fixed_count += int(cur.rowcount or 0)
                    sqlite_conn.commit()

            # 7. Files with parse errors — symbols silently dropped. A file
            # can index "successfully" (no exception) yet have an extractor
            # hit a syntax/parse error on part of it, so some functions /
            # classes are missing. file_index_state.parse_errors_count
            # records the per-file count; the reindex CLI's "errors=0" only
            # counts hard exceptions, so partial extraction was previously
            # invisible — a silent-incomplete-coverage bug. Informational
            # (a few heredoc / markdown parse errors don't corrupt the
            # graph) but MUST be visible so the agent knows node coverage
            # is below 100%.
            try:
                pe_row = sqlite_conn.execute(
                    "SELECT COALESCE(SUM(parse_errors_count), 0), "
                    "COUNT(DISTINCT file_path) FROM file_index_state "
                    "WHERE parse_errors_count > 0"
                ).fetchone()
                pe_total = int(pe_row[0] or 0)
                pe_files = int(pe_row[1] or 0)
            except Exception as exc:  # table absent on a fresh graph
                logger.debug("parse-error probe suppressed: %s", exc)
                pe_total = pe_files = 0
            stats["parse_error_total"] = pe_total
            stats["files_with_parse_errors"] = pe_files
            if pe_files:
                pe_sample = sqlite_conn.execute(
                    "SELECT file_path, parse_errors_count FROM file_index_state "
                    "WHERE parse_errors_count > 0 "
                    "ORDER BY parse_errors_count DESC LIMIT 10"
                ).fetchall()
                issues.append(
                    {
                        "category": "files_with_parse_errors",
                        "severity": "info",
                        "count": pe_files,
                        "parse_error_total": pe_total,
                        "sample": [
                            {"file_path": r[0], "parse_errors": int(r[1])} for r in pe_sample
                        ],
                    }
                )

            # 8. Slowest extractions — per-file duration_ms telemetry
            # (polyglot roadmap E1, migration v28). Informational: budget
            # data for monorepo-scale consumers, never a health failure.
            try:
                slow_rows = sqlite_conn.execute(
                    "SELECT file_path, extractor_chain, duration_ms "
                    "FROM file_index_state WHERE duration_ms IS NOT NULL "
                    "ORDER BY duration_ms DESC LIMIT 10"
                ).fetchall()
            except Exception as exc:  # column absent on a pre-v28 DB
                logger.debug("slowest-extraction probe suppressed: %s", exc)
                slow_rows = []
            if slow_rows:
                stats["slowest_extraction_ms"] = int(slow_rows[0][2])
            # Surface as an issue card only past the worst per-language P95
            # budget (roadmap §7) — a within-budget top-10 is telemetry, not
            # a finding, and a permanent card reads as a problem.
            if slow_rows and int(slow_rows[0][2]) >= _SLOW_EXTRACTION_FLOOR_MS:
                issues.append(
                    {
                        "category": "slowest_extractions",
                        "severity": "info",
                        "count": len(slow_rows),
                        "budget_floor_ms": _SLOW_EXTRACTION_FLOOR_MS,
                        "sample": [
                            {
                                "file_path": r[0],
                                "extractor_chain": r[1],
                                "duration_ms": int(r[2]),
                            }
                            for r in slow_rows
                        ],
                    }
                )

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

    # W7.6 / R4-N9: informational categories (orphaned_external_unresolved)
    # do NOT trip healthy=false. Real issues = anything else.
    _INFORMATIONAL_CATEGORIES = {
        "orphaned_external_unresolved",
        "files_with_parse_errors",
        "slowest_extractions",
    }
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
