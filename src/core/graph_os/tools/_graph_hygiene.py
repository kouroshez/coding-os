"""Coverage hygiene: cos_graph_test_gap and cos_graph_dead_code.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import time as _time
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import (
    _clamp_int,
    _fail,
    _ok,
    _validate_positive_int,
)
from ._graph_walk import _BEHAVIOURAL_EDGE_TYPES

_DEAD_CODE_SKIP_LABELS = frozenset({"main", "register", "extract", "setup"})


def _is_test_file(fp: str) -> bool:
    return bool(fp) and (
        fp.startswith("tests/")
        or "/tests/" in fp
        or fp.startswith("test_")
        or "/test_" in fp
        or "_test." in fp
    )


def cos_graph_test_gap(
    *,
    kind: str = "",
    top: int = 50,
    backend: str | None = None,
) -> dict[str, Any]:
    """List prod function/method/class with zero inbound edge from any test (untested symbols)."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=500)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    sqlite_conn = getattr(be, "_conn", None)
    if sqlite_conn is None:
        return _ok(
            {"untested": [], "total_count": 0, "note": "test-gap scan requires the sqlite backend"},
            meta={"backend": be.backend_id, "layer": "graph"},
        )
    kinds: tuple[str, ...] = (
        "function",
        "method",
        "class",
        "code:function",
        "code:method",
        "code:class",
    )
    if kind:
        from ..types import normalize_kind as _normalize_kind_enum

        try:
            kn = _normalize_kind_enum(kind).value
        except Exception:
            return _fail("validation", f"unknown kind {kind!r}; use function|method|class")
        kinds = (kn, f"code:{kn}")

    ref_types = sorted(_BEHAVIOURAL_EDGE_TYPES)
    # Inbound edge counts ONLY when the source is a test file → symbols with
    # COUNT(s.id)=0 have no test exercising them (the inverse of dead_code).
    test_src = (
        "(s.file_path LIKE 'tests/%' OR s.file_path LIKE '%/tests/%' "
        "OR s.file_path LIKE 'test_%' OR s.file_path LIKE '%/test_%' "
        "OR s.file_path LIKE '%_test.%')"
    )
    edge_ph = ",".join("?" * len(ref_types))
    kind_ph = ",".join("?" * len(kinds))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, n.kind, n.label, n.file_path
            FROM graph_nodes n
            LEFT JOIN graph_edges_v12 e
              ON e.target_id = n.id AND e.edge_type IN ({edge_ph})
            LEFT JOIN graph_nodes s ON s.id = e.source_id AND {test_src}
            WHERE n.kind IN ({kind_ph})
              AND n.uid NOT LIKE 'code:external:%'
              AND n.file_path IS NOT NULL AND n.file_path != ''
            GROUP BY n.id
            HAVING COUNT(s.id) = 0
            """,
            (*ref_types, *kinds),
        ).fetchall()
    except Exception as exc:
        return _fail("internal", f"test-gap query failed: {exc}")

    untested: list[dict[str, Any]] = []
    for uid, nkind, label, fp in rows:
        lab = label or ""
        if _is_test_file(fp or ""):
            continue  # don't report test code itself as "untested"
        if lab.startswith("__") or lab in _DEAD_CODE_SKIP_LABELS:
            continue
        if (fp or "").endswith(".sh"):
            continue  # shell has no call-graph → cannot infer test coverage
        untested.append({"uid": uid, "kind": nkind, "label": lab, "file_path": fp})

    untested.sort(key=lambda d: (d["file_path"] or "", d["label"]))
    total = len(untested)
    return _ok(
        {
            "untested": untested[:top],
            "total_count": total,
            "note": (
                "candidates — symbols with no inbound edge from a test file. "
                "Indirect exercise (via CLI, fixtures, dynamic dispatch) may not "
                "show as an edge; shell excluded (no call-graph)."
            ),
        },
        meta={
            "backend": be.backend_id,
            "layer": "graph",
            "kind": kind or "function,method,class",
            "result_truncated": total > top,
        },
    )


def cos_graph_dead_code(
    *,
    kind: str = "",
    top: int = 50,
    include_tests: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """List in-repo symbols with zero non-test inbound references (dead-code candidates)."""
    err = _validate_positive_int(top, "top")
    if err:
        return err
    top, _ = _clamp_int(top, min_v=1, max_v=500)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    sqlite_conn = getattr(be, "_conn", None)
    if sqlite_conn is None:
        return _ok(
            {"dead": [], "total_count": 0, "note": "dead-code scan requires the sqlite backend"},
            meta={"backend": be.backend_id, "layer": "graph"},
        )

    kinds: tuple[str, ...] = (
        "function",
        "method",
        "class",
        "code:function",
        "code:method",
        "code:class",
    )
    if kind:
        from ..types import normalize_kind as _normalize_kind_enum

        try:
            kn = _normalize_kind_enum(kind).value
        except Exception:
            return _fail("validation", f"unknown kind {kind!r}; use function|method|class")
        kinds = (kn, f"code:{kn}")

    # "Referenced" = any inbound behavioural edge (calls/constructs/inherits/
    # implements/dispatches/handles_*/type-uses). handles_* means it is an
    # entry-point handler → not dead. Test-sourced edges are excluded so a
    # symbol used only by its own tests still surfaces as dead.
    ref_types = sorted(_BEHAVIOURAL_EDGE_TYPES)
    test_pred = (
        ""
        if include_tests
        else (
            " AND s.file_path IS NOT NULL"
            " AND s.file_path NOT LIKE 'tests/%' AND s.file_path NOT LIKE '%/tests/%'"
            " AND s.file_path NOT LIKE 'test_%' AND s.file_path NOT LIKE '%/test_%'"
            " AND s.file_path NOT LIKE '%_test.%'"
        )
    )
    edge_ph = ",".join("?" * len(ref_types))
    kind_ph = ",".join("?" * len(kinds))
    try:
        rows = sqlite_conn.execute(
            f"""
            SELECT n.uid, n.kind, n.label, n.file_path
            FROM graph_nodes n
            LEFT JOIN graph_edges_v12 e
              ON e.target_id = n.id AND e.edge_type IN ({edge_ph})
            LEFT JOIN graph_nodes s ON s.id = e.source_id{test_pred}
            WHERE n.kind IN ({kind_ph})
              AND n.uid NOT LIKE 'code:external:%'
              AND n.file_path IS NOT NULL AND n.file_path != ''
            GROUP BY n.id
            HAVING COUNT(s.id) = 0
            """,
            (*ref_types, *kinds),
        ).fetchall()
    except Exception as exc:
        return _fail("internal", f"dead-code query failed: {exc}")

    def _is_test_path(fp: str) -> bool:
        return bool(fp) and (
            fp.startswith("tests/")
            or "/tests/" in fp
            or fp.startswith("test_")
            or "/test_" in fp
            or "_test." in fp
        )

    dead: list[dict[str, Any]] = []
    for uid, nkind, label, fp in rows:
        lab = label or ""
        if lab.startswith("__") or lab in _DEAD_CODE_SKIP_LABELS:
            continue  # dunder + dynamic-dispatch entry points (register/extract/main/setup)
        # Shell has no intra-script call-graph (code_shell emits no `calls`
        # between bash functions), so every .sh function would look dead —
        # pure noise. Reachability needs a call-graph; skip languages w/o one.
        if (fp or "").endswith(".sh"):
            continue
        if not include_tests and _is_test_path(fp or ""):
            continue
        # Exception classes are caught / raised dynamically (`except FooError`,
        # `raise cls()`, registry lookup) — an AST "zero inbound edges" reading
        # is a false positive. PEP8 names them *Error/*Exception/*Warning; skip
        # rather than nag a delete that would break the handlers that catch them.
        if nkind in ("class", "code:class") and lab.endswith(("Error", "Exception", "Warning")):
            continue
        dead.append({"uid": uid, "kind": nkind, "label": lab, "file_path": fp})

    dead.sort(key=lambda d: (d["file_path"] or "", d["label"]))
    total = len(dead)
    return _ok(
        {
            "dead": dead[:top],
            "total_count": total,
            "note": (
                "candidates only — symbols reachable solely via dynamic dispatch, "
                "CLI/plugin registration, or external callers may appear here; "
                "verify with cos_graph_references before deleting"
            ),
        },
        meta={
            "backend": be.backend_id,
            "layer": "graph",
            "kind": kind or "function,method,class",
            "include_tests": include_tests,
            "result_truncated": total > top,
        },
    )


def _git_files_since(root, epoch: int) -> tuple[set[str], str | None]:
    # Returns (paths, error). An error means "cannot answer" — the caller must
    # say so rather than return an empty list, because an empty list is the
    # shape of "nothing is stale" and would read as reassurance.
    import subprocess

    try:
        out = subprocess.run(
            ["git", "log", f"--since=@{epoch}", "--name-only", "--format=", "--", "."],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return set(), f"git unavailable: {exc}"
    if out.returncode != 0:
        return set(), (out.stderr or "git log failed").strip()[:200]
    return {line for line in out.stdout.splitlines() if line.strip()}, None


def cos_graph_stale_files(
    *,
    top: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """List indexed files with a git commit newer than the index pass that read them."""
    # Truncation has a flag because the harness knows it truncated. Staleness
    # has none: the graph is complete against its own model while the model is
    # behind the tree, so every envelope looks clean. Comparing indexed files
    # against files committed after the last index pass turns "possibly stale"
    # into a list, without a second analyzer that would share the extractor's
    # blind spots.
    top, _ = _clamp_int(top, min_v=1, max_v=5000)
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    # Same access path cos_graph_doctor uses for raw tables the typed backend
    # surface does not expose.
    conn = getattr(be, "_conn", None)
    if conn is None:
        return _fail("unavailable", "backend exposes no sqlite connection", retryable=True)
    try:
        rows = conn.execute(
            "SELECT file_path, last_indexed_at FROM file_index_state "
            "WHERE last_indexed_at IS NOT NULL"
        ).fetchall()
    except Exception as exc:
        return _fail("unavailable", f"file_index_state unreadable: {exc}", retryable=True)

    if not rows:
        return _ok(
            {"stale": [], "stale_count": 0, "indexed_files": 0, "index_age_seconds": None},
            meta={"source": "graph_os.stale_files", "reason": "nothing indexed yet"},
        )

    indexed = {str(r[0]): int(r[1]) for r in rows}
    newest = max(indexed.values())
    root = _kernel._repo_root_for_paths()
    committed, git_error = _git_files_since(root, min(indexed.values()))

    if git_error is not None:
        # No history to compare against is not "nothing is stale".
        return _fail("unavailable", f"cannot answer: {git_error}", retryable=False)

    stale = sorted(path for path in committed if path in indexed)
    now = int(_time.time())
    return _ok(
        {
            "stale": stale[:top],
            "stale_count": len(stale),
            "indexed_files": len(indexed),
            "index_age_seconds": now - newest,
            "newest_index_at": newest,
        },
        meta={
            "source": "graph_os.stale_files",
            "result_truncated": len(stale) > top,
            "total_count": len(stale),
        },
    )
