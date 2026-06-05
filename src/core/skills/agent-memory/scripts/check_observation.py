"""Validate an agent-memory observation against the memory policy before recording.

PURPOSE:      Stop low-quality or unsafe observations from polluting memory —
              check confidence range, required fields, and PII/secret leakage
              before cos_observation_record is called.
INPUT:        observation JSON on stdin or --file. Shape:
                {"type": "pattern|workflow|error|decision|discovery",
                 "summary": "...", "confidence": 0.5, "impact": 0.5}
              [--json]
OUTPUT:       Findings on stderr; "ok"/"N issue(s)" on stdout. Exit 0 ok,
              1 if issues, 2 usage/parse error.
DEPENDENCIES: stdlib only.
NOTES:        Pure validate() is unit-testable. Policy SSOT: src/core/rules/memory.md.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

VALID_TYPES = {"pattern", "workflow", "error", "decision", "discovery"}
PII = re.compile(r"(?i)\b([\w.+-]+@[\w-]+\.\w+|\d{3}-\d{2}-\d{4}|\b(?:\d[ -]?){13,16}\b)")
SECRET = re.compile(r"(?i)(password|secret|api[_-]?key|token)\s*[:=]\s*\S+")


def validate(obs: dict) -> list[str]:
    issues: list[str] = []
    if obs.get("type") not in VALID_TYPES:
        issues.append(f"type must be one of {sorted(VALID_TYPES)} (got {obs.get('type')!r})")
    summary = obs.get("summary", "")
    if not isinstance(summary, str) or len(summary.strip()) < 10:
        issues.append("summary missing or too short (<10 chars) — say what was learned")
    for field in ("confidence", "impact"):
        val = obs.get(field)
        if val is None:
            issues.append(f"{field} missing (default 0.5; raise to 0.8+ only after a 2nd confirmation)")
        elif not isinstance(val, (int, float)) or not 0.0 <= val <= 1.0:
            issues.append(f"{field} must be a number in [0,1] (got {val!r})")
    blob = json.dumps(obs)
    if PII.search(blob):
        issues.append("PII detected (email/SSN/card) — never store PII in memory; use an id/hash")
    if SECRET.search(blob):
        issues.append("secret-shaped value detected — never store secrets in memory")
    return issues


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--file", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    raw = open(args.file, encoding="utf-8").read() if args.file else sys.stdin.read()
    if not raw.strip():
        print("error: no observation JSON (stdin or --file)", file=sys.stderr)
        return 2
    try:
        obs = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(obs, dict):
        print("error: observation must be a JSON object", file=sys.stderr)
        return 2

    issues = validate(obs)
    for i in issues:
        print(f"  ✗ {i}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"issues": issues, "count": len(issues)}))
    else:
        print("ok" if not issues else f"{len(issues)} issue(s)")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
