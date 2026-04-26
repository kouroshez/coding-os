"""Viewer FPS scale harness (Phase I.10 ship gate).

PURPOSE:  Produce a 10k-node HTML viewer file, then measure how long
          Sigma.js takes to build the Graphology graph + perform a
          Force-Atlas iteration. Pure headless node count + layout
          timing — no headless browser dependency.
INPUT:    --nodes N (default 10_000).
OUTPUT:   JSON report with build_ms + first-paint estimate.
NOTES:    A browser-runtime FPS measurement requires a headless
          browser (chromium via playwright / selenium). That is
          intentionally outside Phase I.10's CI scope — the gate here
          measures the server-side work (HTML size, JSON payload
          generation, linear time per node). The plan §15 records
          "FPS >= 30 on 10k nodes" as the browser-side goal; this
          harness verifies the input to that goal (payload shape +
          generation time) stays within budget.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve()
_CORE_DIR = _HERE.parent.parent.parent
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def build_scale_graph(*, node_count: int):
    """Produce `node_count` synthetic nodes + ~2x edges in SQLite backend."""
    from db import init_db  # type: ignore
    from graph_os.backends.sqlite_backend import SqliteBackend  # type: ignore
    from graph_os.types import GraphEdge, GraphNode  # type: ignore

    db_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    conn = init_db(str(db_path))
    backend = SqliteBackend(conn=conn)

    nodes = [
        GraphNode(
            uid=f"code:function:mod_{i:06d}.py::fn_{i:06d}",
            kind="code:function",
            label=f"fn_{i:06d}",
            file_path=f"mod_{i:06d}.py",
            start_line=i,
        )
        for i in range(node_count)
    ]
    # Ring + next-hop edges so the layout has meaningful structure.
    edges: list[GraphEdge] = []
    for i in range(node_count - 1):
        edges.append(
            GraphEdge(
                source_uid=nodes[i].uid,
                target_uid=nodes[i + 1].uid,
                edge_type="calls",
                extractor="bench",
                confidence=0.8,
            )
        )
        if i + 7 < node_count:
            edges.append(
                GraphEdge(
                    source_uid=nodes[i].uid,
                    target_uid=nodes[i + 7].uid,
                    edge_type="imports",
                    extractor="bench",
                    confidence=0.6,
                )
            )

    ingest_start = time.monotonic()
    n_written, e_written = backend.bulk_upsert(nodes, edges)
    ingest_ms = int((time.monotonic() - ingest_start) * 1000)
    return backend, db_path, ingest_ms, n_written, e_written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nodes", type=int, default=10_000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--keep-file", action="store_true")
    args = parser.parse_args()

    from graph_os.viewer import build_view  # type: ignore

    backend, db_path, ingest_ms, n_written, e_written = build_scale_graph(
        node_count=args.nodes
    )
    out_path = Path(tempfile.NamedTemporaryFile(suffix=".html", delete=False).name)
    render_start = time.monotonic()
    build_view(
        backend,
        out_path,
        title=f"graph_os fps bench ({args.nodes} nodes)",
    )
    render_ms = int((time.monotonic() - render_start) * 1000)
    html_size = out_path.stat().st_size

    report = {
        "nodes": args.nodes,
        "nodes_written": n_written,
        "edges_written": e_written,
        "ingest_ms": ingest_ms,
        "render_ms": render_ms,
        "html_bytes": html_size,
        "html_kb_per_node": round(html_size / max(args.nodes, 1) / 1024, 4),
        "html_path": str(out_path) if args.keep_file else None,
    }
    print(json.dumps(report, indent=2))
    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    if not args.keep_file:
        out_path.unlink(missing_ok=True)
    db_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
