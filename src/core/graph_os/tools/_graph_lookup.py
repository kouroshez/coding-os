"""String-to-node lookup: uid grammar, FTS5 sanitising, and lexical ranking.

Leaf of graph_os.tools.graph — depends on the envelope and walk leaves.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence
from typing import Any

from ..backend import GraphBackend
from ..types import GraphNode
from ._graph_envelope import _fail, logger
from ._graph_walk import _degree_map_for

# ---------------------------------------------------------------------------
# UID resolution
# ---------------------------------------------------------------------------
#
# Tools accept fully-qualified node uids ("code:file:foo.py",
# "code:function:foo.py::bar", "doc:file:README.md", "folder:src/utils").
# Agents (and humans) often pass a raw repo path because that is the most
# natural mental model. _resolve_uid bridges the gap by transparently
# retrying a small set of well-known prefixes when the literal lookup
# misses, and _fail_uid_not_found returns the candidates tried plus a
# scheme cheat-sheet so failures are self-explanatory.

_UID_PATH_PREFIXES: tuple[str, ...] = (
    "code:file:",
    "doc:file:",
    "folder:",
)

_UID_FORMAT_HINT = (
    "uids follow the scheme code:file:<path> | "
    "code:function:<path>::<name> | code:class:<path>::<name> | "
    "code:module:<dotted> | doc:file:<path> | "
    "doc:heading:<path>#<slug>:<level> | folder:<path>. "
    "Use cos_graph_query to discover candidates."
)


# G8/G9/G39: kind-weighting for resolve / context / query — real
# symbols rank above imports + external stubs at the same FTS5 score.
_KIND_RESOLVE_WEIGHT: dict[str, int] = {
    "class": 1,
    "code:class": 1,
    "function": 2,
    "code:function": 2,
    "method": 3,
    "code:method": 3,
    "interface": 4,
    "code:interface": 4,
    "variable": 5,
    "code:variable": 5,
    "mcp_tool": 6,
    "hook": 6,
    "tool": 6,
    "route": 6,
    "module": 10,
    "code:module": 10,
    "file": 11,
    "code:file": 11,
    "doc:file": 12,
    "doc:heading": 13,
    "import_": 20,
    "code:import": 20,
    "identifier": 30,  # `code:external:unresolved:*` lives here
}


def _KIND_RESOLVE_RANK(node: GraphNode) -> tuple[int, int]:
    """Lower tuple == better. Tie-break by uid length (shorter is canonical)."""
    weight = _KIND_RESOLVE_WEIGHT.get(node.kind or "", 25)
    if (node.uid or "").startswith("code:external:"):
        weight += 5
    return (weight, len(node.uid or ""))


def _normalize_kinds(kinds: Any) -> tuple[str, ...]:
    # G3: FastMCP wire can deliver Sequence[str] as stringified JSON.
    # Accept list/CSV/JSON-array-string/single-stringified-list.
    if kinds is None:
        return ()
    if isinstance(kinds, str):
        s = kinds.strip()
        if not s:
            return ()
        if s.startswith("[") and s.endswith("]"):
            try:
                import json as _json

                parsed = _json.loads(s)
                if isinstance(parsed, list):
                    return tuple(str(x).strip() for x in parsed if str(x).strip())
            except (_json.JSONDecodeError, TypeError, ValueError):
                pass  # not JSON → fall through to the CSV split below (intentional)
        return tuple(p.strip() for p in s.split(",") if p.strip())
    if isinstance(kinds, (list, tuple)):
        if len(kinds) == 1 and isinstance(kinds[0], str) and kinds[0].lstrip().startswith("["):
            return _normalize_kinds(kinds[0])
        return tuple(str(k).strip() for k in kinds if str(k).strip())
    return ()


def _looks_prefixed(raw: str) -> bool:
    """True when input already carries an explicit uid scheme."""
    head = raw.split("/", 1)[0]
    return ":" in head


def _resolve_uid(backend: GraphBackend, raw_uid: str) -> tuple[GraphNode | None, list[str], str]:
    """Look up a node uid, with path-prefix fallback for raw paths.

    Returns ``(node, tried, source)`` where ``tried`` is the ordered list
    of candidates attempted and ``source`` is one of ``direct`` |
    ``path_prefix`` | ``fuzzy_fts5`` | ``not_found``.

    R4-01: bare identifiers used to silently fall through to FTS5 fuzzy
    and return a plausible-but-wrong symbol. After fix, FTS5 fallback
    fires only for identifier-shaped inputs (``_looks_like_label``) and
    callers surface ``meta.resolved_from="fuzzy_fts5"`` so the agent can
    tell the answer came from a fuzzy match instead of an explicit lookup.
    """
    direct = backend.get_node(raw_uid)
    if direct is not None:
        return direct, [raw_uid], "direct"

    if _looks_prefixed(raw_uid):
        return None, [raw_uid], "not_found"

    tried: list[str] = [raw_uid]
    for prefix in _UID_PATH_PREFIXES:
        candidate = f"{prefix}{raw_uid}"
        tried.append(candidate)
        node = backend.get_node(candidate)
        if node is not None:
            return node, tried, "path_prefix"

    if _looks_like_label(raw_uid):
        fts_node = _fts5_label_lookup(backend, raw_uid)
        if fts_node is not None:
            tried.append(f"fts5:{raw_uid}")
            return fts_node, tried, "fuzzy_fts5"
    return None, tried, "not_found"


def _looks_like_label(raw: str) -> bool:
    if len(raw) < 3:
        return False
    if not any(c.isalpha() for c in raw):
        return False
    return all(c.isalnum() or c in "_." for c in raw)


def _fts5_label_lookup(backend: GraphBackend, raw_label: str) -> GraphNode | None:
    """Pick the top-ranked FTS5 hit whose label matches `raw_label`."""
    sqlite_conn = getattr(backend, "_conn", None)
    if sqlite_conn is None:
        return None
    row_to_node = getattr(backend, "_row_to_node", None)
    if row_to_node is None:
        return None
    fts_q = _fts5_safe_query(raw_label)
    if not fts_q:
        return None
    try:
        rows = sqlite_conn.execute(
            """
            SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                   n.end_line, n.signature, n.lang, n.doc_blob,
                   n.ast_hash, n.content_hash, n.metadata_json
            FROM graph_nodes_fts
            JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
            WHERE graph_nodes_fts MATCH ?
            ORDER BY rank
            LIMIT 20
            """,
            (fts_q,),
        ).fetchall()
    except Exception as exc:
        logger.debug("fts5 resolve fallback suppressed: %s", exc)
        return None
    # Prefer an exact label match if FTS5 surfaces one; otherwise take
    # the top-ranked hit so a near-match still resolves.
    # G9: rank candidates by kind weight (real symbol > doc heading >
    # import > external) — F11 fallback used to return whatever FTS5
    # ranked first, including doc:heading when caller wanted code:function.
    nodes = [row_to_node(r) for r in rows]
    nodes = [n for n in nodes if n is not None]
    for n in nodes:
        if (n.label or "") == raw_label and not (n.uid or "").startswith("code:external:"):
            return n
    if nodes:
        return sorted(nodes, key=_KIND_RESOLVE_RANK)[0]
    return None


def _fail_uid_not_found(
    raw_uid: str,
    tried: list[str],
    *,
    label: str = "uid",
) -> dict[str, Any]:
    """Helpful 'not_found' envelope including the candidates tried."""
    if len(tried) > 1:
        suggestions = ", ".join(repr(c) for c in tried[1:])
        msg = f"no node with {label} {raw_uid!r} (also tried {suggestions}). {_UID_FORMAT_HINT}"
    else:
        msg = f"no node with {label} {raw_uid!r}. {_UID_FORMAT_HINT}"
    return _fail("not_found", msg)


def _lexical_search(
    backend: GraphBackend,
    *,
    q: str,
    kinds: Sequence[str] | None,
    limit: int,
    max_hops: int,
) -> list[GraphNode]:
    """Multi-signal lexical search with centrality tie-breaker."""
    lower = q.lower()
    sqlite_conn = getattr(backend, "_conn", None)
    candidates: list[GraphNode] = []
    if sqlite_conn is not None:
        rows: list[Any] = []
        try:
            if not lower and kinds:
                # kinds-only browse — no text filter needed
                placeholders = ",".join(["?"] * len(kinds))
                rows = sqlite_conn.execute(
                    f"SELECT kind, label, uid, file_path, start_line, end_line,"
                    f"       signature, lang, doc_blob, ast_hash, content_hash,"
                    f"       metadata_json"
                    f" FROM graph_nodes WHERE kind IN ({placeholders}) LIMIT ?",
                    (*list(kinds), int(limit) * 6),
                ).fetchall()
            else:
                # F13: try the maintained FTS5 index first (indexed MATCH,
                # scales to 500k); fall back to the leading-wildcard LIKE
                # scan only when FTS5 yields nothing so recall is preserved.
                fts_q = _fts5_safe_query(lower)
                if fts_q:
                    try:
                        fts_kinds_clause = ""
                        fts_params: list[Any] = [fts_q]
                        if kinds:
                            ph = ",".join(["?"] * len(kinds))
                            fts_kinds_clause = f" AND n.kind IN ({ph})"
                            fts_params.extend(list(kinds))
                        fts_params.append(int(limit) * 6)
                        rows = sqlite_conn.execute(
                            f"""
                            SELECT n.kind, n.label, n.uid, n.file_path, n.start_line,
                                   n.end_line, n.signature, n.lang, n.doc_blob,
                                   n.ast_hash, n.content_hash, n.metadata_json
                            FROM graph_nodes_fts
                            JOIN graph_nodes n ON n.id = graph_nodes_fts.rowid
                            WHERE graph_nodes_fts MATCH ?{fts_kinds_clause}
                            LIMIT ?
                            """,
                            tuple(fts_params),
                        ).fetchall()
                    except Exception as exc:
                        logger.debug("fts5 lexical search suppressed: %s", exc)
                        rows = []
                if not rows:
                    like_q = f"%{lower}%"
                    kinds_clause = ""
                    params: list[Any] = [like_q, like_q, like_q]
                    if kinds:
                        placeholders = ",".join(["?"] * len(kinds))
                        kinds_clause = f" AND kind IN ({placeholders})"
                        params.extend(list(kinds))
                    params.append(int(limit) * 6)
                    rows = sqlite_conn.execute(
                        f"""
                        SELECT kind, label, uid, file_path, start_line, end_line,
                               signature, lang, doc_blob, ast_hash, content_hash,
                               metadata_json
                        FROM graph_nodes
                        WHERE (LOWER(label) LIKE ?
                               OR LOWER(COALESCE(signature, '')) LIKE ?
                               OR LOWER(COALESCE(doc_blob, '')) LIKE ?)
                        {kinds_clause}
                        LIMIT ?
                        """,
                        tuple(params),
                    ).fetchall()
        except Exception as exc:
            logger.debug("lexical sql search suppressed: %s", exc)
        row_to_node = getattr(backend, "_row_to_node", None)
        for row in rows:
            if row_to_node is not None:
                candidates.append(row_to_node(row))
            else:
                n = backend.get_node(row[2])
                if n is not None:
                    candidates.append(n)

    if not candidates:
        seen: dict[str, GraphNode] = {}
        for edge in backend.list_edges(limit=1000):
            for side in (edge.source_uid, edge.target_uid):
                if side in seen:
                    continue
                node = backend.get_node(side)
                if node is None:
                    continue
                if kinds and node.kind not in kinds:
                    continue
                haystack = " ".join(
                    filter(
                        None,
                        [node.uid, node.label, node.signature, node.doc_blob],
                    )
                ).lower()
                if lower in haystack:
                    seen[side] = node
                if len(seen) >= limit * 3:
                    break
        candidates = list(seen.values())

    degree_map = _degree_map_for(backend, [n.uid for n in candidates])
    from math import log2

    def score(n: GraphNode) -> float:
        label = (n.label or "").lower()
        sig = (n.signature or "").lower()
        doc = (n.doc_blob or "").lower()
        if label == lower:
            base = 1.0
        elif label.startswith(lower):
            base = 0.85
        elif lower in label:
            base = 0.70
        elif lower in sig:
            base = 0.45
        elif lower in doc:
            base = 0.30
        else:
            base = difflib.SequenceMatcher(None, lower, label).ratio() * 0.5
        boost = log2((degree_map.get(n.uid) or 0) + 1) * 0.05
        # G39: penalise external stubs + identifier noise so they don't
        # outrank a real symbol at the same label match.
        kind_penalty = 0.0
        if (n.uid or "").startswith("code:external:"):
            kind_penalty = 0.5
        elif n.kind == "identifier":
            kind_penalty = 0.4
        elif (n.kind or "") in ("import_", "code:import"):
            kind_penalty = 0.2
        return base + min(boost, 0.4) - kind_penalty

    return sorted(candidates, key=score, reverse=True)[:limit]


# Arabic/Persian harakat — combining vowel + gemination marks (U+064B–U+0652)
# plus the superscript alef (U+0670). The unicode61 `remove_diacritics 2`
# tokenizer folds Latin combining marks but NOT these, so a harakat-bearing
# query would miss a harakat-free indexed form. Strip them from the query so
# the common case (harakat-typed query vs harakat-free index) matches. Full
# symmetric folding of harakat-bearing INDEXED text needs an FTS-rebuild
# migration and is deferred until Persian/Arabic is a named market.
_HARAKAT_STRIP = dict.fromkeys((*range(1611, 1619), 1648))


def _fold_harakat(raw: str) -> str:
    """Drop Arabic/Persian harakat so a vowel-marked query folds to its base."""
    return raw.translate(_HARAKAT_STRIP)


def _fts5_safe_query(raw: str) -> str:
    """Sanitise a free-text query for FTS5.

    FTS5 reserves `"`, `*`, `(`, `)`, `:`. We strip them rather than
    quote-escape because most agent queries are noun phrases — splitting
    into tokens with implicit AND is the highest-recall behaviour.
    Arabic/Persian harakat are folded first (see _fold_harakat).
    Returns empty string on degenerate input so the caller skips FTS.
    """
    raw = _fold_harakat(raw)
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch in "._-":
            cleaned.append(ch)
        else:
            cleaned.append(" ")
    tokens = [t for t in "".join(cleaned).split() if len(t) >= 2]
    if not tokens:
        return ""
    # Quote each token to handle digits + dotted names; join with space
    # so FTS5 applies an implicit AND.
    return " ".join(f'"{t}"' for t in tokens[:8])
