"""graph_os — a same-length TypeScript view of an `.astro` component.

An Astro file is a `---` frontmatter fence of TypeScript, a template, and
optional `<script>` / `<style>` blocks. code_ts reads the masked view: the
frontmatter and each processable `<script>` body are kept, every other
character becomes a space and every newline survives, so the lines and columns
code_ts reports are the `.astro` file's own.
"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^---[ \t]*$", re.MULTILINE)
_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script\s*>", re.IGNORECASE)
_TYPE_ATTR_RE = re.compile(r"""\btype\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_SRC_ATTR_RE = re.compile(r"\bsrc\s*=", re.IGNORECASE)
# `type` values Astro processes as a module; anything else (JSON-LD, a
# template) is data, not code.
_SCRIPT_TYPES = frozenset(
    {"", "module", "text/javascript", "application/javascript", "text/typescript"}
)


def mask_astro(text: str) -> str:
    """Same-length view of `text` keeping only its frontmatter and script bodies."""
    keep = [False] * len(text)
    template_start = _keep_frontmatter(text, keep)
    semicolons = _keep_scripts(text, keep, template_start)
    return "".join(
        ";" if index in semicolons else (char if keep[index] or char == "\n" else " ")
        for index, char in enumerate(text)
    )


_NOT_TEMPLATE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>|<!--.*?-->", re.IGNORECASE | re.DOTALL)


def astro_template(text: str) -> str:
    """Same-length view of `text` keeping only its template: no frontmatter, scripts, styles or comments."""
    start = _keep_frontmatter(text, [False] * len(text))
    view = "".join(char if char == "\n" else " " for char in text[:start]) + text[start:]
    return _NOT_TEMPLATE_RE.sub(
        lambda match: "".join(char if char == "\n" else " " for char in match.group(0)), view
    )


def _keep_frontmatter(text: str, keep: list[bool]) -> int:
    opening = _FENCE_RE.search(text)
    if opening is None or text[: opening.start()].strip():
        return 0
    closing = _FENCE_RE.search(text, opening.end())
    if closing is None:
        return 0
    keep[opening.end() : closing.start()] = [True] * (closing.start() - opening.end())
    return closing.end()


def _keep_scripts(text: str, keep: list[bool], start: int) -> set[int]:
    semicolons: set[int] = set()
    for opening in _SCRIPT_OPEN_RE.finditer(text, start):
        tag_end = _tag_end(text, opening.end())
        if tag_end is None or text[tag_end - 1] == "/":
            continue
        attributes = text[opening.end() : tag_end]
        script_type = _TYPE_ATTR_RE.search(attributes)
        if _SRC_ATTR_RE.search(attributes) or (
            script_type and script_type.group(1).strip().lower() not in _SCRIPT_TYPES
        ):
            continue
        closing = _SCRIPT_CLOSE_RE.search(text, tag_end)
        body_end = closing.start() if closing else len(text)
        keep[tag_end + 1 : body_end] = [True] * (body_end - tag_end - 1)
        # The blanked tag is followed by code; a `;` where its `>` was keeps a
        # body that opens with `(` or `[` from joining the previous statement.
        semicolons.add(tag_end)
    return semicolons


def _tag_end(text: str, index: int) -> int | None:
    quote, depth = "", 0
    while index < len(text):
        char = text[index]
        if quote:
            quote = "" if char == quote else quote
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth = max(depth - 1, 0)
        elif char == ">" and depth == 0:
            return index
        index += 1
    return None
