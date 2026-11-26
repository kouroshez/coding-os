"""Enforce a coverage threshold from a coverage report (gate for CI).

PURPOSE:      Fail a build when line coverage drops below a floor — one command
              instead of eyeballing a report. Reads coverage.py JSON or
              Cobertura XML so it works for Python and most JS/Go toolchains.
INPUT:        report path (coverage.json / coverage.xml) or --file. [--min N]
              required percent (default 80). [--json]
OUTPUT:       Percent + verdict on stderr; "pass"/"fail" on stdout. Exit 0 if
              >= min, 1 if below, 2 usage/parse error.
DEPENDENCIES: stdlib only (json, xml.etree).
NOTES:        Pure percent_from_* parsers are unit-testable. Spec:
              docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def percent_from_coveragepy(text: str) -> float:
    data = json.loads(text)
    return float(data["totals"]["percent_covered"])


def percent_from_cobertura(text: str) -> float:
    root = ET.fromstring(text)
    # Cobertura root carries line-rate in [0,1]; convert to percent.
    rate = root.get("line-rate")
    if rate is None:
        raise ValueError("no line-rate on cobertura root")
    return float(rate) * 100.0


def parse_percent(path: Path) -> float:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return percent_from_coveragepy(text)
    if path.suffix == ".xml":
        return percent_from_cobertura(text)
    # sniff
    stripped = text.lstrip()
    return (
        percent_from_coveragepy(text) if stripped.startswith("{") else percent_from_cobertura(text)
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", nargs="?", default="coverage.json")
    parser.add_argument("--file", default=None)
    parser.add_argument("--min", default=80.0, type=float)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    target = Path(args.file or args.path)
    try:
        pct = parse_percent(target)
    except FileNotFoundError:
        print(f"error: {target} not found", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ET.ParseError, KeyError, ValueError) as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
        return 2

    ok = pct >= args.min
    print(f"  coverage {pct:.1f}% (min {args.min:.1f}%)", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"percent": round(pct, 2), "min": args.min, "pass": ok}))
    else:
        print("pass" if ok else "fail")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
