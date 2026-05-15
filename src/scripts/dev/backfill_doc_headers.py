"""Backfill canonical doc headers (frontmatter + opening block) into docs/**.

The doc header system (Phase O.4) expects every `docs/**/*.md` to start with:

    <!-- domain:DOCS | layer:policy | ssot:true | updated:YYYY-MM-DD -->
    # <H1 Title>

    Purpose: <one line>
    Read when: <triggers>
    Skip when: <when this doc is the wrong choice>
    Read next: [foo](foo.md), [bar](bar.md)

This script finds docs missing that header, infers reasonable defaults from
path/content, and either prints a diff (default: dry-run) or writes the
backfilled version (`--apply`).

It also normalises legacy YAML frontmatter (`---\\nkey: value\\n---`) into the
canonical HTML-comment form so `parse_doc_header` (core/thinking_os/tools/docs.py)
can index the file.

Usage:
    python scripts/dev/backfill_doc_headers.py            # dry-run, all docs
    python scripts/dev/backfill_doc_headers.py --apply    # write changes
    python scripts/dev/backfill_doc_headers.py docs/engineering --apply
    python scripts/dev/backfill_doc_headers.py --only-missing  # skip YAML conv

Exit codes:
    0  — nothing to do, or all writes succeeded
    1  — at least one file would change (dry-run signal for CI)
    2  — fatal error (bad path, IO failure)
"""
from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS_ROOT = ROOT / "docs"

_VALID_FRONTMATTER_KEYS = {
    "domain", "layer", "ssot", "updated", "tokens", "reads", "priority",
}

_HTML_FM_RE = re.compile(r"^\s*<!--\s*(?P<body>.+?)\s*-->", re.DOTALL)
_YAML_FM_RE = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
_OPENING_PURPOSE_RE = re.compile(r"^Purpose:\s*", re.M)

_PATH_DOMAIN: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"docs/governance/"), "DOCS"),
    (re.compile(r"docs/engineering/"), "CORE"),
    (re.compile(r"docs/architecture"), "CORE"),
    (re.compile(r"docs/adapters/"), "CORE"),
    (re.compile(r"docs/playbooks/"), "DOCS"),
    (re.compile(r"docs/api-contracts/"), "CORE"),
    (re.compile(r"docs/code-os-core-docs/scrumban/"), "DOCS"),
    (re.compile(r"docs/code-os-core-docs/thinkingos-formulas/"), "CORE"),
    (re.compile(r"docs/code-os-core-docs/"), "DOCS"),
    (re.compile(r"docs/tasks/"), "DOCS"),
    (re.compile(r"docs/postmortems/"), "DOCS"),
]

_PATH_LAYER: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"docs/governance/"), "policy"),
    (re.compile(r"docs/playbooks/"), "playbook"),
    (re.compile(r"docs/api-contracts/"), "spec"),
    (re.compile(r"docs/postmortems/"), "postmortem"),
    (re.compile(r"docs/architecture"), "spec"),
    (re.compile(r"docs/adapters/"), "engineering"),
    (re.compile(r"docs/engineering/"), "engineering"),
    (re.compile(r"docs/tasks/"), "task"),
]


@dataclass
class HeaderPlan:
    path: Path
    had_html_fm: bool
    had_yaml_fm: bool
    had_opening: bool
    new_text: str
    reason: str


def _infer_domain(rel: str) -> str:
    for pattern, value in _PATH_DOMAIN:
        if pattern.search(rel):
            return value
    return "DOCS"


def _infer_layer(rel: str) -> str:
    for pattern, value in _PATH_LAYER:
        if pattern.search(rel):
            return value
    return "engineering"


def _today_iso() -> str:
    return _dt.date.today().isoformat()


def _parse_yaml_frontmatter(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if line.startswith((" ", "\t", "-")):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value:
            continue
        out[key] = value
    return out


def _render_html_frontmatter(fm: dict[str, str]) -> str:
    parts = [f"{k}:{v}" for k, v in fm.items()]
    return "<!-- " + " | ".join(parts) + " -->"


def _ensure_required(fm: dict[str, str], rel: str) -> dict[str, str]:
    fm.setdefault("domain", _infer_domain(rel))
    fm.setdefault("layer", _infer_layer(rel))
    fm.setdefault("ssot", "false")
    fm.setdefault("updated", _today_iso())
    return {k: v for k, v in fm.items() if k in _VALID_FRONTMATTER_KEYS}


def _extract_h1(text: str) -> tuple[str | None, int]:
    match = _H1_RE.search(text)
    if not match:
        return None, -1
    return match.group(1).strip(), match.start()


def _has_opening_block(text: str) -> bool:
    return bool(_OPENING_PURPOSE_RE.search(text))


def _build_opening_stub(title: str) -> str:
    return (
        f"Purpose: TODO — one-line statement of why {title!r} exists.\n"
        f"Read when: TODO — concrete trigger that sends an agent here.\n"
        f"Skip when: TODO — when another doc is the right choice instead.\n"
        f"Read next: TODO — 1-3 follow-up doc links.\n"
    )


def _plan_backfill(path: Path, *, only_missing: bool) -> HeaderPlan | None:
    rel = str(path.relative_to(ROOT))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"FAIL: cannot read {rel}: {exc}", file=sys.stderr)
        return None

    html_match = _HTML_FM_RE.match(text)
    yaml_match = _YAML_FM_RE.match(text)

    fm: dict[str, str] = {}
    body = text
    had_html = bool(html_match)
    had_yaml = bool(yaml_match)

    if had_html:
        for fragment in html_match.group("body").split("|"):
            if ":" not in fragment:
                continue
            k, _, v = fragment.partition(":")
            fm[k.strip()] = v.strip()
        body = text[html_match.end():].lstrip("\n")
    elif had_yaml:
        fm = _parse_yaml_frontmatter(yaml_match.group("body"))
        body = text[yaml_match.end():]

    if had_html and only_missing:
        return None

    fm = _ensure_required(fm, rel)
    new_fm_line = _render_html_frontmatter(fm)

    title, h1_pos = _extract_h1(body)
    needs_opening = title is not None and not _has_opening_block(body)

    if needs_opening:
        h1_line_end = body.find("\n", h1_pos)
        stub = _build_opening_stub(title or "this document")
        if h1_line_end == -1:
            new_body = body + "\n\n" + stub
        else:
            head = body[: h1_line_end + 1]
            tail = body[h1_line_end + 1 :].lstrip("\n")
            new_body = head + "\n" + stub + "\n" + tail
    else:
        new_body = body

    new_text = new_fm_line + "\n" + new_body
    if not new_text.endswith("\n"):
        new_text += "\n"

    if new_text == text:
        return None

    reason_bits = []
    if not had_html and had_yaml:
        reason_bits.append("yaml→html frontmatter")
    elif not had_html:
        reason_bits.append("missing frontmatter")
    else:
        reason_bits.append("frontmatter normalised")
    if needs_opening:
        reason_bits.append("opening block stub")
    reason = ", ".join(reason_bits)

    return HeaderPlan(
        path=path,
        had_html_fm=had_html,
        had_yaml_fm=had_yaml,
        had_opening=not needs_opening,
        new_text=new_text,
        reason=reason,
    )


def _iter_targets(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.is_file() and root.suffix == ".md":
            files.append(root)
            continue
        if not root.is_dir():
            print(f"WARN: skipping non-existent path {root}", file=sys.stderr)
            continue
        for path in sorted(root.rglob("*.md")):
            if any(part in {".venv", "node_modules", ".coding-os"} for part in path.parts):
                continue
            files.append(path)
    return files


def _short(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill doc headers in docs/**")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional file or directory roots (default: docs/)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to disk (default: dry-run, exit 1 if changes pending).",
    )
    parser.add_argument(
        "--only-missing",
        action="store_true",
        help="Skip docs that already have HTML-comment frontmatter (don't re-normalise).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print only summary, not per-file plan.",
    )
    args = parser.parse_args(argv)

    roots = [Path(p).resolve() for p in args.paths] if args.paths else [DOCS_ROOT]
    targets = _iter_targets(roots)
    if not targets:
        print("no markdown targets found", file=sys.stderr)
        return 2

    plans: list[HeaderPlan] = []
    for path in targets:
        plan = _plan_backfill(path, only_missing=args.only_missing)
        if plan is not None:
            plans.append(plan)

    if not plans:
        print(f"OK  : {len(targets)} docs scanned, 0 changes needed")
        return 0

    if not args.quiet:
        for plan in plans:
            print(f"PLAN: {_short(plan.path)}  ({plan.reason})")

    if not args.apply:
        print(
            f"\nDRY-RUN: {len(plans)}/{len(targets)} docs would change. "
            f"Re-run with --apply to write."
        )
        return 1

    written = 0
    for plan in plans:
        try:
            plan.path.write_text(plan.new_text, encoding="utf-8")
            written += 1
        except OSError as exc:
            print(f"FAIL: cannot write {_short(plan.path)}: {exc}", file=sys.stderr)
    print(f"\nWROTE: {written}/{len(plans)} docs updated ({len(targets)} scanned)")
    return 0 if written == len(plans) else 2


if __name__ == "__main__":
    sys.exit(main())
