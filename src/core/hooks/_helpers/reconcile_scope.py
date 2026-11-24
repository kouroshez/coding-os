"""Say whether a Bash command may have changed files inside the project.

Prints "skip" only when the command provably worked elsewhere: it cd's to a
literal absolute path outside the project, or every path it names is an
absolute path outside it. Anything unclear prints "go", because a stale graph
answers wrongly while an extra reindex only costs time.

USAGE
    python3 reconcile_scope.py <command> <project_root>
"""

from __future__ import annotations

import os
import shlex
import sys

_OPERATORS = {"&&", "||", ";", "|", "&", "(", ")"}
_REDIRECTS = {">", ">>", "<", "2>", "&>", "2>>"}


def _inside(path: str, roots: set[str]) -> bool:
    candidate = os.path.normpath(path)
    return any(candidate == root or candidate.startswith(root + os.sep) for root in roots)


def _is_dynamic(token: str) -> bool:
    return "$" in token or "`" in token


def decide(command: str, project_root: str) -> str:
    roots = {os.path.normpath(project_root), os.path.realpath(project_root)}
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return "go"
    away = False  # cd'd to a known place outside the project
    outside = False
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else ""
        if token in _OPERATORS or token in _REDIRECTS or previous in _REDIRECTS:
            continue
        if _is_dynamic(token):
            return "go"
        path = os.path.expanduser(token)
        if previous == "cd":
            if os.path.isabs(path):
                away = not _inside(path, roots)
                outside = outside or away
            continue  # a relative cd stays wherever the command already was
        if "/" not in token or token.startswith("-"):
            continue
        if os.path.isabs(path):
            if _inside(path, roots):
                return "go"
            outside = True
        elif not away:
            return "go"
    return "skip" if outside else "go"


def main(argv: list[str]) -> int:
    print(decide(argv[1], argv[2]) if len(argv) == 3 else "go")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
