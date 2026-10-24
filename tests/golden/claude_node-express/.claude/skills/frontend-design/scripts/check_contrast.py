"""Compute the WCAG contrast ratio of two colors and report AA/AAA pass/fail.

PURPOSE:      Verify a text/background pair is readable (and accessible) before
              it ships — design and a11y in one check.
INPUT:        two colors as hex (#rrggbb / #rgb) or "r,g,b". [--large] (large
              text uses the 3:1 / 4.5:1 thresholds). [--json]
OUTPUT:       Ratio + AA/AAA verdict on stderr; "pass"/"fail" (vs AA) on stdout.
              Exit 0 if AA passes, 1 if not, 2 usage/parse error.
DEPENDENCIES: stdlib only.
NOTES:        Implements WCAG 2.x relative-luminance + contrast formula. Pure
              contrast_ratio() is unit-testable. Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys


def parse_color(s: str) -> tuple[int, int, int]:
    s = s.strip()
    if s.startswith("#"):
        h = s[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) != 6:
            raise ValueError(f"bad hex color: {s}")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        raise ValueError(f"bad color: {s}")
    rgb = tuple(int(p) for p in parts)
    if any(not 0 <= v <= 255 for v in rgb):
        raise ValueError(f"rgb out of range: {s}")
    return rgb  # type: ignore[return-value]


def _luminance(rgb: tuple[int, int, int]) -> float:
    def chan(c: int) -> float:
        x = c / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1, l2 = _luminance(c1), _luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("fg")
    parser.add_argument("bg")
    parser.add_argument("--large", action="store_true", help="large text thresholds")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    try:
        ratio = contrast_ratio(parse_color(args.fg), parse_color(args.bg))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    aa = 3.0 if args.large else 4.5
    aaa = 4.5 if args.large else 7.0
    passes_aa, passes_aaa = ratio >= aa, ratio >= aaa
    print(
        f"  contrast {ratio:.2f}:1 — AA {'pass' if passes_aa else 'FAIL'} "
        f"(>= {aa}), AAA {'pass' if passes_aaa else 'FAIL'} (>= {aaa})",
        file=sys.stderr,
    )
    if args.as_json:
        print(
            json.dumps(
                {"ratio": round(ratio, 2), "aa": passes_aa, "aaa": passes_aaa, "large": args.large}
            )
        )
    else:
        print("pass" if passes_aa else "fail")
    return 0 if passes_aa else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
