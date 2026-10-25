"""core.web.routes.memory — read-only view of the project's `.agents/memory/` files.

Parses and lints with `src/core/scripts/memory_lint.py`, the module behind
`make memory-lint`, so the Hub and the gate agree on what is indexed or broken.
"""

from __future__ import annotations

import datetime
import importlib.util
import logging
import re
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from fastapi import APIRouter

_CORE_DIR = Path(__file__).resolve().parents[2]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

logger = logging.getLogger("coding_os.web.memory")

router = APIRouter(tags=["memory"])

_ENTRY = re.compile(r"^- \[([^\]]+)\]\([a-z0-9-]+\.md\)\s*[—-]?\s*(.*)$")
_HEADING = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@lru_cache(maxsize=1)
def _memory_lint() -> ModuleType:
    script = _CORE_DIR / "scripts" / "memory_lint.py"
    spec = importlib.util.spec_from_file_location("memory_lint", script)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _entries(lint: ModuleType, text: str) -> list[dict]:
    entries = []
    for line_number, line, slug in lint.index_entries(text):
        match = _ENTRY.match(line)
        title, rule = (match.group(1), match.group(2)) if match else (line[2:], "")
        entries.append({"line": line_number, "slug": slug, "title": title, "rule": rule})
    return entries


def _index(lint: ModuleType, name: str, text: str) -> dict:
    heading = _HEADING.search(text)
    return {
        "name": name,
        "file": f"{name}.md",
        "title": heading.group(1).strip() if heading else name,
        "entries": _entries(lint, text),
    }


def _memory(lint: ModuleType, slug: str, text: str) -> dict:
    frontmatter = lint.FRONTMATTER.match(text)
    return {
        "slug": slug,
        "name": lint.front_field(text, "name"),
        "description": _description(frontmatter.group(1) if frontmatter else ""),
        "type": lint.front_field(text, "type"),
        "verified": lint.front_field(text, "verified"),
        "links": sorted(set(lint.WIKILINK.findall(text))),
        "body": text[frontmatter.end() :].strip() if frontmatter else text.strip(),
    }


def _description(frontmatter: str) -> str | None:
    match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None


def memory_payload(root: Path) -> dict:
    lint = _memory_lint()
    memory_dir = root / lint.MEMORY_DIR
    index_path = memory_dir / f"{lint.MAIN}.md"
    if not index_path.is_file():
        return {"present": False, "dir": lint.MEMORY_DIR}

    index_text = index_path.read_text(encoding="utf-8")
    texts = {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(memory_dir.glob("*.md"))
        if path.name != index_path.name
    }
    sub_names = sorted(name for name in texts if lint.SUBINDEX.match(name))
    root_index = _index(lint, lint.MAIN, index_text)
    pointers = {entry["slug"]: entry for entry in root_index["entries"]}
    indexes = [root_index]
    for name in sub_names:
        sub = _index(lint, name, texts[name])
        pointer = pointers.get(name)
        sub["pointer"] = pointer and {"title": pointer["title"], "rule": pointer["rule"]}
        indexes.append(sub)

    today = datetime.datetime.now(datetime.timezone.utc).date()
    errors, warnings, summary = lint.lint(root, [], today)
    return {
        "present": True,
        "dir": lint.MEMORY_DIR,
        "budget": {
            "lines": len(index_text.splitlines()),
            "bytes": len(index_text.encode("utf-8")),
            "max_lines": lint.INDEX_MAX_LINES,
            "max_bytes": lint.INDEX_MAX_BYTES,
        },
        "indexes": indexes,
        "memories": [
            _memory(lint, slug, text) for slug, text in texts.items() if slug not in sub_names
        ],
        "lint": {"errors": errors, "warnings": warnings, "summary": summary},
    }


@router.get("/api/memory")
def get_memory() -> dict:
    from web._project_context import current_project_root  # type: ignore

    return memory_payload(current_project_root())
