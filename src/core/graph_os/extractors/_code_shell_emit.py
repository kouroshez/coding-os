"""graph_os — shell extractor uid derivation + node/edge emission."""

from __future__ import annotations

import logging
import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from .md_links import ExtractionResult, _normalize_path

logger = logging.getLogger("graph_os.extractors.code_shell")
EXTRACTOR_ID = "code_shell@v2"


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


_DIRNAME_SELF_RE = re.compile(r"""^\$\(dirname\s+["']?\$\{?(?:0|BASH_SOURCE\[0\])\}?["']?\)/?""")


def _resolve_script_target(origin: str, target: str) -> str:
    """Resolve a `source`/`./script.sh` target to a repo-rooted uid."""
    target = target.strip().strip("'\"")
    if not target:
        return ""
    # Common idiom: `$(dirname "$0")/helper.sh` and friends. The substitution
    # resolves to the directory of the running script, which is exactly the
    # origin file's parent directory. Rewrite to a relative path so the
    # standard resolver can take over.
    stripped = _DIRNAME_SELF_RE.sub("", target)
    if stripped != target:
        target = stripped
    if target.startswith("$") or target.startswith("`"):
        return ""  # still dynamic after rewrite
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


def _emit_function(
    name: str, line: int, path: str, normalised: str, result: ExtractionResult, mod_uid: str
) -> None:
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
            source_uid=mod_uid,
            target_uid=fn_uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )
    result.edges.append(
        GraphEdge(
            source_uid=file_uid(path),
            target_uid=fn_uid,
            edge_type="contains",
            extractor=EXTRACTOR_ID,
            confidence=1.0,
        )
    )


def _emit_source_edge(
    raw_target: str,
    line: int,
    path: str,
    normalised: str,
    result: ExtractionResult,
    mod_uid: str,
) -> None:
    resolved = _resolve_script_target(path, raw_target)
    if not resolved:
        # A `source "$VAR/x.sh"` whose path is built from a runtime variable
        # is expected and successfully parsed — just not statically
        # resolvable. That is NOT a parse error (it was wrongly inflating the
        # shell parse-error count ~14x); log at debug and move on.
        logger.debug("unresolved dynamic source in %s: %s", normalised, raw_target)
        return
    result.edges.append(
        GraphEdge(
            source_uid=mod_uid,
            target_uid=resolved,
            edge_type="imports",
            extractor=EXTRACTOR_ID,
            confidence=0.9,
            source_span=f"{normalised}:{line}",
            evidence=(EvidenceSignal("shell_source", 0.9),),
        )
    )


def _emit_call_edge(
    raw_target: str,
    line: int,
    path: str,
    normalised: str,
    result: ExtractionResult,
    mod_uid: str,
) -> None:
    if raw_target.endswith(PurePosixPath(normalised).name) and "/" not in raw_target:
        return
    resolved = _resolve_script_target(path, raw_target)
    if not resolved:
        return
    already = any(
        e.source_uid == mod_uid and e.target_uid == resolved and e.edge_type == "imports"
        for e in result.edges
    )
    if already:
        return
    result.edges.append(
        GraphEdge(
            source_uid=mod_uid,
            target_uid=resolved,
            edge_type="calls",
            extractor=EXTRACTOR_ID,
            confidence=0.7,
            source_span=f"{normalised}:{line}",
            evidence=(EvidenceSignal("shell_call_script", 0.7),),
        )
    )


def _emit_log_hook_edge(
    hook_name: str,
    line: int,
    normalised: str,
    result: ExtractionResult,
    mod_uid: str,
) -> None:
    result.edges.append(
        GraphEdge(
            source_uid=mod_uid,
            target_uid=f"cos:hook:{hook_name}",
            edge_type="handles_tool",
            extractor=EXTRACTOR_ID,
            confidence=0.95,
            source_span=f"{normalised}:{line}",
            evidence=(EvidenceSignal("cos_log_hook_call", 0.95),),
        )
    )
