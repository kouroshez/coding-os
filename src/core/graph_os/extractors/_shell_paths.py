"""graph_os — the static file a shell script names, despite variables and idioms.

`source "$DIR/lib.sh"`, `python3 "$HOOKS/_helpers/x.py"` and a `for part in a b;
do source "$DIR/$part.sh"; done` loop all name a fixed file once the script-
directory idioms (`$(dirname "$0")`, `$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.."
&>/dev/null && pwd)`, `${BASH_SOURCE[0]%/*}`, with `readlink -f` / `realpath` or
backticks around them, or as a `${DIR:-…}` default) and the variables built from
them are expanded. A variable assigned more than once keeps every static value,
and each reading is tried. Anything still runtime-dependent stays unresolved —
never guessed.
"""

from __future__ import annotations

import re
from itertools import islice, product
from pathlib import Path, PurePosixPath

SCRIPT_FILE = "\x00file"
SCRIPT_DIR = "\x00dir"

MAX_READINGS = 8

_SELF_REFERENCES = {"0", "BASH_SOURCE", "BASH_SOURCE[0]"}
_REFERENCE_RE = re.compile(r"\$\{([A-Za-z_]\w*(?:\[0\])?|0)\}|\$([A-Za-z_]\w*|0)")
_DEFAULT_RE = re.compile(r"\$\{([A-Za-z_]\w*):?[-=]")
_BACKTICK_RE = re.compile(r"`([^`]*)`")
# `$(readlink -f "$0")` / `$(realpath "${BASH_SOURCE[0]}")` name the script itself.
_RESOLVED_SELF_RE = re.compile(
    r"""\$\(\s*(?:g?readlink\s+-[A-Za-z]+|realpath(?:\s+-[A-Za-z-]+)*)\s+["']?"""
    r"""(\$\{?(?:0|BASH_SOURCE(?:\[0\])?)\}?)["']?\s*\)"""
)
_DIRNAME = r"""\$\(\s*dirname\s+(?:--\s+)?["']?([^"')\s]+)["']?\s*\)"""
_DIRNAME_RE = re.compile(rf"^{_DIRNAME}")
_CD_DIRNAME_RE = re.compile(
    rf"""^\$\(\s*cd\s+(?:-[PL]\s+|--\s+)*["']?{_DIRNAME}(/[^"'\s;&)]*)?["']?"""
    r"""(?:\s*(?:&>|\d?>{1,2})\s*/dev/null|\s*\d?>&\d)*\s*(?:&&|;)\s*pwd(?:\s+-[PL])?\s*\)"""
)
_STRIP_LAST_RE = re.compile(r"""^\$\{(BASH_SOURCE(?:\[0\])?|0|[A-Za-z_]\w*)%/\*\}""")
_DIRECTIVE_RE = re.compile(r"#\s*shellcheck\s+source=(\S+)")


def unquote(text: str) -> str:
    """Strip one matching pair of outer quotes (`"x.sh"` / `'x.sh'`)."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


class ShellScope:
    """Variables a script assigns to a static path, each with every static value it gets."""

    def __init__(self) -> None:
        self.variables: dict[str, list[str]] = {}

    def assign(self, name: str, raw_value: str) -> None:
        readings = self.expand_all(unquote(raw_value))
        values = self.variables.setdefault(name, [])
        values.extend(value for value in readings if value not in values)
        del values[MAX_READINGS:]

    def expand_all(self, text: str, extra: dict[str, str] | None = None) -> list[str]:
        """Every static reading of `text`, one per combination of the values it references."""
        known = {name: values for name, values in self.variables.items() if values}
        known.update({name: [value] for name, value in (extra or {}).items()})
        names = sorted(
            {match.group(1) or match.group(2) for match in _REFERENCE_RE.finditer(text)}
            | set(_DEFAULT_RE.findall(text))
        )
        names = [name for name in names if name in known]
        readings: list[str] = []
        for values in islice(product(*(known[name] for name in names)), MAX_READINGS):
            expanded = _expand(text, dict(zip(names, values, strict=True)))
            if expanded is not None and expanded not in readings:
                readings.append(expanded)
        return readings


def _expand(text: str, binding: dict[str, str]) -> str | None:
    text = _apply_defaults(_RESOLVED_SELF_RE.sub(r"\1", _BACKTICK_RE.sub(r"$(\1)", text)), binding)
    idiom_free = _expand_directory_idiom(text, binding)
    if idiom_free is None:
        return None
    unresolved = False

    def _substitute(match: re.Match[str]) -> str:
        nonlocal unresolved
        name = match.group(1) or match.group(2)
        if name in _SELF_REFERENCES:
            return SCRIPT_FILE
        if name in binding:
            return binding[name]
        unresolved = True
        return ""

    expanded = _REFERENCE_RE.sub(_substitute, idiom_free)
    return None if unresolved or "$(" in expanded or "`" in expanded else expanded


def _apply_defaults(text: str, binding: dict[str, str]) -> str:
    # `${DIR:-word}` reads as DIR when the script assigned it, else as its default.
    parts: list[str] = []
    index = 0
    while (match := _DEFAULT_RE.search(text, index)) is not None:
        end = _closing_brace(text, match.end())
        if end is None:
            break
        name = match.group(1)
        parts += [text[index : match.start()], binding.get(name, text[match.end() : end])]
        index = end + 1
    return "".join(parts) + text[index:]


def _closing_brace(text: str, start: int) -> int | None:
    depth = 0
    for position in range(start, len(text)):
        if text[position] in "({":
            depth += 1
        elif text[position] == "}" and depth == 0:
            return position
        elif text[position] in ")}":
            depth -= 1
    return None


def _expand_directory_idiom(text: str, known: dict[str, str]) -> str | None:
    for pattern in (_CD_DIRNAME_RE, _DIRNAME_RE, _STRIP_LAST_RE):
        match = pattern.match(text)
        if match is None:
            continue
        reference = match.group(1).lstrip("$").strip("{}")
        names_script = reference in _SELF_REFERENCES or known.get(reference) == SCRIPT_FILE
        suffix = (match.group(2) or "") if pattern.groups > 1 else ""
        return SCRIPT_DIR + suffix + text[match.end() :] if names_script else None
    return text


def directive_paths(comment_text: str) -> list[str]:
    """Paths a `# shellcheck source=` directive names (`/dev/null` excluded)."""
    return [path for path in _DIRECTIVE_RE.findall(comment_text) if path != "/dev/null"]


def resolve(script: str, expanded: str, root: Path | None) -> tuple[str, bool] | None:
    """Repo-relative file an expanded path names, and whether it is script-dir anchored.

    A bare relative path runs from the caller's working directory, which for a
    repo's scripts and hooks is usually the root, so it may name a file next to
    the script or one at the root; the first that exists wins. Without a repo
    root to check against, the script-dir reading is kept.
    """
    anchored = expanded.startswith(SCRIPT_DIR)
    relative = expanded[len(SCRIPT_DIR) :].lstrip("/") if anchored else expanded
    if not relative or "\x00" in relative or relative.startswith(("/", "~")):
        return None
    script_dir = str(PurePosixPath(script).parent)
    candidates = [_join(script_dir, relative)]
    if not anchored:
        candidates.append(_join("", relative))
    existing = [
        path for path in candidates if path and root is not None and (root / path).is_file()
    ]
    if existing:
        return existing[0], anchored
    if root is None and candidates[0]:
        return candidates[0], anchored
    return None


def _join(directory: str, relative: str) -> str:
    parts: list[str] = []
    for part in f"{directory}/{relative}".split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return ""
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)
