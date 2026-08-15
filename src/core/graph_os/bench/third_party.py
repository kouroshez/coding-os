"""Token-cost benchmark against a real third-party repo.

Methodology SSOT: docs/engineering/third-party-token-bench.md — graph envelope
tokens vs what a graph-less agent pays for the same question, measured on the
target repo's own .py corpus with the production extractors, backend, and token
estimator.

Two rules keep the number honest, both of which the first version of this harness
broke: the baseline defaults to what a competent agent actually does rather than
reading every matching file, and an envelope whose coverage walk was truncated is
never scored as a saving.

DEPENDS: graph_os.bench.harness, graph_os.bench.token_cost,
         graph_os.bench._baselines, graph_os.bench._coverage,
         graph_os.backends.sqlite_backend, git (only for URL targets).
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
_CORE_DIR = _HERE.parent.parent.parent
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from graph_os.backends.sqlite_backend import SqliteBackend  # noqa: E402
from graph_os.bench._baselines import (  # noqa: E402
    Baseline,
    Corpus,
    baseline_characters,
    baseline_note,
)
from graph_os.bench._coverage import INCOMPLETE, Envelope, resolve_complete  # noqa: E402
from graph_os.bench.harness import run_benchmark  # noqa: E402
from graph_os.bench.token_cost import _fresh_conn  # noqa: E402

WORKFLOWS = ("references", "impact", "rename_plan")

_SKIP_DIR_NAMES = frozenset(
    {".git", ".hg", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"}
)
_MAX_FILE_BYTES = 2 * 1024 * 1024
_CLONE_TIMEOUT_SECONDS = 300
_PROBE_SAMPLE_LIMIT = 400
_PROBE_EDGE_SCAN_LIMIT = 500

# Median always-on cost of a real consumer profile, measured by
# src/scripts/context_budget.py across all 21 presets (range 12,704-13,972).
DEFAULT_CONTEXT_BUDGET_TOKENS = 13_158


@dataclass
class ProbeRow:
    uid: str
    label: str
    workflow: str
    graph_tokens: int
    baseline_tokens: int
    savings_pct: float
    answer_shape: str
    total_count: int | None
    rows_shown: int
    budget_used: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clone(url: str, ref: str | None, dest: Path) -> Path:
    cmd = ["git", "clone", "--depth", "1"]
    if ref:
        cmd += ["--branch", ref]
    cmd += [url, str(dest)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=_CLONE_TIMEOUT_SECONDS)
    return dest


def _collect_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def _top_degree_symbols(backend: SqliteBackend, count: int) -> list[Any]:
    """Highest-degree symbols, one per label.

    Two nodes can share a label across files; their baselines are then identical
    (the baseline greps the name), so keeping both would double-weight one symbol
    in the median.
    """
    scored = []
    for kind in ("function", "class"):
        for node in backend.sample_nodes(kind, limit=_PROBE_SAMPLE_LIMIT):
            degree = len(backend.list_edges(target_uid=node.uid, limit=_PROBE_EDGE_SCAN_LIMIT))
            scored.append((degree, node))
    scored.sort(key=lambda pair: (-pair[0], pair[1].uid))

    seen: set[str] = set()
    probes = []
    for _, node in scored:
        if node.label in seen:
            continue
        seen.add(node.label)
        probes.append(node)
        if len(probes) == count:
            break
    return probes


def _envelopes_for(graph_tools: Any, uid: str, label: str) -> dict[str, Envelope]:
    """One coverage-settled envelope per workflow, widening budgets where the tool
    exposes one. `rename_plan` is exhaustive by construction and takes no budget."""
    return {
        "references": resolve_complete(
            lambda budget: graph_tools.cos_graph_references(uid, limit=budget)
        ),
        "impact": resolve_complete(
            lambda budget: graph_tools.cos_graph_impact(uid, depth=3, visit_limit=budget)
        ),
        "rename_plan": resolve_complete(
            lambda _budget: graph_tools.cos_graph_rename_plan(uid, label + "_renamed"),
            widens=False,
        ),
    }


def _probe_rows(
    graph_tools: Any, probes: list[Any], corpus: Corpus, baseline: Baseline
) -> list[ProbeRow]:
    rows: list[ProbeRow] = []
    for node in probes:
        baseline_tokens = max(1, baseline_characters(corpus, node.label, baseline) // 4)
        envelopes = _envelopes_for(graph_tools, node.uid, node.label)
        for workflow in WORKFLOWS:
            envelope = envelopes[workflow]
            rows.append(
                ProbeRow(
                    uid=node.uid,
                    label=node.label,
                    workflow=workflow,
                    graph_tokens=envelope.tokens,
                    baseline_tokens=baseline_tokens,
                    savings_pct=round((1 - envelope.tokens / baseline_tokens) * 100, 1),
                    answer_shape=envelope.answer_shape,
                    total_count=envelope.total_count,
                    rows_shown=envelope.rows_shown,
                    budget_used=envelope.budget_used,
                )
            )
    return rows


def _summarize(rows: list[ProbeRow], context_budget_tokens: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for workflow in WORKFLOWS:
        in_workflow = [r for r in rows if r.workflow == workflow]
        scored = [r for r in in_workflow if r.answer_shape != INCOMPLETE]
        skipped = len(in_workflow) - len(scored)
        if not scored:
            summary[workflow] = {"probes": 0, "skipped_incomplete": skipped}
            continue
        savings = [r.savings_pct for r in scored]
        per_query_saving = statistics.median(r.baseline_tokens - r.graph_tokens for r in scored)
        summary[workflow] = {
            "median_savings_pct": round(statistics.median(savings), 1),
            "mean_savings_pct": round(statistics.fmean(savings), 1),
            "min_savings_pct": min(savings),
            "probes": len(scored),
            "skipped_incomplete": skipped,
            "median_tokens_saved_per_query": round(per_query_saving),
            "break_even_queries": (
                math.ceil(context_budget_tokens / per_query_saving)
                if per_query_saving > 0
                else None
            ),
        }
    return summary


def measure_repo(
    repo_root: Path,
    *,
    queries: int,
    repo_label: str,
    ref: str | None,
    baseline: Baseline,
    context_budget_tokens: int,
) -> dict[str, Any]:
    from graph_os.tools import graph as graph_tools

    files = _collect_python_files(repo_root)
    if not files:
        raise SystemExit(f"[FAIL] no .py files found under {repo_root}")
    corpus = Corpus.load(files)

    with tempfile.TemporaryDirectory() as tmp:
        conn = _fresh_conn(str(Path(tmp) / "graph.db"))
        try:
            backend = SqliteBackend(conn=conn)
            bench = run_benchmark(backend, files)
            backend.link_external_stubs()
            backend.link_import_bindings()

            previous_singleton = graph_tools._BACKEND_SINGLETON
            graph_tools._BACKEND_SINGLETON = backend
            try:
                probes = _top_degree_symbols(backend, queries)
                rows = _probe_rows(graph_tools, probes, corpus, baseline)
            finally:
                graph_tools._BACKEND_SINGLETON = previous_singleton
        finally:
            conn.close()

    return {
        "repo": repo_label,
        "ref": ref,
        "files": len(files),
        "nodes": bench.nodes_written,
        "edges": bench.edges_written,
        "index_ms": bench.index_duration_ms,
        "token_estimator": "chars/4 heuristic (production envelope estimator)",
        "baseline": baseline.value,
        "baseline_note": baseline_note(baseline),
        "context_budget_tokens": context_budget_tokens,
        "summary": _summarize(rows, context_budget_tokens),
        "probes": [r.to_dict() for r in rows],
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(f"[OK] baseline={report['baseline']} — {report['baseline_note']}", file=sys.stderr)
    for workflow, stats in report["summary"].items():
        if not stats.get("probes"):
            print(f"[SKIP] {workflow}: every probe returned a truncated walk", file=sys.stderr)
            continue
        marker = "[WARN]" if stats["skipped_incomplete"] else "[OK]"
        print(
            f"{marker} {workflow:12s} median {stats['median_savings_pct']}% "
            f"mean {stats['mean_savings_pct']}% min {stats['min_savings_pct']}% "
            f"({stats['probes']} probes, {stats['skipped_incomplete']} skipped incomplete) "
            f"break-even {stats['break_even_queries']} queries",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure graph-envelope vs graph-less token cost on a third-party repo."
    )
    parser.add_argument("--repo", required=True, help="Local path or git URL of the target repo.")
    parser.add_argument("--ref", default=None, help="Tag/branch to pin when --repo is a URL.")
    parser.add_argument("--queries", type=int, default=10, help="Number of probe symbols.")
    parser.add_argument(
        "--baseline",
        type=Baseline,
        choices=list(Baseline),
        default=Baseline.GREP_WINDOWS,
        metavar="{" + ",".join(b.value for b in Baseline) + "}",
        help="What the graph-less agent is assumed to do (default: grep-windows).",
    )
    parser.add_argument(
        "--context-budget-tokens",
        type=int,
        default=DEFAULT_CONTEXT_BUDGET_TOKENS,
        help="Always-on instruction cost to amortize; see src/scripts/context_budget.py.",
    )
    parser.add_argument("--out", default=None, help="Write the JSON report here (default stdout).")
    args = parser.parse_args(argv)

    kwargs = {
        "queries": args.queries,
        "ref": args.ref,
        "baseline": args.baseline,
        "context_budget_tokens": args.context_budget_tokens,
    }
    local = Path(args.repo).expanduser()
    if local.exists():
        report = measure_repo(local, repo_label=str(local), **kwargs)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = _clone(args.repo, args.ref, Path(tmp) / "repo")
            report = measure_repo(checkout, repo_label=args.repo, **kwargs)

    payload = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    _print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
