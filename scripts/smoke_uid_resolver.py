"""Smoke test for graph_os uid auto-resolution + helpful error envelopes.

DEPENDS:    core/graph_os/tools/graph.py, populated coding-os.db.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

from graph_os.tools import graph as g  # noqa: E402


FAILURES: list[str] = []


def _check(label: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label}{(': ' + detail) if detail else ''}")
    if not cond:
        FAILURES.append(label)


def _parse(envelope):
    if isinstance(envelope, str):
        return json.loads(envelope)
    return envelope


def _data(envelope) -> dict:
    return _parse(envelope).get("data") or {}


def _call(fn, *args, **kwargs):
    return _parse(fn(*args, **kwargs))


def main() -> int:
    g.reset_backend()

    # ------------------------------------------------------------------
    # Scenario 1: raw path → cos_graph_impact must auto-resolve.
    # Reproduces the exact failing call from the screenshot.
    # ------------------------------------------------------------------
    raw = "core/graph_os/tools/graph.py"
    res = _call(g.cos_graph_impact, raw)
    _check(
        "impact(raw path) → ok",
        res.get("ok") is True,
        f"err={res.get('error')}" if not res.get("ok") else "",
    )
    if res.get("ok"):
        root = _data(res).get("root", {})
        _check(
            "impact(raw path) resolved to code:file:",
            root.get("uid") == f"code:file:{raw}",
            f"got uid={root.get('uid')!r}",
        )

    # ------------------------------------------------------------------
    # Scenario 2: prefixed uid still works.
    # ------------------------------------------------------------------
    pref = f"code:file:{raw}"
    res2 = _call(g.cos_graph_impact, pref)
    _check("impact(prefixed) → ok", res2.get("ok") is True)
    _check(
        "impact(prefixed) root.uid matches",
        _data(res2).get("root", {}).get("uid") == pref,
    )

    # ------------------------------------------------------------------
    # Scenario 3: unknown path → helpful not_found with suggestions.
    # ------------------------------------------------------------------
    bogus = "no/such/file.py"
    res3 = _call(g.cos_graph_impact, bogus)
    err = res3.get("error") or {}
    _check("impact(bogus) is fail", res3.get("ok") is False)
    _check("impact(bogus) category=not_found", err.get("category") == "not_found")
    msg = err.get("message", "")
    _check(
        "impact(bogus) message lists fallbacks",
        "code:file:" in msg and "doc:file:" in msg and "folder:" in msg,
        msg[:160],
    )
    _check(
        "impact(bogus) message hints cos_graph_query",
        "cos_graph_query" in msg,
    )

    # ------------------------------------------------------------------
    # Scenario 4: cos_graph_references with raw path.
    # ------------------------------------------------------------------
    res4 = _call(g.cos_graph_references, raw)
    _check("references(raw path) → ok", res4.get("ok") is True)
    if res4.get("ok"):
        node_uid = _data(res4).get("node", {}).get("uid")
        _check(
            "references(raw path) resolved",
            node_uid == f"code:file:{raw}",
            f"got uid={node_uid!r}",
        )

    # ------------------------------------------------------------------
    # Scenario 5: cos_graph_context with raw path.
    # ------------------------------------------------------------------
    res5 = _call(g.cos_graph_context, raw)
    _check("context(raw path) → ok", res5.get("ok") is True)

    # ------------------------------------------------------------------
    # Scenario 6: cos_graph_similar with raw path.
    # ------------------------------------------------------------------
    res6 = _call(g.cos_graph_similar, raw, top_k=3)
    _check("similar(raw path) → ok", res6.get("ok") is True)

    # ------------------------------------------------------------------
    # Scenario 7: cos_graph_path with raw paths on both ends.
    # ------------------------------------------------------------------
    res7 = _call(g.cos_graph_path, raw, "core/hooks/registry.yaml", max_hops=3)
    _check("path(raw,raw) → ok envelope", res7.get("ok") is True)

    # ------------------------------------------------------------------
    # Scenario 8: cos_graph_path bogus source → labelled error.
    # ------------------------------------------------------------------
    res8 = _call(g.cos_graph_path, "does/not/exist.py", raw)
    err8 = res8.get("error") or {}
    _check("path(bogus source) is fail", res8.get("ok") is False)
    _check(
        "path(bogus source) message labels source_uid",
        "source_uid" in err8.get("message", ""),
        err8.get("message", "")[:120],
    )

    # ------------------------------------------------------------------
    # Scenario 9: trace from a known function uid.
    # ------------------------------------------------------------------
    func_uid = (
        "code:function:core/graph_os/tools/graph.py::_resolve_uid"
    )
    res9 = _call(g.cos_graph_trace, func_uid, max_steps=5)
    _check("trace(known function uid) → ok", res9.get("ok") is True)

    # ------------------------------------------------------------------
    # Scenario 10: rename_plan with raw path → auto-resolve, no edits.
    # ------------------------------------------------------------------
    res10 = _call(g.cos_graph_rename_plan, raw, new_name="renamed_graph")
    _check(
        "rename_plan(raw path) → ok",
        res10.get("ok") is True,
        f"err={res10.get('error')}" if not res10.get("ok") else "",
    )

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("\nALL SCENARIOS PASS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
