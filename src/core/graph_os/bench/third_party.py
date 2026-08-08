"""Token-cost benchmark against a real third-party repo.

Methodology SSOT: docs/engineering/third-party-token-bench.md — graph
envelope tokens vs the grep-then-read-every-matching-file baseline,
measured on the target repo's own .py corpus with the production
extractors, backend, and token estimator.

DEPENDS: graph_os.bench.harness, graph_os.bench.token_cost,
         graph_os.backends.sqlite_backend, git (only for URL targets).
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

_HERE = Path(__file__).resolve()
_CORE_DIR = _HERE.parent.parent.parent
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from graph_os.backends.sqlite_backend import SqliteBackend  # noqa: E402
from graph_os.bench.harness import run_benchmark  # noqa: E402
from graph_os.bench.token_cost import (  # noqa: E402
    _envelope_tokens,
    _fresh_conn,
    _token_estimator,
)

WORKFLOWS = ("references", "impact", "rename_plan")

_SKIP_DIR_NAMES = frozenset(
    {".git", ".hg", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"}
)
_MAX_FILE_BYTES = 2 * 1024 * 1024
_CLONE_TIMEOUT_SECONDS = 300
_PROBE_SAMPLE_LIMIT = 400
_PROBE_EDGE_SCAN_LIMIT = 500


@dataclass
class ProbeRow:
    uid: str
    label: str
    workflow: str
    graph_tokens: int
    naive_tokens: int
    savings_pct: float

    def to_dict(self) -> dict:
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


def _top_degree_symbols(backend: SqliteBackend, count: int) -> list:
    scored = []
    for kind in ("function", "class"):
        for node in backend.sample_nodes(kind, limit=_PROBE_SAMPLE_LIMIT):
            degree = len(backend.list_edges(target_uid=node.uid, limit=_PROBE_EDGE_SCAN_LIMIT))
            scored.append((degree, node))
    scored.sort(key=lambda pair: (-pair[0], pair[1].uid))
    return [node for _, node in scored[:count]]


def _naive_grep_read_tokens(files: list[Path], symbol_name: str, estimate) -> int:
    total_chars = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if symbol_name in text:
            total_chars += len(text)
    return max(1, estimate("x" * total_chars))


def measure_repo(repo_root: Path, *, queries: int, repo_label: str, ref: str | None) -> dict:
    from graph_os.tools import graph as graph_tools

    estimate = _token_estimator()
    files = _collect_python_files(repo_root)
    if not files:
        raise SystemExit(f"no .py files found under {repo_root}")

    with tempfile.TemporaryDirectory() as tmp:
        conn = _fresh_conn(str(Path(tmp) / "graph.db"))
        try:
            backend = SqliteBackend(conn=conn)
            bench = run_benchmark(backend, files)
            backend.link_external_stubs()
            backend.link_import_bindings()

            prev_singleton = graph_tools._BACKEND_SINGLETON
            graph_tools._BACKEND_SINGLETON = backend
            try:
                probes = _top_degree_symbols(backend, queries)
                rows: list[ProbeRow] = []
                for node in probes:
                    naive = _naive_grep_read_tokens(files, node.label, estimate)
                    envelopes = {
                        "references": graph_tools.cos_graph_references(node.uid),
                        "impact": graph_tools.cos_graph_impact(node.uid, depth=3),
                        "rename_plan": graph_tools.cos_graph_rename_plan(
                            node.uid, node.label + "_renamed"
                        ),
                    }
                    for workflow in WORKFLOWS:
                        graph_tokens = max(1, _envelope_tokens(envelopes[workflow], estimate))
                        rows.append(
                            ProbeRow(
                                uid=node.uid,
                                label=node.label,
                                workflow=workflow,
                                graph_tokens=graph_tokens,
                                naive_tokens=naive,
                                savings_pct=round((1 - graph_tokens / naive) * 100, 1),
                            )
                        )
            finally:
                graph_tools._BACKEND_SINGLETON = prev_singleton
        finally:
            conn.close()

    summary = {}
    for workflow in WORKFLOWS:
        savings = [r.savings_pct for r in rows if r.workflow == workflow]
        summary[workflow] = {
            "median_savings_pct": round(statistics.median(savings), 1),
            "mean_savings_pct": round(statistics.fmean(savings), 1),
            "min_savings_pct": min(savings),
            "probes": len(savings),
        }
    return {
        "repo": repo_label,
        "ref": ref,
        "files": len(files),
        "nodes": bench.nodes_written,
        "edges": bench.edges_written,
        "index_ms": bench.index_duration_ms,
        "token_estimator": "chars/4 heuristic (production envelope estimator)",
        "summary": summary,
        "probes": [r.to_dict() for r in rows],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure graph-envelope vs grep+read token cost on a third-party repo."
    )
    parser.add_argument("--repo", required=True, help="Local path or git URL of the target repo.")
    parser.add_argument("--ref", default=None, help="Tag/branch to pin when --repo is a URL.")
    parser.add_argument("--queries", type=int, default=10, help="Number of probe symbols.")
    parser.add_argument("--out", default=None, help="Write the JSON report here (default stdout).")
    args = parser.parse_args(argv)

    local = Path(args.repo).expanduser()
    if local.exists():
        report = measure_repo(local, queries=args.queries, repo_label=str(local), ref=args.ref)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            checkout = _clone(args.repo, args.ref, Path(tmp) / "repo")
            report = measure_repo(
                checkout, queries=args.queries, repo_label=args.repo, ref=args.ref
            )

    payload = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    for workflow, stats in report["summary"].items():
        print(
            f"[bench] {workflow:12s} median {stats['median_savings_pct']}% "
            f"mean {stats['mean_savings_pct']}% min {stats['min_savings_pct']}% "
            f"({stats['probes']} probes)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
