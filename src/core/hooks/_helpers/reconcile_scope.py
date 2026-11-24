"""Say whether a Bash command may have changed files inside the project.

Prints "skip" only when the command provably worked elsewhere: it cd's to a
literal absolute path outside the project, or every path it names is an
absolute path outside it. Anything a static read cannot settle prints "go",
because a stale graph answers wrongly while an extra reindex only costs time.

USAGE
    python3 reconcile_scope.py <command> <project_root>
"""

from __future__ import annotations

import os
import shlex
import sys

_OPERATORS = {"&&", "||", ";", "|", "&"}
_REDIRECTS = {">", ">>", "<", "2>", "&>", "2>>"}
# cd state a static read cannot follow: subshells, directory stacks, `cd -`.
_UNTRACKABLE = {"(", ")", "pushd", "popd"}


def _inside(path: str, roots: set[str]) -> bool:
    forms = {os.path.normpath(path), os.path.realpath(path)}
    return any(form == root or form.startswith(root + os.sep) for form in forms for root in roots)


def _previous_command_was_cd(tokens: list[str], index: int) -> bool:
    start = index - 1
    while start > 0 and tokens[start - 1] not in _OPERATORS:
        start -= 1
    return tokens[start] == "cd"


def decide(command: str, project_root: str) -> str:
    roots = {os.path.normpath(project_root), os.path.realpath(project_root)}
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return "go"
    away = False  # cd'd to a known place outside the project
    outside = False
    command_position = True
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else ""
        if token in _UNTRACKABLE or (previous == "cd" and token == "-"):
            return "go"
        if token in _OPERATORS:
            if token == "||" and _previous_command_was_cd(tokens, index):
                return "go"  # the cd may have failed and the rest ran here
            command_position = True
            continue
        if token in _REDIRECTS or previous in _REDIRECTS:
            continue
        if "$" in token or "`" in token:
            return "go"
        if command_position:
            command_position = False
            continue  # the command word itself is not a path
        if previous == "cd":
            path = os.path.expanduser(token)
            if os.path.isabs(path):
                away = not _inside(path, roots)
                outside = outside or away
            continue  # a relative cd stays wherever the command already was
        operand = token.split("=", 1)[1] if token.startswith("-") and "=" in token else token
        if operand.startswith("-") or not operand:
            continue
        path = os.path.expanduser(operand)
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
