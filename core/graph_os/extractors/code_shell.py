"""graph-os — shell script extractor (I.7).

PURPOSE:  Map a `.sh` file to code:file / code:module + `source` /
          `calls` edges. Primary enterprise use-case is the coding-os
          hook system — `source cos-env.sh` chains, Makefile-invoked
          scripts, and hook cross-calls all become navigable graph
          edges.
INPUT:    file path + raw text (pure extractor).
OUTPUT:   ExtractionResult.
DEPENDS:  stdlib regex only.
NOTES:    The shell grammar is intentionally narrow — we track:
            * `source X` and `. X` includes (sourced-from edges)
            * direct invocations of other `.sh` files in the repo
            * `cos_log_hook name` calls (coding-os hook probe)
          Anything dynamic (variable-expansion paths, `eval`, subshells)
          is skipped with a `dynamic` parse_error.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_shell")
EXTRACTOR_ID = "code_shell@v1"


_COMMENT_RE = re.compile(r"(?<!\\)#[^\n]*")
_SOURCE_RE = re.compile(
    r"^\s*(?:source|\.)\s+(?P<path>[^\s;&|]+)", re.MULTILINE
)
_CALL_SCRIPT_RE = re.compile(
    r"""^\s*
        (?:bash\s+|sh\s+)?
        (?P<path>[^\s;&|]+?\.sh)
        (?:\s|$)
    """,
    re.VERBOSE | re.MULTILINE,
)
_COS_LOG_HOOK_RE = re.compile(r"\bcos_log_hook\s+(?P<name>[A-Za-z0-9_-]+)")
_FUNCTION_DEF_RE = re.compile(
    r"""^\s*
        (?:function\s+)?
        (?P<name>[A-Za-z_][\w-]*)
        \s*\(\)\s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)
_DYNAMIC_HINT_RE = re.compile(r"\$\(|\$\{|`|\beval\b")


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


def _resolve_script_target(origin: str, target: str) -> str:
    """Resolve a `source`/`./script.sh` target to a repo-rooted uid."""
    target = target.strip().strip("'\"")
    if not target:
        return ""
    if target.startswith("$"):
        return ""  # dynamic
    if target.startswith("/"):
        return f"code:file:{_normalize_path(target.lstrip('/'))}"
    origin_dir = PurePosixPath(_normalize_path(origin)).parent
    resolved = (origin_dir / target).as_posix()
    parts: list[str] = []
    for part in resolved.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return f"code:file:{'/'.join(parts)}"


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a shell script → nodes + edges.

    PURPOSE:      Per-file write path. The coding-os hook graph is the
                  primary consumer — `auto-reindex-docs.sh` calls this
                  when a `core/hooks/*.sh` file changes.
    INPUT:        repo-relative path + raw script.
    OUTPUT:       ExtractionResult.
    NOTES:        Never raises.
    """
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    result.nodes.append(
        GraphNode(
            uid=file_uid(path),
            kind="code:file",
            label=PurePosixPath(normalised).name,
            file_path=normalised,
            lang="sh",
            content_hash=content_hash,
            metadata={"extractor": EXTRACTOR_ID},
        )
    )
    mod = GraphNode(
        uid=module_uid(path),
        kind="code:module",
        label=PurePosixPath(normalised).stem,
        file_path=normalised,
        lang="sh",
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(mod)
    result.edges.append(
        GraphEdge(
            source_uid=file_uid(path),
            target_uid=mod.uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )

    stripped = _COMMENT_RE.sub("", content)

    for match in _SOURCE_RE.finditer(stripped):
        raw_target = match.group("path")
        line = stripped[: match.start()].count("\n") + 1
        resolved = _resolve_script_target(path, raw_target)
        if not resolved:
            result.parse_errors.append(
                ParseError(
                    kind="dynamic",
                    detail=f"dynamic source path: {raw_target}",
                    line=line,
                )
            )
            continue
        result.edges.append(
            GraphEdge(
                source_uid=mod.uid,
                target_uid=resolved,
                edge_type="imports",
                extractor=EXTRACTOR_ID,
                confidence=0.9,
                source_span=f"{normalised}:{line}",
                evidence=(EvidenceSignal("shell_source", 0.9),),
            )
        )

    for match in _CALL_SCRIPT_RE.finditer(stripped):
        raw_target = match.group("path")
        # Skip if this is the `source` path we already captured.
        line = stripped[: match.start()].count("\n") + 1
        # Avoid matching on the file itself.
        if raw_target.endswith(PurePosixPath(normalised).name) and "/" not in raw_target:
            continue
        resolved = _resolve_script_target(path, raw_target)
        if not resolved:
            continue
        # If we already emitted a `source` edge to this target, skip.
        already = any(
            e.source_uid == mod.uid and e.target_uid == resolved and e.edge_type == "imports"
            for e in result.edges
        )
        if already:
            continue
        result.edges.append(
            GraphEdge(
                source_uid=mod.uid,
                target_uid=resolved,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=0.7,
                source_span=f"{normalised}:{line}",
                evidence=(EvidenceSignal("shell_call_script", 0.7),),
            )
        )

    for match in _FUNCTION_DEF_RE.finditer(stripped):
        name = match.group("name")
        line = stripped[: match.start()].count("\n") + 1
        fn_uid = f"code:function:{_normalize_path(path)}::{name}"
        result.nodes.append(
            GraphNode(
                uid=fn_uid,
                kind="code:function",
                label=name,
                file_path=normalised,
                start_line=line,
                signature=f"{name}() {{ ... }}",
                lang="sh",
                metadata={"extractor": EXTRACTOR_ID},
            )
        )
        result.edges.append(
            GraphEdge(
                source_uid=mod.uid,
                target_uid=fn_uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )
        # S3: File→Function direct edge for the tree-view spine.
        result.edges.append(
            GraphEdge(
                source_uid=file_uid(path),
                target_uid=fn_uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )

    for match in _COS_LOG_HOOK_RE.finditer(stripped):
        hook_name = match.group("name")
        line = stripped[: match.start()].count("\n") + 1
        result.edges.append(
            GraphEdge(
                source_uid=mod.uid,
                target_uid=f"cos:hook:{hook_name}",
                edge_type="handles_tool",
                extractor=EXTRACTOR_ID,
                confidence=0.95,
                source_span=f"{normalised}:{line}",
                evidence=(EvidenceSignal("cos_log_hook_call", 0.95),),
            )
        )

    if _DYNAMIC_HINT_RE.search(stripped):
        result.parse_errors.append(
            ParseError(
                kind="dynamic_shell",
                detail="script uses subshells / variable paths / eval — "
                "edges may be incomplete",
            )
        )

    # S3: Folder→...→File spine.
    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid(path),
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    _promote_stubs(result)
    return result


__all__ = ["EXTRACTOR_ID", "extract", "file_uid", "module_uid"]
