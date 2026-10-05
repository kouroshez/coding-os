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

import dataclasses
import hashlib
import logging
import re
import subprocess
from pathlib import Path, PurePosixPath

from ..toolchain import get_active
from ..types import EvidenceSignal, GraphEdge, GraphNode
from ._code_shell_emit import (
    EXTRACTOR_ID as EXTRACTOR_ID,
    _emit_call_edge,
    _emit_function,
    _emit_log_hook_edge,
    _emit_source_edge,
    _resolve_script_target as _resolve_script_target,
    file_uid as file_uid,
    module_uid as module_uid,
)
from ._shell_commands import ShellFile, collect_directives, handle_command
from ._shell_paths import ShellScope
from .md_links import (
    ExtractionResult,
    ParseError,
    _normalize_path,
    _promote_stubs,
    emit_contains_spine,
)

logger = logging.getLogger("graph_os.extractors.code_shell")

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


# ---------------------------------------------------------------------------
# Tree-sitter walker
# ---------------------------------------------------------------------------


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

    def text_of(node) -> str:
        return _ts_overlay.node_text(node, content_bytes)

    nodes = _all_nodes(root)
    shims = {id(node) for node in nodes if _is_fallback_shim(node, text_of)}
    scope = ShellScope()
    loops: dict[tuple[int, int], tuple[str, list[str]]] = {}
    local_functions: dict[str, str] = {}
    for node in sorted(nodes, key=lambda candidate: candidate.start_byte):
        if node.type == "variable_assignment":
            name_node, value_node = (
                node.child_by_field_name("name"),
                node.child_by_field_name("value"),
            )
            if name_node is not None and value_node is not None:
                scope.assign(text_of(name_node), text_of(value_node))
        elif node.type == "for_statement":
            loop = _literal_loop(node, text_of)
            if loop is not None:
                loops[(node.start_byte, node.end_byte)] = loop
        elif node.type == "function_definition" and id(node) not in shims:
            name = _function_name(node, text_of)
            if name:
                local_functions[name] = f"code:function:{_normalize_path(path)}::{name}"
    shell_file = ShellFile(
        path=normalised,
        module_uid=mod_uid,
        root=_active_root(),
        scope=scope,
        local_functions=local_functions,
        loops=loops,
        directives=collect_directives(root, text_of),
        result=result,
    )
    err_count = 0
    for node in nodes:
        if node.type == "ERROR":
            err_count += 1
        elif node.type == "function_definition":
            name = _function_name(node, text_of)
            if name:
                _emit_function(
                    name,
                    node.start_point[0] + 1,
                    path,
                    normalised,
                    result,
                    mod_uid,
                    end_line=node.end_point[0] + 1,
                    fallback_shim=id(node) in shims,
                )
        elif node.type == "command":
            caller = _enclosing_function_uid(node, content_bytes, path) or mod_uid
            handle_command(node, text_of, caller, shell_file)
    return err_count


def _all_nodes(root) -> list:
    nodes, stack = [], [root]
    while stack:
        node = stack.pop()
        nodes.append(node)
        stack.extend(reversed(list(node.children)))
    return nodes


def _function_name(node, text_of) -> str:
    for child in node.children:
        if child.type in ("word", "concatenation"):
            return text_of(child).strip()
    return ""


def _literal_loop(node, text_of) -> tuple[str, list[str]] | None:
    variable = node.child_by_field_name("variable")
    words = node.children_by_field_name("value")
    if variable is None or not words or any(word.type != "word" for word in words):
        return None
    return text_of(variable), [text_of(word) for word in words]


def _is_fallback_shim(node, text_of) -> bool:
    # `if ! command -v log_it >/dev/null; then log_it() { :; }; fi` defines a
    # no-op only when the real function was not sourced; counting it as the
    # definition hid the real one (86 such shims for one helper).
    if node.type != "function_definition":
        return False
    name = _function_name(node, text_of)
    current, hops = node.parent, 0
    while current is not None and hops < SHIM_SEARCH_DEPTH:
        if current.type in ("if_statement", "list") and _probes_for(text_of(current), name):
            return True
        current, hops = current.parent, hops + 1
    return False


def _probes_for(text: str, name: str) -> bool:
    probe = re.escape(name)
    return bool(re.search(rf"(?:command\s+-v|declare\s+-F|type(?:\s+-t)?)\s+{probe}\b", text))


def _active_root() -> Path | None:
    context = get_active()
    return Path(context.repo_root) if context is not None and context.repo_root else None


SHIM_SEARCH_DEPTH = 4


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

    local_funcs: dict[str, str] = {}
    for match in _FUNCTION_DEF_RE.finditer(stripped):
        name = match.group("name")
        line = stripped[: match.start()].count("\n") + 1
        _emit_function(name, line, path, normalised, result, mod_uid)
        local_funcs[name] = f"code:function:{_normalize_path(path)}::{name}"

    # Intra-file function calls (parity with the tree-sitter `_walk_ts`
    # path). A line whose first token is a same-file function name — and
    # is not the `name() {` definition line — is a real call. Gating on
    # `local_funcs` membership avoids keyword false-positives. Sourced at
    # the module (the regex path has no scope tree to find the caller fn).
    if local_funcs:
        seen_local_calls: set[str] = set()
        for m in re.finditer(r"(?m)^[ \t]*(?P<cmd>[A-Za-z_][\w-]*)\b", stripped):
            cmd = m.group("cmd")
            tgt = local_funcs.get(cmd)
            if tgt is None or cmd in seen_local_calls:
                continue
            if stripped[m.end() :].lstrip()[:2] == "()":
                continue  # the definition line, not a call
            line = stripped[: m.start()].count("\n") + 1
            seen_local_calls.add(cmd)
            result.edges.append(
                GraphEdge(
                    source_uid=mod_uid,
                    target_uid=tgt,
                    edge_type="calls",
                    extractor=EXTRACTOR_ID,
                    confidence=0.85,
                    source_span=f"{normalised}:{line}",
                    evidence=(EvidenceSignal("shell_local_call_regex", 0.85),),
                )
            )

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
                if _bash_syntax_ok(content):
                    # Valid bash that tree-sitter's grammar cannot parse
                    # ($((10#…)), ${V:+ (…$V…)}, concatenated quoted+glob
                    # case patterns) — a grammar gap, not a file error
                    # (roadmap §6): symbols near the gap may be missing,
                    # but parse_errors_count must reflect FILE errors only.
                    # GraphNode is frozen — swap in a patched module node.
                    patched = dataclasses.replace(
                        mod,
                        metadata={**mod.metadata, "grammar_gaps": err_count},
                    )
                    result.nodes[result.nodes.index(mod)] = patched
                else:
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


def _bash_syntax_ok(content: str) -> bool:
    # Read-only syntax probe (bash -n on stdin) — runs only when
    # tree-sitter reported ERROR nodes, so the subprocess cost is rare.
    # Fail-closed: no bash / timeout → treat the ERROR as a real parse
    # error rather than silently suppressing coverage gaps.
    try:
        probe = subprocess.run(
            ["bash", "-n"],
            input=content.encode("utf-8", errors="replace"),
            capture_output=True,
            timeout=5,
        )
        return probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


__all__ = ["EXTRACTOR_ID", "extract", "file_uid", "module_uid"]
