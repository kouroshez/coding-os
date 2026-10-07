"""graph_os — the ESM imports of an `.mdx` page and the components it renders.

An MDX page imports components (`import Callout from '../Callout.astro'`) and
renders them as tags; md_links read only its links, so neither made an edge.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..types import EvidenceSignal, GraphEdge
from ._extract_base import EXTRACTOR_ID, ExtractionResult
from ._md_uids import file_uid as doc_file_uid

_IMPORT_RE = re.compile(
    r"""^import\s+(?P<clause>[^'"]+?)\s+from\s+['"](?P<module>[^'"]+)['"]""", re.MULTILINE
)
_TAG_RE = re.compile(r"<([A-Z][\w$]*)(?=[\s/>.])")
_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*")


def emit_mdx_imports(path: str, content: str, result: ExtractionResult) -> None:
    from ..resolve_ts import resolve

    source = doc_file_uid(path)
    modules: dict[str, str] = {}
    for match in _IMPORT_RE.finditer(content):
        specifier = match.group("module")
        resolved = resolve(path, specifier, Path.cwd()) if specifier.startswith(".") else None
        target = f"code:module:{resolved}" if resolved else f"code:module:npm:{specifier}"
        line = content[: match.start()].count("\n") + 1
        _edge(result, source, target, "imports", 0.9, "mdx_import", f"{path}:{line}")
        clause = match.group("clause").replace("type ", "")
        for name in _NAME_RE.findall(clause.replace(" as ", " ")):
            modules[name] = target
    seen: set[str] = set()
    for match in _TAG_RE.finditer(content):
        target = modules.get(match.group(1))
        if target is not None and target not in seen:
            seen.add(target)
            line = content[: match.start()].count("\n") + 1
            _edge(result, source, target, "constructs", 0.8, "mdx_component", f"{path}:{line}")


def _edge(
    result: ExtractionResult,
    source: str,
    target: str,
    kind: str,
    confidence: float,
    signal: str,
    span: str,
) -> None:
    result.edges.append(
        GraphEdge(
            source_uid=source,
            target_uid=target,
            edge_type=kind,
            extractor=EXTRACTOR_ID,
            confidence=confidence,
            source_span=span,
            evidence=(EvidenceSignal(signal, confidence),),
        )
    )
