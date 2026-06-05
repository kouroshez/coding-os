"""Scaffold a production-grade Bash or Python script skeleton.

PURPOSE:      Emit a script that already satisfies the seven non-negotiables
              (strict mode, trap, arg-parsing, progress, parseable result) so
              the agent fills logic instead of re-deriving boilerplate.
INPUT:        --lang bash|python  (required) · --name <snake_case> (required)
              [--root <dir>]      target dir, default `scripts` (consumer-relative)
              [--force]           overwrite an existing file
OUTPUT:       One file: <root>/<name>.{sh,py}. Prints the path on stdout.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent — refuses to overwrite without --force. The emitted
              script is itself lint-clean against lint_script.sh. Spec:
              docs/playbooks/skill-authoring.md § scripts contract.
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

BASH_TEMPLATE = """\
#!/usr/bin/env bash
# {name}.sh — PURPOSE: <one line> / INPUT: <flags> / OUTPUT: <result> / DEPS: <bins> / NOTES: <gotchas>
set -euo pipefail
IFS=$'\\n\\t'

_tmp=""
cleanup() {{ [[ -n "$_tmp" ]] && rm -f "$_tmp"; }}
trap cleanup EXIT

log() {{ printf '%s\\n' "$*" >&2; }}            # narration -> stderr
usage() {{ echo "usage: $0 --input <path> [--dry-run]" >&2; exit 2; }}

input=""
dry_run=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input)   input="${{2:?--input needs a value}}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown arg: $1" >&2; usage ;;
  esac
done
[[ -n "$input" ]] || {{ echo "error: --input is required" >&2; usage; }}

log "[1/1] working on $input (dry_run=$dry_run)..."
# TODO: real work here. Fail-closed: let set -e abort on any error.

printf '{{"ok":true,"input":"%s"}}\\n' "$input"   # result -> stdout, parseable
"""

PYTHON_TEMPLATE = '''\
"""{name}.py — PURPOSE: <one line>.

INPUT:        --input <path> (required) [--dry-run]
OUTPUT:       JSON result on stdout; progress on stderr.
DEPENDENCIES: stdlib only.
NOTES:        Idempotent; fail-closed (non-zero exit on any unmet precondition).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def run(input_path: Path, *, dry_run: bool, log) -> dict:
    log(f"[1/1] working on {{input_path}} (dry_run={{dry_run}})...")
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    # TODO: real work here.
    return {{"ok": True, "input": str(input_path)}}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\\n")[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    def log(msg: str) -> None:
        print(msg, file=sys.stderr)

    result = run(args.input, dry_run=args.dry_run, log=log)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
'''


def build(lang: str, name: str) -> tuple[str, str]:
    if lang == "bash":
        return f"{name}.sh", BASH_TEMPLATE.format(name=name)
    return f"{name}.py", PYTHON_TEMPLATE.format(name=name)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lang", required=True, choices=("bash", "python"))
    parser.add_argument("--name", required=True)
    parser.add_argument("--root", default="scripts", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    if not args.name.replace("_", "").isalnum():
        print(f"error: --name must be snake_case alnum, got {args.name!r}", file=sys.stderr)
        return 2

    filename, content = build(args.lang, args.name)
    args.root.mkdir(parents=True, exist_ok=True)
    target = args.root / filename
    if target.exists() and not args.force:
        print(f"error: {target} exists (use --force)", file=sys.stderr)
        return 1

    target.write_text(content, encoding="utf-8")
    if args.lang == "bash":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(str(target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
