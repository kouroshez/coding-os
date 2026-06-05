"""Scaffold a compliant cos_* MCP tool stub (envelope + naming + docstring).

PURPOSE:      Emit a tool that already obeys Rule 2 (cos_ prefix), Rule 12
              (one-line docstring), and Rule 13 (@safe_tool + ok/fail envelope)
              so the author fills logic, not boilerplate.
INPUT:        --name <tool>  (without the cos_ prefix; added if missing)
              --layer <memory|docs|tasks|graph|board|cognition|...> (meta.layer)
              [--out <path>]  append to a file instead of printing.
OUTPUT:       The tool source on stdout (or appended to --out). Exit 0; 2 usage.
DEPENDENCIES: stdlib only.
NOTES:        Pure render() is unit-testable. Register the tool + update
              docs/governance/mcp-tool-inventory.md by hand. Spec:
              docs/playbooks/mcp-tool-authoring.md.
"""

from __future__ import annotations

import argparse
import re
import sys

TEMPLATE = '''\
@safe_tool
@mcp.tool()
def {fn}(arg: str) -> dict:
    """{summary}"""
    if not arg:
        return fail("validation", "arg must be non-empty")
    result = {fn}_impl(arg)
    return ok({{"result": result, "meta": {{"layer": "{layer}"}}}})
'''


def normalize(name: str) -> str:
    name = re.sub(r"[^a-z0-9_]", "_", name.lower()).strip("_")
    return name if name.startswith("cos_") else f"cos_{name}"


def render(name: str, layer: str) -> str:
    fn = normalize(name)
    summary = fn.replace("cos_", "").replace("_", " ").strip().capitalize() + " — one-line description."
    return TEMPLATE.format(fn=fn, layer=layer, summary=summary)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--name", required=True)
    parser.add_argument("--layer", default="memory")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    if not args.name.strip():
        print("error: --name must be non-empty", file=sys.stderr)
        return 2

    code = render(args.name, args.layer)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as fh:
            fh.write("\n\n" + code)
        print(args.out)
    else:
        sys.stdout.write(code)
    print("reminder: add @safe_tool/ok/fail imports from tools._shared; register + "
          "update docs/governance/mcp-tool-inventory.md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
