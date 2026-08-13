#!/usr/bin/env python3
"""Extract -m/--message bodies from REAL `git commit` invocations only.

Reads the bash command on stdin, emits the commit message(s) joined by a
blank line (the multi-`-m` paragraph convention). The shared shlex parser
scopes extraction to segments whose command word is actually `git` — so a
`git commit -m "bad"` quoted INSIDE an `echo` or `python3 -c "..."` (a
verification snippet, a doc example) is NOT treated as a commit to validate
(TASK-567 fixed enforce-commit-message false-positiving on those). Forms
the tokenizer can't cleanly resolve (heredoc `-F-`, command substitution)
yield no message and defer to the git-level commit-msg hook, as before.
"""

from __future__ import annotations

import re
import sys

from git_command_parse import git_invocations

# `git_command_parse.normalize()` collapses every newline to `; ` before
# tokenizing — correct for real statement separators, but a heredoc body
# (`$(cat <<'EOF' ... EOF)`) has embedded newlines that are literal content,
# not separators. shlex then hands `_messages` one intact-looking quoted
# token that is actually still-unexpanded shell source (heredoc markers,
# `$(...)`/backtick command substitution) rather than the string bash would
# have produced. Validating that raw source AS IF it were the final message
# is exactly the bug this module's docstring already promises not to have:
# treat any such value as unparseable and defer, matching a plain `-m` value
# that legitimately contains none of these constructs.
_UNEXPANDED_RE = re.compile(r"\$\(|`|<<-?['\"]?\w")


def _looks_unexpanded(value: str) -> bool:
    return bool(_UNEXPANDED_RE.search(value))


def _messages(args: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-m", "--message"):
            if i + 1 < len(args):
                out.append(args[i + 1])
                i += 2
                continue
        elif a.startswith("--message="):
            out.append(a[len("--message=") :])
        elif a.startswith("-m") and len(a) > 2 and not a.startswith("--"):
            out.append(a[2:])  # `-mfoo` attached value
        # short cluster ending in m (`-am`, `-sm`)
        elif (
            len(a) >= 2
            and a[0] == "-"
            and a[1] != "-"
            and a[1:].isalpha()
            and a.endswith("m")
            and i + 1 < len(args)
        ):
            out.append(args[i + 1])
            i += 2
            continue
        i += 1
    if any(_looks_unexpanded(v) for v in out):
        return []  # can't cleanly resolve this invocation — defer, don't mis-validate
    return out


def main() -> int:
    command = sys.stdin.read()
    parts: list[str] = []
    for inv in git_invocations(command):
        if inv.subcmd == "commit":
            parts.extend(_messages(inv.args))
    sys.stdout.write("\n\n".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
