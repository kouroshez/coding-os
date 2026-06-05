"""Audit a tsconfig.json for the strictness flags that catch real bugs.

PURPOSE:      Flag a tsconfig that leaves the type checker blindfolded — one
              summary instead of eyeballing nested compilerOptions.
INPUT:        tsconfig path (default tsconfig.json) or --file. [--json]
OUTPUT:       Findings on stderr; "clean"/"N finding(s)" on stdout. Exit 0
              clean, 1 findings, 2 usage/parse error.
DEPENDENCIES: stdlib only. Tolerates JSONC (comments, trailing commas).
NOTES:        `extends` is NOT resolved — a flag may be inherited; the script
              says so rather than guess. Pure audit() is unit-testable.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# flag -> (required_value, why)
REQUIRED = {
    "strict": (True, "the umbrella flag — without it null-safety + implicit-any are off"),
}
RECOMMENDED = {
    "noUncheckedIndexedAccess": (True, "makes arr[i] honestly T | undefined"),
    "noImplicitOverride": (True, "catches a method that no longer overrides its base"),
    "exactOptionalPropertyTypes": (True, "distinguishes missing from undefined"),
    "noFallthroughCasesInSwitch": (True, "catches a missing break/return in a switch"),
}


def strip_jsonc(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)   # block comments
    text = re.sub(r"(^|\s)//[^\n]*", r"\1", text)            # line comments
    text = re.sub(r",(\s*[}\]])", r"\1", text)               # trailing commas
    return text


def load_tsconfig(text: str) -> dict:
    data = json.loads(strip_jsonc(text))
    if not isinstance(data, dict):
        raise ValueError("tsconfig root must be an object")
    return data


def audit(config: dict) -> list[str]:
    opts = config.get("compilerOptions", {})
    findings: list[str] = []
    for flag, (want, why) in REQUIRED.items():
        if opts.get(flag) != want:
            findings.append(f"{flag} != {json.dumps(want)} — {why}")
    for flag, (want, why) in RECOMMENDED.items():
        if opts.get(flag) != want:
            findings.append(f"{flag} not set — {why}")
    if "extends" in config and findings:
        findings.append(f"note: this config extends {config['extends']!r}; "
                        "a flag above may be inherited — verify the resolved config")
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("path", nargs="?", default="tsconfig.json")
    parser.add_argument("--file", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    target = args.file or args.path
    try:
        findings = audit(load_tsconfig(open(target, encoding="utf-8").read()))
    except FileNotFoundError:
        print(f"error: {target} not found", file=sys.stderr)
        return 2
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: {target}: {exc}", file=sys.stderr)
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
