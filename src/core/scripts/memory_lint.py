#!/usr/bin/env python3
"""Structural lint for a project's .agents/memory (`make memory-lint`).

Checks only what cannot false-positive:
  1. every memory is linked exactly once, from MEMORY.md or from an index-*.md
     sub-index that MEMORY.md links, and every index line points at a real file;
  2. every [[wikilink]] resolves to a memory or a sub-index;
  3. no index line states a status — status goes stale, so point at its owner;
  4. sub-indexes are one level deep;
  5. MEMORY.md fits what Claude Code loads: the first 200 lines or 25 KB;
  6. for staged files only: a memory body staged without the index that links
     it, an index line over 200 bytes, and a project/reference memory whose
     `metadata.verified` date is missing or older than 90 days.

Whether a memory's claims are still true stays a human judgement.

usage: python3 memory_lint.py [--root DIR]
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import sys
from pathlib import Path

MEMORY_DIR = ".agents/memory"
MAIN = "MEMORY"
INDEX_PATH = f"{MEMORY_DIR}/{MAIN}.md"
INDEX_MAX_LINES = 200
INDEX_MAX_BYTES = 25_000
INDEX_WARN_RATIO = 0.9
INDEX_LINE_MAX_BYTES = 200
VERIFIED_TYPES = {"project", "reference"}
VERIFY_MAX_AGE_DAYS = 90
RERUN = "make memory-lint"

# The lookbehind keeps hyphenated compounds out: "hook-blocked" names a
# mechanism, while "blocked on the migration" claims a status that goes stale.
STATUS_WORDS = re.compile(
    r"(?<![-\w])(pending|resolved|fixed|done|in progress|blocked|not yet|still|next up|"
    r"upcoming|to be built|shipped|complete[d]?|wip)\b",
    re.IGNORECASE,
)
LINK = re.compile(r"\[[^\]]+\]\(([a-z0-9-]+\.md)\)")
WIKILINK = re.compile(r"\[\[([a-z0-9-]+)\]\]")
SUBINDEX = re.compile(r"^index-[a-z0-9-]+$")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.DOTALL)


def rel(name: str) -> str:
    return f"{MEMORY_DIR}/{name}.md"


def index_entries(text: str) -> list[tuple[int, str, str | None]]:
    entries = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith("- "):
            match = LINK.search(line)
            entries.append((number, line, match.group(1)[:-3] if match else None))
    return entries


def index_size_findings(text: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    measures = (
        (len(text.splitlines()), INDEX_MAX_LINES, "lines"),
        (len(text.encode("utf-8")), INDEX_MAX_BYTES, "bytes"),
    )
    for measured, limit, unit in measures:
        if measured > limit:
            errors.append(
                f"MEMORY.md is {measured:,} {unit}; Claude Code loads only the first {limit:,}, "
                "so the newest index lines never load — shorten the lines or move a domain "
                "into an index-<domain>.md sub-index"
            )
        elif measured > limit * INDEX_WARN_RATIO:
            warnings.append(
                f"MEMORY.md is {measured:,} {unit}, past 90% of the {limit:,} Claude Code "
                "loads; keep each new index line to one short rule"
            )
    return errors, warnings


def long_index_line_warnings(
    index_text: str, staged: list[str], index_path: str = INDEX_PATH
) -> list[str]:
    if index_path not in staged:
        return []
    label = index_path.rsplit("/", 1)[-1]
    warnings = []
    for number, line in enumerate(index_text.splitlines(), 1):
        size = len(line.encode("utf-8"))
        if line.startswith("- ") and size > INDEX_LINE_MAX_BYTES:
            warnings.append(
                f"{label}:{number}: index line is {size} bytes (cap {INDEX_LINE_MAX_BYTES}) "
                "— keep the rule, move the detail into the memory file"
            )
    return warnings


def unreviewed_index_warnings(staged: list[str], owners: dict[str, str]) -> list[str]:
    warnings = []
    for path in sorted(staged):
        name = path.rsplit("/", 1)[-1][:-3]
        if not (path.startswith(f"{MEMORY_DIR}/") and path.endswith(".md")) or name not in owners:
            continue
        owner_path = rel(owners[name])
        if owner_path not in staged:
            warnings.append(
                f"{name}.md is staged without {owner_path.rsplit('/', 1)[-1]} — re-read its "
                "index line; the one-line rule may now contradict the file"
            )
    return warnings


def front_field(body: str, field: str) -> str | None:
    frontmatter = FRONTMATTER.match(body)
    if not frontmatter:
        return None
    match = re.search(rf"^\s*{field}:\s*(\S+)", frontmatter.group(1), re.MULTILINE)
    return match.group(1).strip("\"'") if match else None


def verification_findings(
    name: str, body: str, today: datetime.date
) -> tuple[list[str], list[str]]:
    if front_field(body, "type") not in VERIFIED_TYPES:
        return [], []
    raw = front_field(body, "verified")
    if raw is None:
        return [], [
            f"{name}.md makes live-state claims and has no metadata.verified date — re-check "
            f"them and add `verified: {today.isoformat()}`"
        ]
    try:
        verified = datetime.date.fromisoformat(raw)
    except ValueError:
        return [f"{name}.md: verified {raw!r} is not a YYYY-MM-DD date"], []
    if verified > today:
        return [f"{name}.md: verified {raw} is in the future"], []
    age = (today - verified).days
    if age > VERIFY_MAX_AGE_DAYS:
        return [], [
            f"{name}.md was last verified {age} days ago ({raw}) — re-check its claims "
            "and update the date"
        ]
    return [], []


def link_structure(
    main_text: str, sub_texts: dict[str, str], memories: set[str]
) -> tuple[list[str], dict[str, str]]:
    errors: list[str] = []
    linkers: dict[str, list[str]] = {}
    reachable_subs = set()
    for _, _, target in index_entries(main_text):
        if target is None:
            continue
        if target in sub_texts:
            reachable_subs.add(target)
        elif target in memories:
            linkers.setdefault(target, []).append(MAIN)
        else:
            errors.append(f"MEMORY.md links {target}.md, which does not exist")
    for sub in sorted(sub_texts):
        if sub not in reachable_subs:
            errors.append(f"{sub}.md is not linked from MEMORY.md — nothing in it is ever reached")
            continue
        for _, _, target in index_entries(sub_texts[sub]):
            if target is None:
                continue
            if target in sub_texts:
                errors.append(
                    f"{sub}.md links the sub-index {target}.md — sub-indexes are one level"
                )
            elif target in memories:
                linkers.setdefault(target, []).append(sub)
            else:
                errors.append(f"{sub}.md links {target}.md, which does not exist")
    for name in sorted(memories - set(linkers)):
        errors.append(f"{name}.md exists but no index links it — an unindexed memory never loads")
    for name, where in sorted(linkers.items()):
        if len(where) > 1:
            errors.append(f"{name}.md is linked from {' and '.join(sorted(where))} — keep one line")
    return errors, {name: where[0] for name, where in linkers.items()}


def status_errors(label: str, text: str) -> list[str]:
    errors = []
    for number, line, _ in index_entries(text):
        # Only the rule after the em dash: a memory titled "Feature not done until
        # the client is green" names its subject, it does not claim a status.
        rule = line.split("—", 1)[1] if "—" in line else ""
        hit = STATUS_WORDS.search(rule)
        if hit:
            errors.append(
                f"{label}:{number}: index line states a status ({hit.group(0)!r}) — status goes "
                "stale; point at the task or doc that owns it"
            )
    return errors


def staged_paths(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.split()


def lint(root: Path, staged: list[str], today: datetime.date) -> tuple[list[str], list[str], str]:
    memory_dir = root / MEMORY_DIR
    names = {p.stem for p in memory_dir.glob("*.md") if p.name != f"{MAIN}.md"}
    subs = {n for n in names if SUBINDEX.match(n)}
    memories = names - subs
    texts = {n: (memory_dir / f"{n}.md").read_text(encoding="utf-8") for n in names}
    index_text = (memory_dir / f"{MAIN}.md").read_text(encoding="utf-8")
    sub_texts = {s: texts[s] for s in subs}

    errors, owners = link_structure(index_text, sub_texts, memories)
    errors += status_errors("MEMORY.md", index_text)
    for sub in sorted(sub_texts):
        errors += status_errors(f"{sub}.md", sub_texts[sub])
    for name in sorted(names):
        for target in sorted(set(WIKILINK.findall(texts[name]))):
            if target not in names:
                errors.append(f"{name}.md: [[{target}]] resolves to no memory")

    warnings = unreviewed_index_warnings(staged, owners)
    warnings += long_index_line_warnings(index_text, staged)
    for sub in sorted(sub_texts):
        warnings += long_index_line_warnings(sub_texts[sub], staged, rel(sub))
    for path in staged:
        name = path.rsplit("/", 1)[-1][:-3]
        if path.startswith(f"{MEMORY_DIR}/") and name in memories:
            found_errors, found_warnings = verification_findings(name, texts[name], today)
            errors += found_errors
            warnings += found_warnings
    size_errors, size_warnings = index_size_findings(index_text)
    errors += size_errors
    warnings += size_warnings

    wikilinks = sum(len(set(WIKILINK.findall(texts[n]))) for n in names)
    summary = (
        f"{len(memories)} memories, {len(subs)} sub-indexes, {len(owners)} indexed, "
        f"{wikilinks} wikilinks"
    )
    return errors, warnings, summary


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Structural lint for .agents/memory")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="project root")
    root = parser.parse_args(argv).root.resolve()
    if not (root / MEMORY_DIR).is_dir():
        print(f"[SKIP] memory-lint: no {MEMORY_DIR} directory under {root}")
        return 0
    if not (root / INDEX_PATH).is_file():
        print(f"[FAIL] memory-lint: {INDEX_PATH} is missing; it is the part every session loads")
        return 1

    today = datetime.datetime.now(datetime.timezone.utc).date()
    errors, warnings, summary = lint(root, staged_paths(root), today)
    for warning in warnings:
        print(f"[WARN] {warning}")
    for error in errors:
        print(f"[FAIL] {error}")
    if errors:
        print(f"[FAIL] memory-lint: {summary}; {len(errors)} structural error(s) — rerun: {RERUN}")
        return 1
    print(f"[OK] memory-lint: {summary}; {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
