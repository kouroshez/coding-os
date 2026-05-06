"""graph_os — YAML extractor (I.7).

DEPENDS:  pyyaml (already in base `dependencies`).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import PurePosixPath
from typing import Any

from ..types import GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_yaml")
EXTRACTOR_ID = "code_yaml@v1"

# Keys we look at specifically — others are surfaced as frontmatter-
# style nodes but do not emit typed edges.
_REFERENCE_KEYS = {
    "ssot_of",
    "ssot",
    "read_first",
    "references",
    "includes",
    "imports",
    "scaffold",
    "rules",
    "hooks",
    "skills",
}


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:yaml:{_normalize_path(path)}"


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a YAML file → nodes + edges."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    file_node = GraphNode(
        uid=file_uid(path),
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang="yaml",
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)
    module = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=PurePosixPath(normalised).stem,
        file_path=normalised,
        lang="yaml",
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(module)
    result.edges.append(
        GraphEdge(
            source_uid=file_node.uid,
            target_uid=module.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    try:
        import yaml
    except ImportError:
        result.parse_errors.append(
            ParseError(kind="dep_missing", detail="pyyaml unavailable")
        )
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    try:
        data = yaml.safe_load(content)
    except Exception as exc:  # noqa: BLE001
        result.parse_errors.append(ParseError(kind="yaml_parse_error", detail=str(exc)))
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    if data is None:
        emit_contains_spine(
            file_path=path,
            file_uid_=file_node.uid,
            result=result,
            extractor_id=EXTRACTOR_ID,
        )
        _promote_stubs(result)
        return result

    if isinstance(data, dict):
        _walk(data, normalised=normalised, parent_uid=module.uid, result=result, prefix="")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _walk(item, normalised=normalised, parent_uid=module.uid, result=result, prefix=f"[{i}]")

    # S3: Folder→...→File spine.
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    _promote_stubs(result)
    return result


def _walk(
    value: Any,
    *,
    normalised: str,
    parent_uid: str,
    result: ExtractionResult,
    prefix: str,
) -> None:
    if isinstance(value, dict):
        for key, sub in value.items():
            current_path = f"{prefix}.{key}" if prefix else str(key)
            _emit_key_node(
                normalised=normalised,
                parent_uid=parent_uid,
                result=result,
                key=str(key),
                value=sub,
                path=current_path,
            )
            _walk(
                sub,
                normalised=normalised,
                parent_uid=parent_uid,
                result=result,
                prefix=current_path,
            )
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _walk(
                item,
                normalised=normalised,
                parent_uid=parent_uid,
                result=result,
                prefix=f"{prefix}[{i}]",
            )


def _emit_key_node(
    *,
    normalised: str,
    parent_uid: str,
    result: ExtractionResult,
    key: str,
    value: Any,
    path: str,
) -> None:
    uid = f"doc:frontmatter:{normalised}::{path}"
    scalar = _stringify_scalar(value)
    label = f"{key}={scalar[:80]}" if scalar else key
    result.nodes.append(
        GraphNode(
            uid=uid,
            kind="doc:frontmatter_key",
            label=label,
            file_path=normalised,
            lang="yaml",
            metadata={"key": key, "value": scalar, "path": path, "extractor": EXTRACTOR_ID},
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=parent_uid,
            target_uid=uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    if key not in _REFERENCE_KEYS or scalar is None:
        return

    # Emit reference edges — ssot_of, references_doc, etc.
    edge_type = {
        "ssot_of": "ssot_of",
        "ssot": None,  # boolean flag, not a pointer
        "read_first": "references_doc",
        "references": "references_doc",
        "includes": "imports",
        "imports": "imports",
        "scaffold": "references_doc",
        "rules": "references_doc",
        "hooks": "references_doc",
        "skills": "references_doc",
    }.get(key)
    if edge_type is None:
        return

    for target in _iter_targets(value):
        target_uid = _classify_target(target)
        if not target_uid:
            continue
        result.edges.append(
            GraphEdge(
                source_uid=parent_uid,
                target_uid=target_uid,
                edge_type=edge_type,
                extractor=EXTRACTOR_ID,
                confidence=0.8,
                source_span=f"{normalised}:{path}",
            )
        )


def _stringify_scalar(value: Any) -> str:
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if value is None:
        return ""
    return type(value).__name__  # list/dict summary


def _iter_targets(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, str)]
    return []


def _classify_target(target: str) -> str | None:
    target = target.strip()
    if not target:
        return None
    if target.startswith(("http://", "https://")):
        return f"doc:external:{target}"
    normalised = _normalize_path(target)
    if target.endswith(".md"):
        return f"doc:file:{normalised}"
    if target.endswith(".sh"):
        return f"code:file:{normalised}"
    if target.endswith((".yaml", ".yml")):
        return f"code:file:{normalised}"
    if target.endswith(".py"):
        return f"code:file:{normalised}"
    if "/" in target:
        return f"code:file:{normalised}"
    # Bare name → assume coding-os artifact identifier.
    return f"cos:identifier:{target}"


__all__ = ["EXTRACTOR_ID", "extract", "file_uid", "module_uid"]
