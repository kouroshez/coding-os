"""Path-integrity checks and the per-file extraction telemetry cards."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from ._doctor_orphans import _SLOW_EXTRACTION_FLOOR_MS

logger = logging.getLogger("graph_os.tools")


def _is_malformed(p: str) -> bool:
    return (
        ("../" in p)
        or ("`" in p)
        or any(c == "\n" or c == "\r" or c == "\t" or ord(c) < 32 for c in p)
    )


def _check_paths(
    sqlite_conn: sqlite3.Connection, repo_root: Path, *, fix: bool
) -> tuple[list[dict[str, Any]], int]:
    issues: list[dict[str, Any]] = []
    fixed_count = 0

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
        if not _is_malformed(p) and (repo_root / p).exists() and (repo_root / p).is_symlink()
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
                    {"uid": r[0], "kind": r[1], "file_path": r[2]} for r in mp_sample_rows[:5]
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
                "sample": [{"uid": r[0], "kind": r[1], "file_path": r[2]} for r in sp_sample[:5]],
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

    return issues, fixed_count


def _check_extraction_telemetry(
    sqlite_conn: sqlite3.Connection,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}

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
                "sample": [{"file_path": r[0], "parse_errors": int(r[1])} for r in pe_sample],
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

    return issues, stats
