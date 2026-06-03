"""graph_os — shell script extractor.

Tree-sitter-bash primary parser. Falls back to regex when tree-sitter is
unavailable so the extractor keeps producing nodes/edges on lean installs.

Migrated from regex-only per docs/playbooks/polyglot-extractor-roadmap.md
(Epic A1). Same UIDs + edge types as before so the migration is a drop-in;
the wins are (a) no false positives from comments/heredocs/strings and
(b) parse_errors_count tied to real tree-sitter ERROR nodes, not the
spurious "dynamic content present" hint that flagged 96% of shell files.
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
EXTRACTOR_ID = "code_shell@v2"

# ---------------------------------------------------------------------------
# Tree-sitter parse path
# ---------------------------------------------------------------------------

try:
    from .. import tree_sitter_overlay as _ts_overlay

    _TS_AVAILABLE = _ts_overlay.is_available()
except ImportError:
    _ts_overlay = None  # type: ignore[assignment]
    _TS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Regex fallback (only used when tree-sitter unavailable)
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"(?<!\\)#[^\n]*")
# E10: heredoc-aware stripping so the regex-fallback doesn't false-match
# `func_in_heredoc() { }` inside `<<EOF ... EOF` as a real function def.
_HEREDOC_RE = re.compile(
    r"<<-?\s*['\"]?(?P<tag>\w+)['\"]?\n[\s\S]*?^[ \t]*(?P=tag)\b",
    re.MULTILINE,
)
_SOURCE_RE = re.compile(r"^\s*(?:source|\.)\s+(?P<path>[^\s;&|]+)", re.MULTILINE)
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


# ---------------------------------------------------------------------------
# UID helpers
# ---------------------------------------------------------------------------


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(path: str) -> str:
    return f"code:module:{_normalize_path(path)}"


_DIRNAME_SELF_RE = re.compile(
    r"""^\$\(dirname\s+["']?\$\{?(?:0|BASH_SOURCE\[0\])\}?["']?\)/?"""
)


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


# ---------------------------------------------------------------------------
# Tree-sitter walker
# ---------------------------------------------------------------------------


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
        result.parse_errors.append(
            ParseError(
                kind="dynamic",
                detail=f"dynamic source path: {raw_target}",
                line=line,
            )
        )
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


def _enclosing_function_uid(node, content_bytes: bytes, path: str) -> str | None:
    cur = node.parent
    while cur is not None:
        if cur.type == "function_definition":
            for ch in cur.children:
                if ch.type in ("word", "concatenation"):
                    nm = _ts_overlay.node_text(ch, content_bytes).strip()
                    return f"code:function:{_normalize_path(path)}::{nm}" if nm else None
        cur = cur.parent
    return None


def _walk_ts(
    root,
    content_bytes: bytes,
    path: str,
    normalised: str,
    mod_uid: str,
    result: ExtractionResult,
) -> int:
    """Walk the tree-sitter-bash AST. Returns ERROR-node count."""
    assert _ts_overlay is not None  # _TS_AVAILABLE gate guards caller
    # Pass 1: collect locally-defined function names so intra-script calls
    # resolve (a command matching a same-file function = a real call edge).
    local_funcs: dict[str, str] = {}
    pre = [root]
    while pre:
        n = pre.pop()
        if n.type == "function_definition":
            for ch in n.children:
                if ch.type in ("word", "concatenation"):
                    nm = _ts_overlay.node_text(ch, content_bytes).strip()
                    if nm:
                        local_funcs[nm] = f"code:function:{_normalize_path(path)}::{nm}"
                    break
        pre.extend(n.children)
    seen_calls: set[tuple[str, str]] = set()
    err_count = 0
    stack = [root]
    while stack:
        node = stack.pop()
        ntype = node.type
        if ntype == "ERROR":
            err_count += 1
            stack.extend(reversed(list(node.children)))
            continue
        if ntype == "function_definition":
            # First named child is the function name (word/concatenation).
            name = ""
            for child in node.children:
                if child.type in ("word", "concatenation"):
                    name = _ts_overlay.node_text(child, content_bytes).strip()
                    break
            if name:
                line = node.start_point[0] + 1
                _emit_function(name, line, path, normalised, result, mod_uid)
            stack.extend(reversed(list(node.children)))
            continue
        if ntype == "command":
            # Children: command_name then optional args.
            cmd_name = ""
            args: list[tuple[str, int]] = []
            for i, child in enumerate(node.children):
                txt = _ts_overlay.node_text(child, content_bytes)
                if i == 0 and child.type == "command_name":
                    cmd_name = txt.strip()
                else:
                    args.append((txt.strip(), child.start_point[0] + 1))
            line = node.start_point[0] + 1
            if cmd_name in ("source", "."):
                if args:
                    _emit_source_edge(args[0][0], line, path, normalised, result, mod_uid)
            elif cmd_name == "cos_log_hook":
                if args:
                    hook = args[0][0]
                    if re.fullmatch(r"[A-Za-z0-9_-]+", hook):
                        _emit_log_hook_edge(hook, line, normalised, result, mod_uid)
            elif cmd_name in ("bash", "sh"):
                # `bash script.sh` invocation pattern.
                for txt, l in args:
                    if txt.endswith(".sh"):
                        _emit_call_edge(txt, l, path, normalised, result, mod_uid)
                        break
            elif cmd_name.endswith(".sh"):
                # Direct `./script.sh` or `script.sh` invocation.
                _emit_call_edge(cmd_name, line, path, normalised, result, mod_uid)
            elif cmd_name in local_funcs:
                # GD: invocation of a function defined in THIS file — a real
                # intra-script call. Source = enclosing function (tree scope)
                # or the module when called at top level.
                tgt = local_funcs[cmd_name]
                src = _enclosing_function_uid(node, content_bytes, path) or mod_uid
                key = (src, tgt)
                if src != tgt and key not in seen_calls:
                    seen_calls.add(key)
                    result.edges.append(
                        GraphEdge(
                            source_uid=src,
                            target_uid=tgt,
                            edge_type="calls",
                            extractor=EXTRACTOR_ID,
                            confidence=0.9,
                            source_span=f"{normalised}:{line}",
                            evidence=(EvidenceSignal("shell_local_call", 0.9),),
                        )
                    )
            stack.extend(reversed(list(node.children)))
            continue
        stack.extend(reversed(list(node.children)))
    return err_count


# ---------------------------------------------------------------------------
# Regex fallback (only when tree-sitter is unavailable)
# ---------------------------------------------------------------------------


def _walk_regex(
    content: str,
    path: str,
    normalised: str,
    mod_uid: str,
    result: ExtractionResult,
) -> None:
    # E10: blank heredoc bodies first (preserving line count so source
    # spans stay correct) so `<<EOF\nfake_func() { } \nEOF` cannot
    # spawn a phantom function node.
    def _blank_heredoc(match: re.Match[str]) -> str:
        # Keep the opener + tag, blank the body, keep the closing tag.
        text = match.group(0)
        return re.sub(r"[^\n]", " ", text)

    stripped = _HEREDOC_RE.sub(_blank_heredoc, content)
    stripped = _COMMENT_RE.sub("", stripped)

    for match in _SOURCE_RE.finditer(stripped):
        raw_target = match.group("path")
        line = stripped[: match.start()].count("\n") + 1
        _emit_source_edge(raw_target, line, path, normalised, result, mod_uid)

    for match in _CALL_SCRIPT_RE.finditer(stripped):
        raw_target = match.group("path")
        line = stripped[: match.start()].count("\n") + 1
        _emit_call_edge(raw_target, line, path, normalised, result, mod_uid)

    for match in _FUNCTION_DEF_RE.finditer(stripped):
        name = match.group("name")
        line = stripped[: match.start()].count("\n") + 1
        _emit_function(name, line, path, normalised, result, mod_uid)

    for match in _COS_LOG_HOOK_RE.finditer(stripped):
        hook_name = match.group("name")
        line = stripped[: match.start()].count("\n") + 1
        _emit_log_hook_edge(hook_name, line, normalised, result, mod_uid)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def extract(path: str, content: str) -> ExtractionResult:
    """Parse a shell script → nodes + edges."""
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

    used_tree_sitter = False
    if _TS_AVAILABLE and _ts_overlay is not None:
        parsed = _ts_overlay.parse("bash", content)
        if parsed is not None:
            used_tree_sitter = True
            err_count = _walk_ts(
                parsed.root,
                content.encode("utf-8"),
                path,
                normalised,
                mod.uid,
                result,
            )
            if err_count:
                result.parse_errors.append(
                    ParseError(
                        kind="tree_sitter_error",
                        detail=f"tree-sitter recorded {err_count} ERROR node(s)",
                    )
                )

    if not used_tree_sitter:
        _walk_regex(content, path, normalised, mod.uid, result)

    emit_contains_spine(
        file_path=path,
        file_uid_=file_uid(path),
        result=result,
        extractor_id=EXTRACTOR_ID,
    )

    _promote_stubs(result)
    return result


__all__ = ["EXTRACTOR_ID", "extract", "file_uid", "module_uid"]
