#!/usr/bin/env python3
"""Detect a git commit that tries to skip the verify hooks.

Replaces block-secrets' bash regex over a quote-STRIPPED string, which
`git commit --no-ver"i"fy`, `"--no-verify"`, `"-n"`, and a `GIT_CONFIG_*=…`
env prefix all slipped past (the string was edited to remove the quotes
BEFORE the flag regex ran, so the spliced flag vanished from the scan yet
bash still executed it). Tokenizing via the shared parser makes the gate
see the SAME `--no-verify` bash will — and keeps a `-m` message body that
merely mentions `--no-verify` an inert value token, never a flag.

Stdout: {"verdict":"allow"} | {"verdict":"block","message":"..."}
Exit 0 always — the JSON verdict is the signal.
"""

from __future__ import annotations

import json
import sys

from git_command_parse import (
    GitInvocation,
    abbrev_resolves,
    commit_flags,
    git_invocations,
)

_HOOKS_ENV_NULL = {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}

# `git commit`'s `--no-*` long options — the competitors that decide whether an
# abbreviation resolves to --no-verify. `--no-verbose` shares the `--no-ver`
# prefix, so `--no-ver` is ambiguous (git itself rejects it) and only `--no-veri`
# and longer resolve to --no-verify; the rest never collide but are listed so the
# disambiguation stays correct as git's option set grows.
_COMMIT_NO_LONGS = frozenset(
    {
        "--no-verify",
        "--no-verbose",
        "--no-edit",
        "--no-amend",
        "--no-status",
        "--no-post-rewrite",
        "--no-gpg-sign",
        "--no-signoff",
        "--no-progress",
        "--no-renames",
    }
)


def _commit_skips_verify(inv: GitInvocation) -> bool:
    # `-n` short flag, or any long option that git would resolve to --no-verify —
    # the literal `--no-verify` match missed `--no-veri`/`--no-verif` (git accepts
    # any unambiguous prefix). A quoted message body is dropped by commit_flags, so
    # a message mentioning the flag stays safe.
    short, longs = commit_flags(inv.args)
    if "n" in short:
        return True
    return any(abbrev_resolves(lg, "--no-verify", _COMMIT_NO_LONGS) for lg in longs)


def _hooks_path_in_globals(globals_: list[str]) -> bool:
    i = 0
    while i < len(globals_):
        t = globals_[i]
        kv = None
        if t == "-c" and i + 1 < len(globals_):
            kv = globals_[i + 1]
            i += 2
        elif t.startswith("-c="):
            kv = t[len("-c=") :]
            i += 1
        else:
            i += 1
            continue
        if kv.split("=", 1)[0].strip().lower() == "core.hookspath":
            return True
    return False


def _env_disables_hooks(env: list[str]) -> bool:
    keys = {}
    for tok in env:
        name, _, val = tok.partition("=")
        keys[name] = val
    for name, val in keys.items():
        if name.startswith("GIT_CONFIG_KEY_") and val.strip().lower() == "core.hookspath":
            return True
    # ANY caller-supplied GIT_CONFIG_GLOBAL/SYSTEM on a commit redirects git's config
    # file — not only `/dev/null`: a custom file containing `[core] hooksPath=/dev/null`
    # disables the verify hooks just as effectively (TASK-571). An agent never sets
    # these on a real commit, so blocking the whole class is safe (no false positive).
    return any(name in keys for name in _HOOKS_ENV_NULL)


_CONFIG_READ_FLAGS = {
    "--get",
    "--get-all",
    "--get-regexp",
    "--get-urlmatch",
    "-l",
    "--list",
    "--name-only",
}


def _config_writes_hooks_path(inv: GitInvocation) -> bool:
    if inv.subcmd != "config":
        return False
    if any(a in _CONFIG_READ_FLAGS for a in inv.args):
        return False  # a READ (`git config --get core.hooksPath`) sets nothing
    return any(a.split("=", 1)[0].strip().lower() == "core.hookspath" for a in inv.args)


def _blocks(command: str) -> bool:
    for inv in git_invocations(command):
        if _hooks_path_in_globals(inv.globals):  # `-c core.hooksPath` on any git op
            return True
        if _config_writes_hooks_path(inv):
            return True
        if inv.subcmd == "commit" and (_commit_skips_verify(inv) or _env_disables_hooks(inv.env)):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        json.dump({"verdict": "allow"}, sys.stdout)
        return 0
    if _blocks(command):
        json.dump(
            {
                "verdict": "block",
                "message": (
                    "BLOCKED: skipping git verify hooks (--no-verify / -n / "
                    "core.hooksPath / GIT_CONFIG_* override). Fix the underlying "
                    "issue, don't bypass."
                ),
            },
            sys.stdout,
        )
        return 0
    json.dump({"verdict": "allow"}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
