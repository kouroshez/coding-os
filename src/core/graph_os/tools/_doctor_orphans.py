"""Phantom-orphan classification and the extraction-budget floor for the doctor."""

from __future__ import annotations

import json
import logging
from functools import lru_cache

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
