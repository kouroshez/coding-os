"""graph_os — markdown link + heading + frontmatter extractor (I.2).

DEPENDS:  stdlib regex; frontmatter is parsed from the HTML comment or
          YAML-fence convention used across coding-os docs.

Module layout
  - `_extract_base`  result container, path normalisation, contains spine,
                     stub promotion — the leaf every extractor imports
  - `_md_uids`       doc uid grammar + governance-path classification
  - `_md_resolve`    link-target resolution (relative, anchor, symlink, asset)
  - `_md_read_next`  opening-block `Read next:` scanning
  - `_md_sections`   frontmatter, heading, and link body scans
  - this module      document assembly, plus the shared-primitive re-exports
                     every sibling extractor imports from `.md_links`
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath

from ..types import GraphNode
from ._extract_base import (
    EXTRACTOR_ID,
    ExtractionResult,
    ParseError,
    _normalize_path as _normalize_path,
    _promote_stubs as _promote_stubs,
    emit_contains_spine,
    folder_uid,
)
from ._md_read_next import _extract_opening_block_reads
from ._md_resolve import (
    _resolve_link as _resolve_link,
    _resolve_through_symlink as _resolve_through_symlink,
)
from ._md_sections import (
    _FENCED_CODE_RE,
    _extract_doc_blob,
    _extract_frontmatter,
    _extract_headings,
    _extract_links,
)
from ._md_uids import (
    _classify_governance_path,
    file_uid,
    frontmatter_key_uid,
    heading_uid,
    slugify,
)

logger = logging.getLogger("graph_os.extractors.md_links")


def extract(
    path: str,
    content: str,
) -> ExtractionResult:
    """Parse a Markdown document → nodes + edges."""
    result = ExtractionResult()
    try:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        normalised = _normalize_path(path)
        special_kind, special_label = _classify_governance_path(normalised)

        file_node = GraphNode(
            uid=file_uid(path),
            kind=special_kind or "doc:file",
            label=special_label or PurePosixPath(normalised).name,
            file_path=normalised,
            lang="md",
            doc_blob=_extract_doc_blob(content),
            content_hash=content_hash,
            metadata={"extractor": EXTRACTOR_ID},
        )
        result.nodes.append(file_node)

        # Frontmatter FIRST so linked docs get ssot/read_next edges even
        # when headings / body parsing fails later.
        _extract_frontmatter(path, content, result)

        # Opening-block "Read next:" / "> N:" → read_next edges. Runs after
        # frontmatter so duplicate-href dedupe inside the scan only fires
        # within the body. Frontmatter `reads:[…]` is handled inline via
        # `_emit_read_next_targets` to keep both forms graph-symmetric.
        # Strip fenced code first — so a `Read next:` line
        # that lives inside a ```bash``` block does not produce a false edge.
        _opening_block_content = _FENCED_CODE_RE.sub("", content)
        _extract_opening_block_reads(path, _opening_block_content, result)

        # Heading scan builds the containment tree AND a slug→uid map
        # for subsequent in-page fragment resolution.
        headings = _extract_headings(path, content, result)

        # Strip fenced code before link scan so ``[x](y)`` inside a code
        # block does not produce a false edge.
        cleaned = _FENCED_CODE_RE.sub("", content)
        _extract_links(path, cleaned, headings, result)

        # S3: attach Folder→...→File spine so the SPA tree-view always
        # has a connected root. Idempotent on uid — parallel extractors
        # emit identical folder uids and bulk_upsert de-dupes.
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )

        # Promote any edge-only uid (link target the extractor does not
        # own the source for) into a stub node so the backend's edge
        # write does not raise ValueError for unknown uids. Upserting
        # the extracted nodes in another pass will replace the stub
        # with the real row — uid is the join key.
        _promote_stubs(result)

        return result
    except Exception as exc:
        logger.debug("md_links.extract(%s) fatal error: %s", path, exc)
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))
        return result


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


__all__ = [
    "EXTRACTOR_ID",
    "ExtractionResult",
    "ParseError",
    "emit_contains_spine",
    "extract",
    "file_uid",
    "folder_uid",
    "frontmatter_key_uid",
    "heading_uid",
    "slugify",
]
