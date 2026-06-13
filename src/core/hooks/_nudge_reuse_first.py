"""Reuse-first placement nudge delegate for `nudge-reuse-first.sh`.

Heuristic: when a file under ``src/services/<svc>/`` defines a symbol that is
also defined in a *different* same-language service, suggest promoting it to
``src/shared/<lang>/``. Advisory only — prints at most one suggestion (or
nothing) and never blocks. Bounded scan so the PostToolUse hook stays fast.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# suffix -> (shared language dir, symbol-definition line patterns)
_LANG: dict[str, tuple[str, tuple[str, ...]]] = {
    ".py": (
        "py",
        (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w+)", r"^\s*class\s+([A-Za-z_]\w+)"),
    ),
    ".go": (
        "go",
        (r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w+)", r"^\s*type\s+([A-Za-z_]\w+)\s"),
    ),
    ".ts": (
        "ts",
        (
            r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_]\w+)",
            r"^\s*export\s+(?:abstract\s+)?class\s+([A-Za-z_]\w+)",
            r"^\s*export\s+const\s+([A-Za-z_]\w+)",
        ),
    ),
}
_LANG[".tsx"] = _LANG[".ts"]
_LANG[".js"] = _LANG[".ts"]
_LANG[".jsx"] = _LANG[".ts"]

MAX_SYMBOLS = 10
MAX_SCAN_FILES = 400
# Short names (New, run, init) collide constantly across services and would
# produce noise, so only nudge on names distinctive enough to be real reuse.
MIN_SYMBOL_LENGTH = 4


def _service_of(rel_path: str) -> str | None:
    parts = rel_path.split("/")
    if len(parts) >= 3 and parts[0] == "src" and parts[1] == "services":
        return parts[2]
    return None


def _defined_symbols(text: str, patterns: tuple[str, ...]) -> list[str]:
    compiled = [re.compile(p) for p in patterns]
    out: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        for rx in compiled:
            match = rx.match(line)
            if not match:
                continue
            name = match.group(1)
            if len(name) < MIN_SYMBOL_LENGTH or name.startswith("_") or name in seen:
                continue
            seen.add(name)
            out.append(name)
        if len(out) >= MAX_SYMBOLS:
            break
    return out


def _first_duplicate(
    services_root: Path,
    own_service: str,
    suffix: str,
    symbol_set: set[str],
    patterns: tuple[str, ...],
    project_root: Path,
) -> tuple[str, str] | None:
    compiled = [re.compile(p) for p in patterns]
    scanned = 0
    for other in sorted(services_root.iterdir()):
        if not other.is_dir() or other.name == own_service:
            continue
        for path in other.rglob(f"*{suffix}"):
            if scanned >= MAX_SCAN_FILES:
                return None
            scanned += 1
            try:
                other_text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in other_text.splitlines():
                for rx in compiled:
                    match = rx.match(line)
                    if match and match.group(1) in symbol_set:
                        return match.group(1), path.relative_to(project_root).as_posix()
    return None


def main() -> int:
    if len(sys.argv) < 3:
        return 0
    rel_path = sys.argv[1].strip()
    project_root = Path(sys.argv[2])

    own_service = _service_of(rel_path)
    if own_service is None:
        return 0
    suffix = Path(rel_path).suffix
    lang = _LANG.get(suffix)
    if lang is None:
        return 0
    lang_dir, patterns = lang

    try:
        text = (project_root / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return 0

    symbols = _defined_symbols(text, patterns)
    if not symbols:
        return 0

    services_root = project_root / "src" / "services"
    if not services_root.is_dir():
        return 0

    hit = _first_duplicate(
        services_root, own_service, suffix, set(symbols), patterns, project_root
    )
    if hit is None:
        return 0

    symbol, other_path = hit
    print(
        f"[reuse-first] '{symbol}' is defined in both src/services/{own_service}/ "
        f"and {other_path} — consider promoting it to src/shared/{lang_dir}/ "
        f"(project-anatomy.md: same-language reuse lives in shared/, not duplicated per service)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
