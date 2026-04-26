"""Phase I demo — index a folder and open the graph_os viewer in a browser.

Usage:
    uv run --extra rag python scripts/graph_demo.py              # index the repo
    uv run --extra rag python scripts/graph_demo.py --path docs  # just docs/
    uv run --extra rag python scripts/graph_demo.py --serve      # local HTTP server

No external services; everything runs locally in SQLite + a static HTML
file. Opens the viewer in your default browser at the end.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import webbrowser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "core"))
sys.path.insert(0, str(REPO_ROOT / "core" / "thinking_os"))

from db import init_db  # type: ignore  # noqa: E402
from graph_os.backends.sqlite_backend import SqliteBackend  # noqa: E402
from graph_os.extractors import (  # noqa: E402
    code_python,
    code_shell,
    code_ts,
    code_yaml,
    contracts,
    md_links,
    task_deps,
)
from graph_os.ingest import walk_local  # noqa: E402
from graph_os.viewer import build_view  # noqa: E402


def _extractors_for(path: str) -> list:
    if path.endswith(".py"):
        return [code_python.extract, contracts.extract]
    if path.endswith((".ts", ".tsx")):
        return [code_ts.extract, contracts.extract]
    if path.endswith(".sh"):
        return [code_shell.extract]
    if path.endswith((".yaml", ".yml")):
        return [code_yaml.extract]
    if path.endswith(".md"):
        if "/tasks/" in path:
            return [task_deps.extract, md_links.extract]
        return [md_links.extract]
    if path.endswith(".go"):
        return [contracts.extract]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=str(REPO_ROOT))
    parser.add_argument(
        "--out", default=str(REPO_ROOT / ".coding-os" / "graph-viz.html")
    )
    parser.add_argument("--db", default=None)
    parser.add_argument("--max-files", type=int, default=2000)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    db_path = args.db or tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    print(f"[demo] init DB at {db_path}")
    conn = init_db(db_path)
    backend = SqliteBackend(conn=conn)

    target = Path(args.path).resolve()
    print(f"[demo] walking {target} ...")
    plan = walk_local(target, max_files=args.max_files)
    print(f"[demo] collected {len(plan.files)} files")

    started = time.monotonic()
    indexed = skipped = errors = 0
    for file_path in plan.files:
        try:
            rel = str(file_path.relative_to(target))
        except ValueError:
            rel = str(file_path)
        extractors = _extractors_for(rel)
        if not extractors:
            skipped += 1
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            errors += 1
            continue
        for extractor in extractors:
            try:
                result = extractor(rel, content)
                backend.bulk_upsert(result.nodes, result.edges)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                print(f"[demo]   ! {rel}: {extractor.__name__} -> {exc}")
        indexed += 1
    elapsed_ms = int((time.monotonic() - started) * 1000)
    node_count = backend.count_nodes()
    edge_count = backend.count_edges()
    print(
        f"[demo] indexed {indexed} files (skipped {skipped}, errors {errors}) "
        f"in {elapsed_ms} ms -> {node_count} nodes, {edge_count} edges"
    )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    build_view(backend, out_path, title=f"graph_os @ {target.name}")
    print(f"[demo] HTML written -> {out_path}")

    if args.serve:
        _serve(out_path, port=args.port, open_browser=not args.no_open)
    elif not args.no_open:
        webbrowser.open(out_path.as_uri())
        print("[demo] opened in default browser (file:// URL)")
    else:
        print(f"[demo] open it manually: {out_path.as_uri()}")
    return 0


def _serve(path: Path, *, port: int, open_browser: bool) -> None:
    """Tiny static server - binds to 127.0.0.1 only."""
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    os.chdir(path.parent)

    class _Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args, **_kwargs):
            pass

    actual_port = port or _pick_free_port()
    httpd = HTTPServer(("127.0.0.1", actual_port), _Handler)
    url = f"http://127.0.0.1:{actual_port}/{path.name}"
    print(f"[demo] serving at {url}")
    print("[demo] Ctrl-C to stop")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[demo] bye")
        httpd.shutdown()


def _pick_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


if __name__ == "__main__":
    raise SystemExit(main())
