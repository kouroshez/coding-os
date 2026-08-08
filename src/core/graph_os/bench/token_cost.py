"""Graph-envelope token cost vs naive file-read baseline (TASK-483).

Measures, per documented graph workflow, the tokens of the graph envelope
(``meta.tokens_estimated`` — a chars/4 heuristic, NOT a real tokenizer)
against the tokens an agent would spend reading the source files to answer
the same structural question by hand. Reuses the existing bench fixtures +
``run_benchmark``; adds no parallel corpus and no second token estimator.

The numbers are heuristic bands, not a contract: the estimator is chars/4
(ASCII) and the naive baseline is a deliberate "read everything the query
would otherwise force you to read" proxy. The only CI gate is gross
regression (graph envelope > 2x its naive baseline).

DEPENDS: graph_os.bench fixtures/harness, graph_os.tools.graph, _shared,
thinking_os.database.
"""

from __future__ import annotations

import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from ..backends.sqlite_backend import SqliteBackend
from . import build_mixed_corpus, build_python_corpus, run_benchmark

# Workflows named in the graph-first rule (.claude/rules/meta-graph-first.md)
# that this bench measures. Order is the report order.
WORKFLOWS = (
    "references",
    "rename_plan",
    "contracts",
    "communities+export",
    "detect_changes",
)


@dataclass
class TokenCostRow:
    workflow: str
    graph_tokens: int
    naive_tokens: int
    ratio: float  # naive / graph — naive tokens one graph token replaces
    savings_pct: float  # (1 - graph/naive) * 100

    def to_dict(self) -> dict:
        return asdict(self)


def _token_estimator():
    from ..tools.graph import _envelope_module

    return _envelope_module()._estimate_tokens


def _fresh_conn(db_path: str):
    try:
        import database  # type: ignore
    except ImportError:
        thinking = Path(__file__).resolve().parent.parent.parent / "thinking_os"
        if str(thinking) not in sys.path:
            sys.path.insert(0, str(thinking))
        import database  # type: ignore
    return database.init_db(db_path)


def _envelope_tokens(envelope: dict, estimate) -> int:
    if isinstance(envelope, dict):
        data = envelope.get("data")
        if isinstance(data, dict):
            meta = data.get("meta")
            if isinstance(meta, dict) and "tokens_estimated" in meta:
                return int(meta["tokens_estimated"])
    # Fail envelope or unexpected shape — fall back to estimating the
    # serialized response so the row is never silently zero.
    return max(1, estimate(json.dumps(envelope, default=str)))


def _highest_degree_function_uid(backend: SqliteBackend) -> str:
    best_uid, best_degree = "", -1
    for node in backend.sample_nodes("function", limit=50):
        degree = len(backend.list_edges(target_uid=node.uid, limit=200))
        if degree > best_degree:
            best_uid, best_degree = node.uid, degree
    return best_uid


def measure_token_cost(*, python_count: int = 40, mixed_size: int = 30) -> list[TokenCostRow]:
    """Build the standard bench corpora, index them, and return per-workflow
    graph-envelope tokens vs the naive read-everything baseline."""
    from ..tools import graph as graph_tools

    estimate = _token_estimator()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        py_files = build_python_corpus(root / "py", count=python_count)
        mixed_files = build_mixed_corpus(root / "mixed", size=mixed_size)
        all_files = py_files + mixed_files

        conn = _fresh_conn(str(root / "graph.db"))
        try:
            backend = SqliteBackend(conn=conn)
            run_benchmark(backend, all_files)
            backend.link_external_stubs()
            backend.link_import_bindings()

            # Naive baselines: tokens an agent spends reading source by hand.
            all_text = "\n".join(p.read_text(encoding="utf-8") for p in all_files)
            route_text = "\n".join(
                p.read_text(encoding="utf-8") for p in all_files if "route_" in p.name
            )
            all_tokens = max(1, estimate(all_text))
            route_tokens = max(1, estimate(route_text)) if route_text else all_tokens

            prev_singleton = graph_tools._BACKEND_SINGLETON
            graph_tools._BACKEND_SINGLETON = backend
            try:
                uid = _highest_degree_function_uid(backend)
                envelopes = {
                    "references": [graph_tools.cos_graph_references(uid)],
                    "rename_plan": [graph_tools.cos_graph_rename_plan(uid, "renamed_symbol")],
                    "contracts": [graph_tools.cos_graph_contracts()],
                    "communities+export": [
                        graph_tools.cos_graph_communities(),
                        graph_tools.cos_graph_export(),
                    ],
                    "detect_changes": [
                        graph_tools.cos_graph_detect_changes(files=[str(p) for p in all_files])
                    ],
                }
            finally:
                graph_tools._BACKEND_SINGLETON = prev_singleton
        finally:
            conn.close()

    naive_for = {
        "references": all_tokens,
        "rename_plan": all_tokens,
        "contracts": route_tokens,
        "communities+export": all_tokens,
        "detect_changes": all_tokens,
    }
    rows: list[TokenCostRow] = []
    for workflow in WORKFLOWS:
        graph_tokens = max(1, sum(_envelope_tokens(e, estimate) for e in envelopes[workflow]))
        naive_tokens = naive_for[workflow]
        rows.append(
            TokenCostRow(
                workflow=workflow,
                graph_tokens=graph_tokens,
                naive_tokens=naive_tokens,
                ratio=round(naive_tokens / graph_tokens, 2),
                savings_pct=round((1 - graph_tokens / naive_tokens) * 100, 1),
            )
        )
    return rows


def report_json(rows: list[TokenCostRow] | None = None) -> str:
    rows = rows if rows is not None else measure_token_cost()
    return json.dumps([r.to_dict() for r in rows], indent=2)


__all__ = ["WORKFLOWS", "TokenCostRow", "measure_token_cost", "report_json"]


if __name__ == "__main__":
    print(report_json())
