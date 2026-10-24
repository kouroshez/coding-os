"""Scaffold a docs/ markdown file with the canonical coding-os header.

PURPOSE:      Emit a doc that already carries the machine-readable header +
              Purpose/Read-when/Skip-when/Read-next + Nav, so regen_doc_index
              indexes it and the renderer finds it. Writer fills the body.
INPUT:        --layer <index|playbook|spec|policy|reference|adr|task> (required)
              --domain <BACKEND|FRONTEND|DOCS|INFRA|META|...> (required)
              --title  "<human title>" (required)
              [--root docs/<dir>]  target dir (default: docs)
              [--ssot true|false]  default true
              [--date YYYY-MM-DD]  header date (default: today, UTC)
              [--force]
OUTPUT:       <root>/<slug>.md. Prints the path on stdout.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent (refuses overwrite without --force). Layer is
              validated against docs-system.md's taxonomy. Spec:
              docs/playbooks/skill-authoring.md + docs/governance/docs-system.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LAYERS = ("index", "playbook", "spec", "policy", "reference", "adr", "task")


def slugify(title: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s or "untitled"


def render(layer: str, domain: str, title: str, ssot: str, date: str) -> str:
    return (
        f"<!-- domain:{domain} | layer:{layer} | ssot:{ssot} | updated:{date} -->\n"
        f"# {title}\n\n"
        "Purpose: <one line — what this doc is for>.\n"
        "Read when: <the trigger situation>.\n"
        "Skip when: <when another doc is the right one>.\n"
        "Read next: <[related](related.md)>\n\n"
        "> Nav: [Section Index](./00-index.md) | [Docs Index](../00-index.md)\n\n"
        "## <First section — one idea>\n\n"
        "<body>\n"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--layer", required=True, choices=LAYERS)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--root", default="docs", type=Path)
    parser.add_argument("--ssot", default="true", choices=("true", "false"))
    parser.add_argument("--date", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    date = args.date or datetime.now(timezone.utc).date().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print(f"error: --date must be YYYY-MM-DD, got {date!r}", file=sys.stderr)
        return 2

    args.root.mkdir(parents=True, exist_ok=True)
    target = args.root / f"{slugify(args.title)}.md"
    if target.exists() and not args.force:
        print(f"error: {target} exists (use --force)", file=sys.stderr)
        return 1

    target.write_text(
        render(args.layer, args.domain.upper(), args.title, args.ssot, date),
        encoding="utf-8",
    )
    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
