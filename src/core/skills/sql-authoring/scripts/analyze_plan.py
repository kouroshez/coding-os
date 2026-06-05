"""Summarize a PostgreSQL EXPLAIN (FORMAT JSON) plan and flag problems.

PURPOSE:      Turn a verbose EXPLAIN plan into a few actionable lines so the
              agent reads one summary, not a 200-line tree. Flags seq scans on
              big inputs, bad row estimates, and risky nested loops.
INPUT:        EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) output on stdin, or
              --file <path>. [--rows-threshold N] big-scan cutoff (default 1000).
              [--estimate-ratio R] estimate-miss factor (default 10). [--json]
OUTPUT:       Findings + a one-line verdict on stderr; result on stdout
              ("clean" or "N finding(s)"). Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only. Works offline — you pipe the plan in.
NOTES:        Pure analysis layer (walk_plan) is unit-testable without a DB.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys


def _node_findings(node: dict, rows_threshold: int, estimate_ratio: float) -> list[str]:
    out: list[str] = []
    ntype = node.get("Node Type", "?")
    rel = node.get("Relation Name")
    plan_rows = node.get("Plan Rows")
    actual = node.get("Actual Rows")
    where = f" on {rel}" if rel else ""

    if ntype == "Seq Scan":
        big = (actual if actual is not None else plan_rows) or 0
        if big >= rows_threshold:
            out.append(f"seq scan{where}: {big} rows — missing/unused index on the filtered column?")

    if plan_rows and actual is not None and plan_rows > 0:
        ratio = max(plan_rows, actual) / max(min(plan_rows, actual), 1)
        if ratio >= estimate_ratio:
            out.append(f"estimate off{where}: planned {plan_rows} vs actual {actual} "
                       f"({ratio:.0f}x) — stale stats (ANALYZE) or a bad correlation assumption")

    if ntype == "Nested Loop" and node.get("Plans"):
        inner_rows = max((c.get("Actual Rows", c.get("Plan Rows", 0)) or 0)
                         for c in node["Plans"])
        if inner_rows >= rows_threshold:
            out.append(f"nested loop over ~{inner_rows} inner rows — a hash/merge join may be cheaper")

    return out


def walk_plan(plan: dict, rows_threshold: int, estimate_ratio: float) -> list[str]:
    findings = _node_findings(plan, rows_threshold, estimate_ratio)
    for child in plan.get("Plans", []):
        findings.extend(walk_plan(child, rows_threshold, estimate_ratio))
    return findings


def analyze(explain_json: object, rows_threshold: int, estimate_ratio: float) -> list[str]:
    # EXPLAIN FORMAT JSON returns a list whose first item holds {"Plan": {...}}.
    root = explain_json[0] if isinstance(explain_json, list) else explain_json
    if not isinstance(root, dict) or "Plan" not in root:
        raise ValueError("input is not an EXPLAIN (FORMAT JSON) plan")
    return walk_plan(root["Plan"], rows_threshold, estimate_ratio)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--file", default=None)
    parser.add_argument("--rows-threshold", default=1000, type=int)
    parser.add_argument("--estimate-ratio", default=10.0, type=float)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    if not raw.strip():
        print("error: no EXPLAIN JSON on stdin (or --file)", file=sys.stderr)
        return 2
    try:
        findings = analyze(json.loads(raw), args.rows_threshold, args.estimate_ratio)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    for f in findings:
        print(f"  ✗ {f}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"findings": findings, "count": len(findings)}))
    else:
        print("clean" if not findings else f"{len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
