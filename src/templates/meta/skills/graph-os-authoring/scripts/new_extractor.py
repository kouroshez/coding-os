"""Scaffold a graph_os extractor stub (idempotent on uid, content-hash short-circuit).

PURPOSE:      Emit an extractor that already obeys the graph_os invariants —
              idempotent on uid, short-circuits via file_index_state, returns
              typed nodes/edges — so the author fills extraction logic only.
INPUT:        --lang <python|typescript|go|...> (the language it extracts)
              [--out <path>]  write to a file instead of printing.
OUTPUT:       The extractor source on stdout (or to --out). Exit 0; 2 usage.
DEPENDENCIES: stdlib only.
NOTES:        Pure render() is unit-testable. Register the extractor in the
              reindex dispatcher by hand. Spec: docs/engineering/graph_os-queries.md.
"""

from __future__ import annotations

import argparse
import re
import sys

TEMPLATE = '''\
"""Extractor for {lang} files — emits graph_os nodes + edges."""

from __future__ import annotations

from graph_os.types import Node, Edge


def extract_{lang}(path: str, content: str, content_hash: str) -> tuple[list[Node], list[Edge]]:
    # Short-circuit: the dispatcher skips unchanged files via file_index_state,
    # but guard here too so a direct call is cheap on a known hash.
    nodes: list[Node] = []
    edges: list[Edge] = []

    # uid MUST be deterministic for the same symbol → idempotent upsert.
    # uid = f"{lang}:{{path}}::{{symbol_name}}"

    # TODO: parse `content` (tree-sitter / ast / regex fallback) and append
    #       Node(uid=..., kind=..., name=..., file=path) and
    #       Edge(src_uid=..., dst_uid=..., kind="calls|imports|contains|...").

    return nodes, edges
'''


def render(lang: str) -> str:
    safe = re.sub(r"[^a-z0-9_]", "_", lang.lower()).strip("_") or "lang"
    return TEMPLATE.format(lang=safe)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lang", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if not args.lang.strip():
        print("error: --lang must be non-empty", file=sys.stderr)
        return 2

    code = render(args.lang)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(code)
        print(args.out)
    else:
        sys.stdout.write(code)
    print("reminder: register the extractor in the reindex dispatcher; "
          "verify with: uv run --extra graph_os pytest src/core/graph_os/tests/ -q", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
