#!/usr/bin/env python3
"""Rename F1–F11 formula codes to semantic role names across the repo.

USAGE:        Already run on 2026-04 — kept for historical reference.
              Re-running is safe (idempotent regex; renames skip if
              destination exists).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


# Mapping stored via hex codes so the migration patterns themselves
# don't match this file. _D() decodes a hex-encoded ASCII literal.
def _D(hex_str: str) -> str:
    return bytes.fromhex(hex_str).decode("ascii")


# Role codes: hex(F1) = "4631", hex(F2) = "4632", … hex(F11) = "463131"
_CODE_HEX = [
    "4631",
    "4632",
    "4633",
    "4634",
    "4635",
    "4636",
    "4637",
    "4638",
    "4639",
    "463130",
    "463131",
]
_NAMES = [
    "researcher",
    "analyst",
    "architect",
    "documenter",
    "implementer",
    "reviewer",
    "debugger",
    "security_auditor",
    "deployer",
    "observer",
    "refactorer",
]
_PYDANTIC_NAMES = [
    "Researcher",
    "Analyst",
    "Architect",
    "Documenter",
    "Implementer",
    "Reviewer",
    "Debugger",
    "SecurityAuditor",
    "Deployer",
    "Observer",
    "Refactorer",
]
ROLE_MAP: dict[str, str] = dict(zip([_D(h) for h in _CODE_HEX], _NAMES))
PYDANTIC_MAP: dict[str, str] = dict(zip([_D(h) for h in _CODE_HEX], _PYDANTIC_NAMES))

# Compound field names like  hex(F2_decompose) used in Pydantic schemas.
_VERBS = [
    "research",
    "decompose",
    "architect",
    "document",
    "implement",
    "test_review",
    "debug",
    "security",
    "deploy",
    "monitor",
    "refactor",
]
COMPOUND_MAP: dict[str, str] = {
    f"{_D(h)}_{verb}": name for h, verb, name in zip(_CODE_HEX, _VERBS, _NAMES)
}

FILE_RENAMES: dict[str, str] = {}
PATH_FRAGMENT_RENAMES: dict[str, str] = {}
for h, verb, name in zip(_CODE_HEX, _VERBS, _NAMES):
    code = _D(h)
    # roles/F<n>_<name>.yaml → <name>.yaml
    FILE_RENAMES[f"{code}_{name}.yaml"] = f"{name}.yaml"
    # agents/F<n>_<verb>.md → <name>.md
    FILE_RENAMES[f"{code}_{verb}.md"] = f"{name}.md"
    PATH_FRAGMENT_RENAMES[f"agents/{code}_{verb}"] = f"agents/{name}"
    PATH_FRAGMENT_RENAMES[f"roles/{code}_{name}"] = f"roles/{name}"


EXCLUDE_DIR_FRAGMENTS = (
    "/.venv/",
    "/.build/",
    "/.git/",
    "/__pycache__/",
    "/tests/golden/",
    "/.coding-os/",
    "/node_modules/",
    "/.claude/",
    "/.codex/",
    "/coding_os.egg-info/",
    "/dist/",
)

PRESERVE_F_NUMBERING: tuple[str, ...] = (
    "docs/code-os-core-docs/thinkingos-formulas/formulas-en.md",
    # Skip self — script's mapping table can't be rewritten.
    "src/scripts/rename_formulas_to_semantic.py",
)

INCLUDE_SUFFIXES = (".py", ".md", ".yaml", ".yml", ".json", ".sh", ".toml")


def is_excluded(path: Path) -> bool:
    s = "/" + str(path).lstrip("/") + "/"
    return any(frag in s for frag in EXCLUDE_DIR_FRAGMENTS)


def is_preserved(path: Path, root: Path) -> bool:
    rel = str(path.relative_to(root))
    return any(rel == p or rel.endswith("/" + p) for p in PRESERVE_F_NUMBERING)


def build_replacers() -> list[tuple[re.Pattern, str, str]]:
    pats: list[tuple[re.Pattern, str, str]] = []

    # 1. Pydantic class names (longest first so 4631_30 wins over 4631).
    for code in sorted(PYDANTIC_MAP, key=lambda c: -len(c)):
        new = PYDANTIC_MAP[code]
        pats.append((re.compile(rf"\b{code}Output\b"), f"{new}Output", f"{code}Output→{new}Output"))
        pats.append((re.compile(rf"\b{code}Input\b"), f"{new}Input", f"{code}Input→{new}Input"))

    # 2. Path fragments
    for old, new in PATH_FRAGMENT_RENAMES.items():
        pats.append((re.compile(re.escape(old)), new, f"{old}→{new}"))

    # 3. Compound field names (uppercase + lowercase)
    for old in sorted(COMPOUND_MAP, key=lambda c: -len(c)):
        new = COMPOUND_MAP[old]
        pats.append((re.compile(rf"\b{old}\b"), new, f"{old}→{new}"))
        lower = old.lower()
        if lower != old:
            pats.append((re.compile(rf"\b{lower}\b"), new, f"{lower}→{new}"))

    # 4. Quoted F-codes
    for code in sorted(ROLE_MAP, key=lambda c: -len(c)):
        new = ROLE_MAP[code]
        pats.append((re.compile(rf'"({code})"'), f'"{new}"', f'"{code}"→"{new}"'))
        pats.append((re.compile(rf"'({code})'"), f"'{new}'", f"'{code}'→'{new}'"))

    # 5. YAML id field
    for code in sorted(ROLE_MAP, key=lambda c: -len(c)):
        new = ROLE_MAP[code]
        pats.append(
            (re.compile(rf"^(\s*id:\s*){code}\b", re.MULTILINE), rf"\1{new}", f"id:{code}→id:{new}")
        )
        pats.append(
            (
                re.compile(rf"^(\s*formula_ref:\s*){code}\b", re.MULTILINE),
                rf"\1{new}",
                f"formula_ref:{code}→formula_ref:{new}",
            )
        )

    return pats


def rewrite_file(path: Path, replacers, dry_run: bool):
    try:
        original = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return False, []
    text = original
    hits: list[str] = []
    for pat, repl, label in replacers:
        new_text, n = pat.subn(repl, text)
        if n:
            hits.append(f"  {n}× {label}")
        text = new_text
    if text != original:
        if not dry_run:
            path.write_text(text, encoding="utf-8")
        return True, hits
    return False, hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent.parent)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = args.root.resolve()
    print(f"Repo root: {root}")
    print(f"Dry run:   {args.dry_run}")

    replacers = build_replacers()

    rewritten = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if is_excluded(path):
            continue
        if path.suffix not in INCLUDE_SUFFIXES:
            continue
        if is_preserved(path, root):
            continue
        changed, hits = rewrite_file(path, replacers, args.dry_run)
        if changed:
            rewritten += 1
            rel = path.relative_to(root)
            print(f"\n[rewrite] {rel}")
            for h in hits:
                print(h)

    renamed = 0
    for old_basename, new_basename in FILE_RENAMES.items():
        for old_path in root.rglob(old_basename):
            if is_excluded(old_path):
                continue
            new_path = old_path.parent / new_basename
            if new_path.exists():
                continue
            print(f"\n[rename] {old_path.relative_to(root)} → {new_basename}")
            if not args.dry_run:
                old_path.rename(new_path)
            renamed += 1

    print(f"\nDone. {rewritten} file(s) rewritten, {renamed} file(s) renamed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
