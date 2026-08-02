#!/usr/bin/env python3
"""Flag scaffold docs that name a module-owned slash command without a matching
module tag, so `| module:X` / `<!-- if-module:X -->` coverage tracks the
subsystem registry automatically instead of by hand (TASK-815 / audit F-H).

A mention of `/<command>` owned by a disable-able module must sit inside an
`<!-- if-module:<module> -->` block OR live in a file tagged `| module:<module>`
in its header — otherwise the reference is stale when that module is disabled.
Scope is deliberately slash-commands only (unambiguous, low false-positive); the
noisier tool-family prefixes are left to hand review.

USAGE: python3 audit_scaffold_module_tags.py [--quiet]
EXIT:  0 = clean, 1 = violations found (printed to stderr).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[3]
_SUBSYSTEMS = _ROOT / "src" / "core" / "subsystems.yaml"
_SCAFFOLD_GLOB = "src/templates/*/scaffold/docs"

_FILE_TAG_RE = re.compile(r"\|\s*module:([a-z][a-z0-9_-]*)")
_IF_MODULE_RE = re.compile(r"^<!--\s*if-module:([a-z0-9_,-]+)\s*-->\s*$")
_ENDIF_RE = re.compile(r"^<!--\s*end-if\s*-->\s*$")


def _command_owners() -> dict[str, str]:
    data = yaml.safe_load(_SUBSYSTEMS.read_text(encoding="utf-8")) or {}
    owners: dict[str, str] = {}
    for module in data.get("modules") or []:
        if module.get("kernel") or module.get("hidden"):
            continue
        for command in module.get("commands") or []:
            owners[str(command)] = str(module["id"])
    return owners


def _audit_doc(path: Path, owners: dict[str, str], cmd_res: dict[str, re.Pattern]) -> list[str]:
    lines = path.read_text(encoding="utf-8").split("\n")
    file_tag = None
    if lines and lines[0].lstrip().startswith("<!--"):
        m = _FILE_TAG_RE.search(lines[0])
        if m:
            file_tag = m.group(1)
    block_modules: set[str] = set()
    violations: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        opener = _IF_MODULE_RE.match(line.strip())
        if opener:
            block_modules = {x for x in opener.group(1).split(",") if x}
            continue
        if _ENDIF_RE.match(line.strip()):
            block_modules = set()
            continue
        for command, module_id in owners.items():
            if (
                cmd_res[command].search(line)
                and file_tag != module_id
                and module_id not in block_modules
            ):
                violations.append(
                    f"{path.relative_to(_ROOT)}:{lineno}: /{command} (module '{module_id}') "
                    "is not under an if-module block or a file module tag"
                )
    return violations


def collect_violations() -> list[str]:
    owners = _command_owners()
    if not owners:
        return []
    # A slash command is preceded by start / whitespace / backtick — never a word
    # char (so "feature/task" is not mistaken for the `/task` command) — and not
    # followed by a word char, slash, or hyphen ("/board_os", "/tasks" excluded).
    cmd_res = {c: re.compile(r"(?<![\w])/" + re.escape(c) + r"(?![\w/-])") for c in owners}
    violations: list[str] = []
    for scaffold_docs in _ROOT.glob(_SCAFFOLD_GLOB):
        for doc in scaffold_docs.rglob("*.md"):
            violations.extend(_audit_doc(doc, owners, cmd_res))
    return violations


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    violations = collect_violations()
    if violations:
        sys.stderr.write("scaffold module-tag audit — FAIL:\n")
        for v in violations:
            sys.stderr.write(f"  {v}\n")
        sys.stderr.write(
            "Fix: wrap the mention in <!-- if-module:<id> --> ... <!-- end-if --> "
            "or add a `| module:<id>` header tag.\n"
        )
        return 1
    if not quiet:
        print("scaffold module-tag audit: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
