"""graph_os — a same-length TypeScript view of an `.astro` component.

An Astro file is a `---` frontmatter fence of TypeScript, a template, and
optional `<script>` / `<style>` blocks. code_ts reads the masked view: the
frontmatter and the body of each `<script>` Astro processes are kept, every
other character becomes a space and every newline survives, so the lines and
columns code_ts reports are the `.astro` file's own. Astro processes a script
only when it has no attribute but `src`; `is:inline`, `type="module"` or any
other attribute leaves it to the browser as written, so it is not read. The
closing fence is the first `---` line outside a string or comment of the
frontmatter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE_RE = re.compile(r"^\ufeff?---[ \t]*\r?$", re.MULTILINE)
_SCRIPT_OPEN_RE = re.compile(r"<script\b", re.IGNORECASE)
_SCRIPT_CLOSE_RE = re.compile(r"</script\s*>", re.IGNORECASE)
_ATTRIBUTE_RE = re.compile(r"""([^\s=/>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?""")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


@dataclass(frozen=True)
class AstroScript:
    line: int
    body_start: int
    body_end: int
    src: str | None


def mask_astro(text: str) -> str:
    """Same-length view of `text` keeping only its frontmatter and processed script bodies."""
    keep = [False] * len(text)
    _keep_frontmatter(text, keep)
    semicolons: set[int] = set()
    for script in astro_scripts(text):
        if script.src is None:
            keep[script.body_start : script.body_end] = [True] * (
                script.body_end - script.body_start
            )
            # The blanked tag is followed by code; a `;` where its `>` was keeps
            # a body that opens with `(` or `[` from joining the previous statement.
            semicolons.add(script.body_start - 1)
    return "".join(
        ";" if index in semicolons else (char if keep[index] or char == "\n" else " ")
        for index, char in enumerate(text)
    )


def astro_scripts(text: str) -> list[AstroScript]:
    """The `<script>` tags Astro processes, in order: no attribute but `src`."""
    start = _keep_frontmatter(text, [False] * len(text))
    comments = [match.span() for match in _HTML_COMMENT_RE.finditer(text, start)]
    scripts = []
    for opening in _SCRIPT_OPEN_RE.finditer(text, start):
        if any(begin <= opening.start() < end for begin, end in comments):
            continue
        tag_end = _tag_end(text, opening.end())
        if tag_end is None:
            continue
        attributes = {
            match.group(1).lower(): next((value for value in match.groups()[1:] if value), "")
            for match in _ATTRIBUTE_RE.finditer(text[opening.end() : tag_end].rstrip("/"))
        }
        if set(attributes) - {"src"}:
            continue
        closing = None if text[tag_end - 1] == "/" else _SCRIPT_CLOSE_RE.search(text, tag_end)
        scripts.append(
            AstroScript(
                line=text.count("\n", 0, opening.start()) + 1,
                body_start=tag_end + 1,
                body_end=closing.start() if closing else tag_end + 1,
                src=attributes.get("src") or None,
            )
        )
    return scripts


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
    closing = _closing_fence(text, opening.end())
    if closing is None:
        return 0
    keep[opening.end() : closing.start()] = [True] * (closing.start() - opening.end())
    return closing.end()


def _closing_fence(text: str, start: int) -> re.Match[str] | None:
    state, index = "", start
    for fence in _FENCE_RE.finditer(text, start):
        state, index = _lex(text, index, fence.start(), state)
        if not state:
            return fence
    return None


def _lex(text: str, index: int, stop: int, state: str) -> tuple[str, int]:
    # `state` is the open string quote or comment opener at `index`, "" in code.
    while index < stop:
        char, pair = text[index], text[index : index + 2]
        if state in ("'", '"', "`"):
            if char == "\\":
                index += 2
                continue
            if char == state or (char == "\n" and state != "`"):
                state = ""
        elif state == "//":
            state = "" if char == "\n" else state
        elif state == "/*":
            if pair == "*/":
                state, index = "", index + 2
                continue
        elif pair in ("//", "/*"):
            state, index = pair, index + 2
            continue
        elif char in "'\"`":
            state = char
        index += 1
    return state, index


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
