"""Classify a meta-repo path into its DNA→mRNA→phenotype layer + propagation.

PURPOSE:      Answer "which layer does this file belong to, and how does an edit
              reach consumers?" before editing — the most common meta-repo
              mis-step is editing the wrong layer.
INPUT:        one or more repo-relative paths. [--json]
OUTPUT:       layer + propagation per path on stdout. Exit 0; 2 usage.
DEPENDENCIES: stdlib only.
NOTES:        Pure classify() is unit-testable. Mirrors AGENTS.md Modularity Map.
              Spec: docs/architecture/meta-project.md.
"""

from __future__ import annotations

import argparse
import json
import sys

# (path-prefix, layer, propagation) — first match wins; order most-specific first.
RULES: list[tuple[str, str, str]] = [
    ("src/core/hooks/", "DNA (core)", "live symlink — reaches every consumer immediately"),
    ("src/core/thinking_os/", "DNA (core)", "MCP server restart picks it up"),
    ("src/core/graph_os/", "DNA (core)", "MCP server restart"),
    ("src/core/board_os/", "DNA (core)", "MCP server restart"),
    ("src/core/rules/", "DNA (core)", "live symlink + `cos update` in consumer"),
    ("src/core/skills/", "DNA (core)", "live symlink + `cos update` in consumer"),
    ("src/core/web/", "DNA (core)", "hub restart / `cos hub restart`"),
    ("src/core/", "DNA (core)", "varies — see Modularity Map"),
    ("src/adapters/", "mRNA (adapter)", "`bash src/adapters/<id>/install.sh` (manual)"),
    ("src/templates/", "phenotype (stack)", "`cos update` + `make manifest-regen` (manual)"),
    ("src/cli/", "factory (CLI)", "new `cos` invocations after `uv tool install --editable .`"),
    ("docs/", "docs", "meta-repo only unless in the base/stack scaffold"),
    ("tests/", "tests", "meta-repo only — never ships"),
]


def classify(path: str) -> tuple[str, str]:
    p = path.lstrip("./")
    for prefix, layer, propagation in RULES:
        if p.startswith(prefix):
            return layer, propagation
    return "unknown", "not a recognized meta-repo layer path"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    rows = [{"path": p, "layer": (c := classify(p))[0], "propagation": c[1]} for p in args.paths]
    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['path']}\n  layer: {r['layer']}\n  reaches consumer: {r['propagation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
