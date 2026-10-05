"""graph_os — the static file a shell script names, despite variables and idioms.

`source "$DIR/lib.sh"`, `python3 "$HOOKS/_helpers/x.py"` and a `for part in a b;
do source "$DIR/$part.sh"; done` loop all name a fixed file once the script-
directory idioms (`$(dirname "$0")`, `$(cd "$(dirname "${BASH_SOURCE[0]}")" &&
pwd)`, `${BASH_SOURCE[0]%/*}`) and the variables built from them are expanded.
Anything still runtime-dependent stays unresolved — never guessed.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

SCRIPT_FILE = "\x00file"
SCRIPT_DIR = "\x00dir"

_SELF_REFERENCES = {"0", "BASH_SOURCE", "BASH_SOURCE[0]"}
_REFERENCE_RE = re.compile(r"\$\{([A-Za-z_]\w*(?:\[0\])?|0)\}|\$([A-Za-z_]\w*|0)")
_DIRNAME_RE = re.compile(r"""^\$\(\s*dirname\s+["']?([^"')\s]+)["']?\s*\)""")
_CD_DIRNAME_RE = re.compile(
    r"""^\$\(\s*cd\s+(?:-P\s+)?["']?\$\(\s*dirname\s+["']?([^"')\s]+)["']?\s*\)["']?"""
    r"""\s*(?:&&|;)\s*pwd(?:\s+-P)?\s*\)"""
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
    """Variables a script assigns to a static path, first assignment wins."""

    def __init__(self) -> None:
        self.variables: dict[str, str] = {}

    def assign(self, name: str, raw_value: str) -> None:
        if name in self.variables:
            return
        value = self.expand(unquote(raw_value))
        if value is not None:
            self.variables[name] = value

    def expand(self, text: str, extra: dict[str, str] | None = None) -> str | None:
        """`text` with every variable and directory idiom expanded, or None if dynamic."""
        known = {**self.variables, **(extra or {})}
        text = _expand_directory_idiom(text, known)
        if text is None:
            return None
        unresolved = False

        def _substitute(match: re.Match[str]) -> str:
            nonlocal unresolved
            name = match.group(1) or match.group(2)
            if name in _SELF_REFERENCES:
                return SCRIPT_FILE
            if name in known:
                return known[name]
            unresolved = True
            return ""

        expanded = _REFERENCE_RE.sub(_substitute, text)
        return None if unresolved or "$(" in expanded or "`" in expanded else expanded


def _expand_directory_idiom(text: str, known: dict[str, str]) -> str | None:
    for pattern in (_CD_DIRNAME_RE, _DIRNAME_RE, _STRIP_LAST_RE):
        match = pattern.match(text)
        if match is None:
            continue
        reference = match.group(1).lstrip("$").strip("{}")
        names_script = reference in _SELF_REFERENCES or known.get(reference) == SCRIPT_FILE
        return SCRIPT_DIR + text[match.end() :] if names_script else None
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
