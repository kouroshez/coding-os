"""Orphan classification and the zero-edge node check for the doctor."""

from __future__ import annotations

import json
import logging
import sqlite3
from functools import lru_cache
from typing import Any

logger = logging.getLogger("graph_os.tools")

# Worst per-language P95 extraction budget (roadmap §7) — the doctor lists
# slowest_extractions as an issue card only above this.
_SLOW_EXTRACTION_FLOOR_MS = 500


@lru_cache(maxsize=1)
def _current_extractor_ids() -> frozenset[str]:
    try:
        from ..extractors import registered_extractor_ids

        return registered_extractor_ids()
    except Exception:
        return frozenset()


def _is_phantom_orphan(
    kind: str | None,
    file_path: str | None,
    uid: str | None = None,
    metadata_json: str | None = None,
) -> bool:
    uid = uid or ""
    # Code-line ref mis-noded as a task by a superseded extractor — a real
    # task uid is `task:file:TASK-NNN` / `task:file:unknown:<path.md>`, never
    # one carrying a `path.py#L1234` source anchor. Zero-edge garbage.
    if uid.startswith("task:file:") and "#L" in uid:
        return True
    extractor_id: str | None = None
    if metadata_json:
        try:
            metadata = json.loads(metadata_json)
            extractor_id = metadata.get("extractor")
            # A stub exists only to anchor an edge; zero edges means the
            # minting edge is gone (golden-tree purge, doc edit) and
            # re-extraction of the source re-mints it if still referenced.
            if metadata.get("stub"):
                return True
        except (ValueError, AttributeError) as exc:
            logger.debug("orphan metadata unreadable for %s: %s", uid, exc)
    # Extractor renames (code_ts_ts@v1 → code_ts@v1, code_shell@v1 → @v2)
    # strand rows the extractor-scoped prune-before-reindex can never
    # match. Empty registry = imports failed = registry unknown; skip the
    # rule rather than treat every id as legacy.
    current_ids = _current_extractor_ids()
    if extractor_id and current_ids and extractor_id not in current_ids:
        return True
    # Zero-edge module / external-doc stub with no on-disk path: a dangling
    # import target (e.g. a stdlib module) or a dead external link left when
    # the referencing edge moved. Idempotent re-extraction recreates it if
    # still referenced, so pruning the orphan is safe.
    if kind in ("module", "doc_external") and not file_path:
        return True
    # Zero-edge file/doc_file with NULL/extensionless path = stub or dir-phantom.
    if kind not in ("file", "doc_file"):
        return False
    if not file_path:
        return True
    return "." not in file_path.rsplit("/", 1)[-1]


def _check_orphans(
    sqlite_conn: sqlite3.Connection, *, fix: bool
) -> tuple[list[dict[str, Any]], dict[str, Any], int]:
    issues: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    fixed_count = 0

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
                "sample": [{"uid": r[0], "kind": r[1], "label": r[2]} for r in real_orphans[:5]],
            }
        )
    if phantom_orphans:
        issues.append(
            {
                "category": "orphaned_phantom",
                "count": len(phantom_orphans),
                "sample": [{"uid": r[0], "kind": r[1], "label": r[2]} for r in phantom_orphans[:5]],
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
                "sample": [{"uid": r[0], "kind": r[1], "label": r[2]} for r in stub_orphans[:5]],
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

    return issues, stats, fixed_count
