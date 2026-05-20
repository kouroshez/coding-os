"""Generate a Next.js component scaffold per `references/anatomy.md`.

PURPOSE:      Eliminate the per-component boilerplate path-decision so
              every agent (claude / codex / cursor) emits the same shape.
INPUT:        --area <segment>     — e.g. users, products
              --name <kebab-case>  — file slug
              [--client]           — emits `<name>.client.tsx` instead.
              [--root <dir>]       — defaults to `src/frontend/`.
OUTPUT:       Two files: `<area>/<name>.tsx` (or `.client.tsx`) +
              `<area>/<name>.test.tsx`.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent — refuses to overwrite existing files.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("-") if part)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--area", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--root", default="src/frontend")
    args = parser.parse_args()

    target_dir = Path(args.root) / "components" / args.area
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".client.tsx" if args.client else ".tsx"
    component_path = target_dir / f"{args.name}{suffix}"
    test_path = target_dir / f"{args.name}.test.tsx"

    if component_path.exists() or test_path.exists():
        print(f"ERROR: refuse to overwrite existing files in {target_dir}", file=sys.stderr)
        return 1

    pascal = _pascal(args.name)
    body_header = "'use client';\n\n" if args.client else ""
    component_path.write_text(
        f"{body_header}export interface {pascal}Props {{\n"
        f"  // TODO: define props\n"
        f"}}\n\n"
        f"export function {pascal}(_props: {pascal}Props) {{\n"
        f'  return <div data-testid="{args.name}" />;\n'
        f"}}\n",
        encoding="utf-8",
    )
    test_path.write_text(
        f"import {{ render, screen }} from '@testing-library/react';\n"
        f"import {{ {pascal} }} from './{args.name}{'.client' if args.client else ''}';\n\n"
        f"describe('{pascal}', () => {{\n"
        f"  it('renders the {args.name} container', () => {{\n"
        f"    render(<{pascal} />);\n"
        f"    expect(screen.getByTestId('{args.name}')).toBeInTheDocument();\n"
        f"  }});\n"
        f"}});\n",
        encoding="utf-8",
    )
    print(f"OK: wrote {component_path}")
    print(f"OK: wrote {test_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
