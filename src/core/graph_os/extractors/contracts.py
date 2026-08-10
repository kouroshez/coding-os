"""graph_os — service contracts extractor (I.7).

Facade: dispatches a file to the scanner modules for its ecosystem, then turns
every ContractMatch into the route/tool/event node and its edges. The scanners
themselves live one ecosystem per sibling.

DEPENDS:  stdlib only.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import PurePosixPath

from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._contracts_events import (
    _scan_celery,
    _scan_channels_signals,
    _scan_mcp,
    _scan_pubsub,
    _scan_sse,
    _scan_websocket,
)
from ._contracts_go import (
    _scan_chi,
    _scan_cobra,
    _scan_echo,
    _scan_fiber,
    _scan_gin,
    _scan_gorilla,
    _scan_grpc,
    _scan_net_http,
    _scan_urfave_cli,
)
from ._contracts_js import _scan_nest, _scan_nextjs, _scan_ts_emitter
from ._contracts_php import (
    _scan_laravel,
    _scan_whmcs,
    _scan_wordpress,
)
from ._contracts_python import (
    _scan_django_urlpatterns,
    _scan_drf,
    _scan_fastapi,
    _scan_flask,
)
from ._contracts_shared import (
    ContractMatch as ContractMatch,
    _python_file_docstring,
)
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.contracts")
EXTRACTOR_ID = "contracts@v1"

# Dynamic hints — fetch with template literal.
_DYNAMIC_FETCH_RE = re.compile(r"fetch\s*\(\s*`[^`]*\$\{")


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a source file for service contracts."""
    result = ExtractionResult()
    normalised = _normalize_path(path)
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    file_doc_blob = _python_file_docstring(content) if normalised.endswith(".py") else None

    file_node = GraphNode(
        uid=f"code:file:{normalised}",
        kind="code:file",
        label=PurePosixPath(normalised).name,
        file_path=normalised,
        lang=_lang_for(normalised),
        doc_blob=file_doc_blob,
        content_hash=content_hash,
        metadata={"extractor": EXTRACTOR_ID},
    )
    result.nodes.append(file_node)

    matches: list[ContractMatch] = []
    try:
        if normalised.endswith(".py"):
            matches.extend(_scan_fastapi(content))
            matches.extend(_scan_flask(content))
            matches.extend(_scan_drf(content))
            matches.extend(_scan_django_urlpatterns(content))
            matches.extend(_scan_mcp(content))
            matches.extend(_scan_celery(content))
            matches.extend(_scan_channels_signals(content))
            matches.extend(_scan_websocket(content))
            # R4: pub/sub + SSE patterns broaden handles_event surface.
            matches.extend(_scan_pubsub(content, framework_label="python"))
            matches.extend(_scan_sse(content))
        elif normalised.endswith(".ts") or normalised.endswith(".tsx"):
            matches.extend(_scan_nextjs(content, path=normalised))
            matches.extend(_scan_nest(content))
            # R4: TS-side event listeners.
            matches.extend(_scan_pubsub(content, framework_label="ts"))
            matches.extend(_scan_ts_emitter(content))
        elif normalised.endswith(".go"):
            matches.extend(_scan_fiber(content))
            matches.extend(_scan_gin(content))
            matches.extend(_scan_echo(content))
            matches.extend(_scan_chi(content))
            matches.extend(_scan_gorilla(content))
            matches.extend(_scan_net_http(content))
            matches.extend(_scan_grpc(content))
            matches.extend(_scan_cobra(content))
            matches.extend(_scan_urfave_cli(content))
        elif normalised.endswith(".php"):
            matches.extend(_scan_laravel(content))
            matches.extend(_scan_wordpress(content))
            matches.extend(_scan_whmcs(content, path=normalised))
    except Exception as exc:
        result.parse_errors.append(ParseError(kind="fatal", detail=str(exc)))

    if _DYNAMIC_FETCH_RE.search(content):
        # A fetch() with a template-literal route is parsed fine — its target
        # is just not statically resolvable. That is NOT a parse error (it was
        # wrongly inflating the count, same class as shell `dynamic`); note it
        # at debug instead (TASK-303).
        logger.debug("opaque fetch route (template literal) in %s", normalised)

    for hit in matches:
        _emit(file_node.uid, hit, normalised=normalised, result=result)

    # S3: Folder→...→File spine + File→Route/Tool/Event direct
    # ``contains`` edges for the tree-view. The ``handles_route`` /
    # ``handles_tool`` / ``handles_event`` edges already emitted by
    # ``_emit`` are semantic (which file owns which surface); the
    # ``contains`` edges added below are structural (tree placement).
    emit_contains_spine(
        file_path=path,
        file_uid_=file_node.uid,
        result=result,
        extractor_id=EXTRACTOR_ID,
    )
    for hit in matches:
        contract_uid = _contract_uid(hit)
        result.edges.append(
            GraphEdge(
                source_uid=file_node.uid,
                target_uid=contract_uid,
                edge_type="contains",
                extractor=EXTRACTOR_ID,
                confidence=1.0,
            )
        )

    _promote_stubs(result)
    return result


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


_HTTP_NOISE_PATHS = {"/x", "/y", "/z", "/foo", "/bar", "/test", "/path"}


def _looks_like_noise(match: ContractMatch) -> bool:
    if match.kind == "http":
        return match.path in _HTTP_NOISE_PATHS
    return False


def _emit(
    source_uid: str,
    match: ContractMatch,
    *,
    normalised: str,
    result: ExtractionResult,
) -> None:
    if _looks_like_noise(match):
        return
    target_uid = _contract_uid(match)
    label = _contract_label(match)
    metadata = {
        "kind": match.kind,
        "framework": match.framework,
        "method": match.method,
        "path": match.path,
        "handler": match.handler,
        "extractor": EXTRACTOR_ID,
    }
    if match.derivation:
        metadata["derivation"] = match.derivation
    if match.note:
        metadata["note"] = match.note
    result.nodes.append(
        GraphNode(
            uid=target_uid,
            kind=_node_kind(match),
            label=label,
            file_path=normalised,
            start_line=match.line,
            lang=_lang_for(normalised),
            metadata=metadata,
        )
    )
    edge_type = {
        "http": "handles_route",
        "mcp": "handles_tool",
        "grpc": "handles_tool",
        "event": "handles_event",
        "websocket": "handles_route",
        "cli": "handles_command",
    }.get(match.kind, "handles_route")

    evidence = (EvidenceSignal(f"{match.framework}_{match.kind}", match.confidence),)
    result.edges.append(
        GraphEdge(
            source_uid=source_uid,
            target_uid=target_uid,
            edge_type=edge_type,
            extractor=EXTRACTOR_ID,
            confidence=match.confidence,
            source_span=f"{normalised}:{match.line}",
            evidence=evidence,
        )
    )
    if match.handler:
        # Resolve Python handlers to the real same-file function node
        # (code_python emits it in the same reindex; _next_def_name yields
        # a def in THIS file). The old unresolved-stub target left
        # references/impact/rename empty for every route + MCP handler.
        # Non-.py handlers keep the stub (no same-file table).
        if normalised.endswith(".py"):
            handler_uid = f"code:function:{normalised}::{match.handler}"
        elif normalised.endswith(".php"):
            if "@" in match.handler:
                # Laravel controller handler `Ctrl@method` — cross-file. Emit a
                # resolvable stub the `link_php_handlers` post-pass binds to the
                # real code:method node (uid …::Ctrl.method).
                handler_uid = f"code:external:phproute:{match.handler.replace('@', '.')}"
            elif "::" not in match.handler:
                # Bare same-file handler (WP callback / WHMCS module fn).
                handler_uid = f"code:function:{normalised}::{match.handler}"
            else:
                handler_uid = f"code:external:unresolved:{match.handler}"
        else:
            handler_uid = f"code:external:unresolved:{match.handler}"
        result.edges.append(
            GraphEdge(
                source_uid=target_uid,
                target_uid=handler_uid,
                edge_type="calls",
                extractor=EXTRACTOR_ID,
                confidence=match.confidence * 0.9,
                source_span=f"{normalised}:{match.line}",
            )
        )


def _contract_uid(match: ContractMatch) -> str:
    if match.kind == "http":
        return f"cos:route:{match.method.upper()}:{match.path}"
    if match.kind == "mcp":
        return f"cos:mcp_tool:{match.path}"
    if match.kind == "grpc":
        return f"cos:route:grpc:{match.path}"
    if match.kind == "event":
        return f"cos:route:event:{match.framework}:{match.path}"
    if match.kind == "websocket":
        return f"cos:route:ws:{match.path}"
    if match.kind == "cli":
        return f"cos:cli:{match.framework}:{match.path}"
    return f"cos:route:{match.kind}:{match.path}"


def _contract_label(match: ContractMatch) -> str:
    if match.kind == "http":
        return f"{match.method.upper()} {match.path}"
    if match.kind == "mcp":
        return f"mcp:{match.path}"
    return f"{match.framework}:{match.path}"


def _node_kind(match: ContractMatch) -> str:
    return {
        "mcp": "cos:mcp_tool",
        "http": "cos:route",
        "grpc": "cos:route",
        "event": "cos:route",
        "websocket": "cos:route",
        "cli": "cos:cli_command",
    }.get(match.kind, "cos:route")


def _lang_for(path: str) -> str:
    if path.endswith(".py"):
        return "py"
    if path.endswith(".ts"):
        return "ts"
    if path.endswith(".tsx"):
        return "tsx"
    if path.endswith(".go"):
        return "go"
    return "txt"


__all__ = ["EXTRACTOR_ID", "ContractMatch", "extract"]
