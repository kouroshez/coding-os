"""Classify an incident's severity (SEV1-4) from its impact signals.

PURPOSE:      Remove the "what SEV is this?" debate at 3am — feed the impact
              facts, get a deterministic level + the response it implies.
INPUT:        flags describing impact:
                --users-affected <0-100>  percent of users impacted
                --data-loss               irreversible data loss/corruption
                --security-breach         confirmed/suspected breach
                --core-down               a core user journey is unavailable
                --workaround              a viable workaround exists
              [--json]
OUTPUT:       Level + rationale + response on stderr; "SEV<n>" on stdout.
              Exit 0 always (classification is not a failure). Exit 2 on usage.
DEPENDENCIES: stdlib only.
NOTES:        Pure classify() is unit-testable. Adjust thresholds per your SEV
              policy. Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import sys

RESPONSE = {
    1: "page on-call now · incident commander · status page · all-hands until mitigated",
    2: "page on-call · dedicated responder · update stakeholders · fix within hours",
    3: "ticket + owner · fix in normal working hours",
    4: "backlog · fix when convenient",
}


def classify(
    *,
    users_affected: float,
    data_loss: bool,
    security_breach: bool,
    core_down: bool,
    workaround: bool,
) -> tuple[int, str]:
    if data_loss or security_breach:
        return 1, "irreversible data loss or security breach — always SEV1"
    if core_down and users_affected >= 50 and not workaround:
        return 1, "core journey down for most users, no workaround"
    if core_down or users_affected >= 25:
        level = 3 if workaround else 2
        why = "core journey impacted" if core_down else f"{users_affected:.0f}% of users impacted"
        return level, f"{why}{' (workaround exists → lower)' if workaround else ''}"
    if users_affected > 0:
        return 3, f"{users_affected:.0f}% of users impacted, no core journey down"
    return 4, "minimal/no user impact"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--users-affected", default=0.0, type=float)
    parser.add_argument("--data-loss", action="store_true")
    parser.add_argument("--security-breach", action="store_true")
    parser.add_argument("--core-down", action="store_true")
    parser.add_argument("--workaround", action="store_true")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    if not 0 <= args.users_affected <= 100:
        print("error: --users-affected must be 0-100", file=sys.stderr)
        return 2

    level, why = classify(
        users_affected=args.users_affected,
        data_loss=args.data_loss,
        security_breach=args.security_breach,
        core_down=args.core_down,
        workaround=args.workaround,
    )
    response = RESPONSE[level]
    print(f"  SEV{level}: {why}", file=sys.stderr)
    print(f"  response: {response}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"severity": level, "rationale": why, "response": response}))
    else:
        print(f"SEV{level}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
