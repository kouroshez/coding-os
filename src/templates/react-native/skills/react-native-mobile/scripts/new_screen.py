"""Generate a React Native screen scaffold per `references/anatomy.md`.

PURPOSE:      Emit a screen + colocated test with the canonical
              three-state async UI shell.
INPUT:        --name <kebab-case>     — file slug.
              [--tab]                 — place under `app/(tabs)/`; default is plain stack screen.
              [--root <dir>]          — defaults to `src/mobile/`.
OUTPUT:       Two files: the screen tsx + colocated test.
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
    parser.add_argument("--name", required=True)
    parser.add_argument("--tab", action="store_true")
    parser.add_argument("--root", default="src/mobile")
    args = parser.parse_args()

    base = Path(args.root) / "app"
    target_dir = base / "(tabs)" if args.tab else base
    target_dir.mkdir(parents=True, exist_ok=True)
    screen_path = target_dir / f"{args.name}.tsx"
    test_path = target_dir / f"{args.name}.test.tsx"

    if screen_path.exists() or test_path.exists():
        print(f"ERROR: refuse to overwrite existing files in {target_dir}", file=sys.stderr)
        return 1

    pascal = _pascal(args.name) + "Screen"
    screen_path.write_text(
        f"import {{ ActivityIndicator, Text, View }} from 'react-native';\n\n"
        f"export default function {pascal}() {{\n"
        f"  // TODO: replace with real data fetching hook.\n"
        f"  const loading = false;\n"
        f"  const error: Error | null = null;\n"
        f"  const data: unknown = null;\n\n"
        f'  if (loading) return <ActivityIndicator accessibilityLabel="Loading" />;\n'
        f'  if (error) return <Text accessibilityRole="alert">{{error.message}}</Text>;\n'
        f"  if (!data) return <Text>Empty</Text>;\n"
        f'  return <View testID="{args.name}" />;\n'
        f"}}\n",
        encoding="utf-8",
    )
    test_path.write_text(
        f"import {{ render }} from '@testing-library/react-native';\n"
        f"import {pascal} from './{args.name}';\n\n"
        f"describe('{pascal}', () => {{\n"
        f"  it('renders the empty state by default', () => {{\n"
        f"    const {{ getByText }} = render(<{pascal} />);\n"
        f"    expect(getByText('Empty')).toBeTruthy();\n"
        f"  }});\n"
        f"}});\n",
        encoding="utf-8",
    )
    print(f"OK: wrote {screen_path}")
    print(f"OK: wrote {test_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
