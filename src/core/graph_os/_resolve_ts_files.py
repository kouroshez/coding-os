"""graph_os — the file probing TS/JS resolution stands on.

A candidate path becomes a repo file through extension, index and React Native
platform-variant probing, and the ESM `./x.js` → `x.ts` / `x.d.ts` convention;
`platform_twins` names the other variants of a file Metro picks per platform.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path, PurePosixPath
from typing import Any

from .toolchain import strip_json_comments

logger = logging.getLogger("graph_os.resolve_ts")

SOURCE_EXTENSIONS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")
# Metro resolves `./Button` to `Button.ios.tsx` / `Button.native.tsx` when no
# plain `Button.tsx` exists.
PLATFORM_VARIANTS = ("native", "ios", "android", "web")
PLATFORM_EXTENSIONS = (".tsx", ".ts", ".jsx", ".js")
# An ESM TypeScript import names the emitted `.js`; the source is the `.ts`.
SOURCE_FOR_EMITTED = {
    ".js": (".ts", ".tsx", ".d.ts"),
    ".jsx": (".tsx",),
    ".mjs": (".mts", ".d.mts"),
    ".cjs": (".cts", ".d.cts"),
}
_LISTING_CACHE: dict[tuple[str, int], frozenset[str]] = {}


def _probe(root: Path, base: str) -> str | None:
    for candidate in _candidates(base):
        if (root / candidate).is_file():
            return candidate
    return None


def _candidates(base: str) -> list[str]:
    suffix = PurePosixPath(base).suffix
    stem = base[: -len(suffix)] if suffix in SOURCE_FOR_EMITTED else None
    sources = [stem + ext for ext in SOURCE_FOR_EMITTED.get(suffix, ())] if stem else []
    plain = [base, *(base + ext for ext in SOURCE_EXTENSIONS)]
    platform = [
        f"{base}.{variant}{ext}" for variant in PLATFORM_VARIANTS for ext in PLATFORM_EXTENSIONS
    ]
    index = [f"{base}/index{ext}" for ext in SOURCE_EXTENSIONS]
    return [*sources, *plain, *platform, *index]


def _join(directory: str, relative: str) -> str | None:
    parts: list[str] = []
    for part in f"{directory}/{relative}".split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def platform_twins(root: Path, path: str) -> list[str]:
    """The other React Native platform variants of `path`: `Map.ios.tsx` → `Map.android.tsx`."""
    folder, _, name = path.rpartition("/")
    extension = next((ext for ext in PLATFORM_EXTENSIONS if name.endswith(ext)), "")
    stem = name[: -len(extension)] if extension else ""
    base, _, variant = stem.rpartition(".")
    stem = base if variant in PLATFORM_VARIANTS else stem
    listing = _listing(root / folder) if stem else frozenset()
    twins = [
        candidate
        for candidate in (
            *(
                f"{stem}.{variant}{ext}"
                for variant in PLATFORM_VARIANTS
                for ext in PLATFORM_EXTENSIONS
            ),
            *(f"{stem}{ext}" for ext in PLATFORM_EXTENSIONS),
        )
        if candidate in listing and candidate != name
    ]
    if not any(_variant_of(candidate) for candidate in [name, *twins]):
        return []
    return [f"{folder}/{twin}" if folder else twin for twin in twins]


def _variant_of(name: str) -> bool:
    stem = name.rpartition(".")[0]
    return stem.rpartition(".")[2] in PLATFORM_VARIANTS


def _listing(folder: Path) -> frozenset[str]:
    key = (str(folder), _mtime(folder))
    if key not in _LISTING_CACHE:
        try:
            _LISTING_CACHE[key] = frozenset(entry.name for entry in folder.iterdir())
        except OSError:
            _LISTING_CACHE[key] = frozenset()
    return _LISTING_CACHE[key]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(strip_json_comments(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        logger.debug("unreadable JSON config %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0
