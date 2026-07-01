"""Flag stale/deprecated Claude model ids in SDK code and suggest current ones.

PURPOSE:      Catch a hardcoded retired model id before it 404s in production —
              model ids rotate and old ones get deprecated.
INPUT:        one or more source paths. [--json]
OUTPUT:       Findings (file:line) on stderr; "clean"/"N finding(s)" on stdout.
              Exit 0 clean, 1 if findings, 2 usage.
DEPENDENCIES: stdlib only (regex).
NOTES:        The CURRENT map is editable below — update it when the model family
              rotates (this is the one place to change). Pure scan_text() is
              unit-testable. Spec: docs/adapters/claude-sdk.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Current generation. Cross-check against src/adapters/claude/adapter.yaml::models
# (the Hub picker SSOT) whenever the family rotates — this script stays a
# self-contained stdlib literal (portable to every consumer project) rather
# than reading that YAML, so the two must be updated together by hand.
CURRENT = {
    "fable": "claude-fable-5",
    "opus": "claude-opus-4-8",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5-20251001",
}

# Any claude model id that is NOT one of the current ids → likely stale.
MODEL_ID = re.compile(r"claude-[a-z0-9.\-]*\d[a-z0-9.\-]*")
_DATE_SUFFIX = re.compile(r"-\d{8}$")

# A pinned id may appear with or without its trailing snapshot date — e.g.
# "claude-haiku-4-5-20251001" (Claude API ID) and "claude-haiku-4-5" (Claude
# API alias) are both current. Tolerate that pairing only; a bare
# "claude-sonnet-4-6" must NOT slip through as a tolerated variant of
# "claude-sonnet-5" (that was the bug this checker exists to catch).
CURRENT_IDS: set[str] = set()
for _v in CURRENT.values():
    CURRENT_IDS.add(_v)
    _undated = _DATE_SUFFIX.sub("", _v)
    if _undated != _v:
        CURRENT_IDS.add(_undated)


def _suggest(model_id: str) -> str:
    for tier, cur in CURRENT.items():
        if tier in model_id:
            return cur
    return CURRENT["sonnet"]


def scan_text(text: str, *, filename: str = "?") -> list[str]:
    findings: list[str] = []
    for n, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith(("#", "//", "*", "/*")):
            continue
        for m in MODEL_ID.finditer(line):
            mid = m.group(0)
            if mid in CURRENT_IDS:
                continue
            findings.append(
                f"{filename}:{n}: stale model id '{mid}' — current is '{_suggest(mid)}'"
            )
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    all_findings: list[str] = []
    for path in args.files:
        try:
            all_findings.extend(scan_text(Path(path).read_text(encoding="utf-8"), filename=path))
        except FileNotFoundError:
            print(f"error: {path} not found", file=sys.stderr)
            return 2

    for f in all_findings:
        print(f"  ✗ {f}", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"findings": all_findings, "count": len(all_findings)}))
    else:
        print("clean" if not all_findings else f"{len(all_findings)} finding(s)")
    return 1 if all_findings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
