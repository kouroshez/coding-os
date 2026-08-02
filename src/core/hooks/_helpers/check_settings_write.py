"""Detect a Bash write whose target is a coding-os git-policy file.

stdin: hook JSON envelope. Prints `block` or `allow` (the Bash hook maps
block→exit 2). Closes the self-downgrade vector where an agent rewrites
`<root>/.coding-os/hub-settings.json` via redirect / tee / dd / cp / mv /
sed -i / `python -c` to flip pr-mode off, then pushes to main under trunk.

Defense-in-depth only — the authoritative wall is server-side branch
protection; this helper FAILS OPEN on its own error (the Bash hook's
`|| echo allow`). Scoped to ONE basename so blast radius is a single file.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from git_command_parse import all_segments, normalize, tokenize  # noqa: E402

_POLICY_BASENAMES = {"hub-settings.json"}
_POLICY_PARENT = ".coding-os"
# A redirection target: `> f`, `>> f`, `2> f` (operator then path).
_REDIRECT_RE = re.compile(r"(?:^|\s)\d*>>?\s*([^\s;&|<>]+)")
# An inline interpreter write: a file mode 'w'/'a' or a known writer call.
_INTERP_WRITE_RE = re.compile(
    r"""['"][wax][+btu]*['"]|writeFileSync|writeText|\.dump\(|\.write\("""
)
# The policy path as a literal inside interpreter source.
_INTERP_PATH_RE = re.compile(r"""['"]([^'"]*\.coding-os/[^'"]*hub-settings\.json)['"]""")


def _is_policy_path(raw: str) -> bool:
    raw = raw.strip().strip("'\"")
    if not raw:
        return False
    real = os.path.realpath(os.path.expanduser(raw))  # Rule 5: collapse ../ + symlinks
    return (
        os.path.basename(real) in _POLICY_BASENAMES
        and os.path.basename(os.path.dirname(real)) == _POLICY_PARENT
    )


def _interpreter_writes_policy(command: str) -> bool:
    # `python -c "...open('....coding-os/hub-settings.json','w')..."`: all_segments
    # shatters the inline code on `()`, so scan the RAW command — require BOTH a
    # write-mode token AND the policy path literal (a read like json.load passes).
    if not _INTERP_WRITE_RE.search(command):
        return False
    return any(_is_policy_path(m.group(1)) for m in _INTERP_PATH_RE.finditer(command))


def _segment_writes_policy(segment: str) -> bool:
    for m in _REDIRECT_RE.finditer(segment):  # `>`/`>>` redirection
        if _is_policy_path(m.group(1)):
            return True
    toks = tokenize(segment)
    if not toks:
        return False
    cmd = os.path.basename(toks[0])
    if cmd == "tee":  # tee writes every non-flag operand
        return any(_is_policy_path(t) for t in toks[1:] if not t.startswith("-"))
    if cmd == "dd":  # dd of=<path>
        return any(t.startswith("of=") and _is_policy_path(t[len("of=") :]) for t in toks)
    if cmd in {"cp", "mv", "install", "rsync"}:  # destination = last positional
        positionals = [t for t in toks[1:] if not t.startswith("-")]
        return bool(positionals) and _is_policy_path(positionals[-1])
    if cmd in {"sed", "perl"} and any(t.startswith("-i") for t in toks[1:]):  # in-place edit
        return any(_is_policy_path(t) for t in toks[1:] if not t.startswith("-"))
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        command = (payload.get("tool_input", {}) or {}).get("command", "") or ""
    except (json.JSONDecodeError, ValueError, AttributeError):
        print("allow")
        return 0
    if not isinstance(command, str) or "hub-settings.json" not in command:
        print("allow")
        return 0
    command = normalize(command)
    if _interpreter_writes_policy(command) or any(
        _segment_writes_policy(seg) for seg in all_segments(command)
    ):
        print("block")
        return 0
    print("allow")
    return 0


if __name__ == "__main__":
    sys.exit(main())
