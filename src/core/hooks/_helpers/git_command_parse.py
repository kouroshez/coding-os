#!/usr/bin/env python3
"""Shared git-command tokenizer for the git-safety hooks.

One audited parser so every git gate (branch-guard, block-secrets,
enforce-commit-message) reasons about the SAME thing bash will actually
execute — not an ad-hoc regex over the raw or quote-stripped string. The
root cause of the whole bypass class (quote-splice `--no-ver"i"fy`,
`GIT_CONFIG_*` env injection, `git commit -a` slipping the dispatch,
`git commit` appearing inside an `echo`/`python -c` string) is each hook
re-parsing differently; this collapses them onto shlex word-splitting.

`shlex.split` collapses quote-splices exactly like bash
(`--no-ver"i"fy` → `--no-verify`), keeps a `-m` message body inside its
own value token (so a message that mentions `--no-verify` never reads as
a flag), and unquotes nested `sh -c '...'`. Unbalanced quotes raise
ValueError — callers fail CLOSED on a git invocation they cannot parse.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass, field

# git global options that take the next token as their argument.
_GLOBAL_OPTS_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
# git global flags with no argument.
_GLOBAL_OPTS_NO_ARG = {
    "-p",
    "--paginate",
    "-P",
    "--no-pager",
    "--no-replace-objects",
    "--bare",
    "--no-optional-locks",
    "--literal-pathspecs",
    "--glob-pathspecs",
    "--noglob-pathspecs",
    "--icase-pathspecs",
}
# `--key=value` long options that bundle the arg.
_GLOBAL_LONG_EQ_PREFIXES = ("--git-dir=", "--work-tree=", "--namespace=", "-c=")

# Shells whose `-c <inner>` invocations we descend into. NOT python/node — a
# `git commit` inside `python3 -c "..."` is a literal string, never executed,
# so it must not read as a real invocation (the enforce-commit-message FP).
_NESTED_SHELLS = {"sh", "bash", "zsh", "dash"}

# Recursion bound for nested `sh -c`/backtick descent — 8 levels is far beyond any
# realistic input; the cap only guards against a pathological/adversarial command.
_MAX_NEST_DEPTH = 8


def looks_like_env_assignment(token: str) -> bool:
    """`FOO=bar` (caller-set env var) — a leading run of these precedes the cmd."""
    if "=" not in token:
        return False
    name = token.split("=", 1)[0]
    return bool(name) and bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name))


def partition_env(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split a leading `VAR=val ...` env prefix off the command. Returns
    (env_assignments, rest). The env list is kept (not just dropped) so a gate
    can inspect `GIT_CONFIG_*` / hook-disabling assignments."""
    i = 0
    while i < len(tokens) and looks_like_env_assignment(tokens[i]):
        i += 1
    return tokens[:i], tokens[i:]


def strip_env_vars(tokens: list[str]) -> list[str]:
    return partition_env(tokens)[1]


def strip_git_globals(tokens: list[str]) -> list[str]:
    """Drop `git`'s pre-subcommand globals so the next token is the subcommand."""
    out: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t in _GLOBAL_OPTS_WITH_ARG:
            i += 2
            continue
        if t in _GLOBAL_OPTS_NO_ARG:
            i += 1
            continue
        if any(t.startswith(p) for p in _GLOBAL_LONG_EQ_PREFIXES):
            i += 1
            continue
        out.extend(tokens[i:])
        break
    return out


# Crude segmenter: split on shell separators that start a new command.
# Doesn't perfectly respect quoting, but quoted commands are recovered via
# the `sh -c <quoted>` extractor below — together they cover the cases the
# reviewer surfaced.
_SEGMENT_SPLIT_RE = re.compile(r"&&|\|\||[;|()&]")


def split_segments(command: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT_RE.split(command) if s.strip()]


# Backtick command substitution `` `cmd` `` — extract inner. The negative
# lookbehind skips ESCAPED backticks (`\``), which inside a `"..."` arg are
# inert literals — bash does not execute them. This avoids false positives
# on commit messages / docs that quote shell snippets like
# `git commit -m "see \`git reset HEAD~1\` for unsafe form"`.
_BACKTICK_RE = re.compile(r"(?<!\\)`([^`]+)`")


def extract_backticks(segments: list[str]) -> list[str]:
    extra: list[str] = []
    for seg in segments:
        for m in _BACKTICK_RE.finditer(seg):
            extra.extend(split_segments(m.group(1)))
    return extra


def extract_nested_shells(segments: list[str]) -> list[str]:
    """For each `sh -c <inner>` / `bash -c <inner>` token sequence, return the
    inner string split into its own segments. shlex unquotes the inner."""
    extra: list[str] = []
    for seg in segments:
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            continue
        tokens = strip_env_vars(tokens)
        if len(tokens) < 3:
            continue
        if tokens[0] in _NESTED_SHELLS and tokens[1] == "-c":
            inner = tokens[2]
            extra.extend(split_segments(inner))
    return extra


def all_segments(command: str) -> list[str]:
    """Expand a normalized command into every executable segment: split on shell
    separators, then unwrap nested `sh -c`/backtick subshells with bounded
    recursion."""
    segments = split_segments(command)
    segments.extend(extract_backticks(segments))
    frontier = list(segments)
    seen = set(segments)
    for _ in range(_MAX_NEST_DEPTH):  # runaway recursion guard
        layer = extract_nested_shells(frontier) + extract_backticks(frontier)
        layer = [s for s in layer if s not in seen]
        if not layer:
            break
        seen.update(layer)
        segments.extend(layer)
        frontier = layer
    return segments


def tokenize(seg: str) -> list[str]:
    try:
        return shlex.split(seg, posix=True)
    except ValueError:
        # Unbalanced quotes — fall back to whitespace split so the dominant
        # `git reset HEAD~1` form is still caught.
        return seg.split()


def normalize(command: str) -> str:
    """Newlines → separators, then collapse whitespace runs — so a multi-line
    or tab-padded command reads as the same segments bash would run."""
    command = re.sub(r"\n+", "; ", command)
    return " ".join(command.split())


@dataclass
class GitInvocation:
    """One real `git <subcmd>` call found in a command line."""

    env: list[str] = field(default_factory=list)  # leading VAR=val assignments
    globals: list[str] = field(default_factory=list)  # pre-subcommand git globals
    subcmd: str = ""
    args: list[str] = field(default_factory=list)  # tokens after the subcommand


# `git commit` short flags that consume the FOLLOWING token as their value, so
# the value is never mis-read as another flag (`-m "msg"`, `-am "msg"`).
_COMMIT_VALUE_SHORT = set("mFCc")


def commit_flags(args: list[str]) -> tuple[set[str], list[str]]:
    """Normalize a `git commit` arg list to (short_flag_letters, long_flags).

    Skips the value of value-taking flags so a message body never reads as a
    flag: `-am "x"` → ({'a','m'}, []), `-m "-a"` → ({'m'}, []) (the `-a` is the
    message, not the -a flag), `--all` → (set(), ['--all']). Shared by the two
    commit gates (no-verify detection, -a sweep detection) so the fiddly
    value-skip logic lives — and is audited — in exactly one place.
    """
    short: set[str] = set()
    longs: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            longs.append(a.split("=", 1)[0])
            i += 1
            continue
        if len(a) >= 2 and a[0] == "-" and a[1:].isalpha():
            # Scan the cluster char-by-char: a value-taking flag (m/F/C/c) consumes
            # the REST of its own cluster as an ATTACHED value, so it and the chars
            # after it are NOT flags. `-mn` = -m with message "n" → short {'m'} (NOT
            # {'m','n'}, which falsely read as -n/--no-verify); `-mnope` = -m "nope".
            # `-nm` = -n -m → {'n','m'}; if the value flag is last, the value is the
            # next token. (Old code did short.update(a[1:]) → the -mn false-positive.)
            j = 1
            while j < len(a):
                c = a[j]
                short.add(c)
                if c in _COMMIT_VALUE_SHORT:
                    if j == len(a) - 1:  # value flag is last → value is the next token
                        i += 1
                    break
                j += 1
            i += 1
            continue
        i += 1  # positional / a value token
    return short, longs


def _unwrap_env(tokens: list[str]) -> tuple[list[str], list[str]]:
    """`env [-i|-u NAME|--] [NAME=VAL]... cmd args` → (captured NAME=VAL, [cmd, …]).
    A leading `env` wrapper otherwise hides the real command word (`env GIT_X=1
    git commit --no-verify` ran git but read as command `env`). The captured
    assignments are merged into the invocation env so a `GIT_CONFIG_*` injected
    THROUGH env is still seen."""
    env: list[str] = []
    i = 1  # tokens[0] is `env`
    while i < len(tokens):
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if t in ("-u", "--unset") and i + 1 < len(tokens):
            i += 2
            continue
        if t.startswith("-"):
            i += 1
            continue
        if looks_like_env_assignment(t):
            env.append(t)
            i += 1
            continue
        break
    return env, tokens[i:]


def resolve_command(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Strip a leading `VAR=val` prefix, a `{ …; }` brace-group opener, AND an
    `env …` wrapper (in any order), returning (env_assignments, command_tokens).
    So `{ FOO=1 env BAR=2 /usr/bin/git commit ...` resolves to command word
    `/usr/bin/git` with env {FOO,BAR} captured. The brace strip closes a grouping
    bypass: `{ git commit --no-verify; }` would otherwise read command word `{`."""
    env: list[str] = []
    rest = list(tokens)
    while True:
        e, rest = partition_env(rest)
        env += e
        if rest and rest[0] == "{":  # brace-group / command-list opener
            rest = rest[1:]
            continue
        if rest and os.path.basename(rest[0]) == "env":
            e2, rest = _unwrap_env(rest)
            env += e2
            continue
        break
    return env, rest


def is_git_word(token: str) -> bool:
    """True for `git`, `/usr/bin/git`, `./git` — a path-qualified git still runs
    git (the old regex allowed a `([^/]*/)?git` prefix; a bare `== "git"` did not)."""
    return os.path.basename(token) == "git"


def _is_operator(tok: str) -> bool:
    return bool(tok) and all(c in "();<>|&" for c in tok)


def _punct_tokens(command: str) -> list[str] | None:
    """Quote-AWARE tokenization: shlex(punctuation_chars=True) emits the shell
    operators `();<>|&` — which ALREADY INCLUDES `;` — as standalone tokens while
    keeping quoted content (a commit message containing `(`, `;`, `|`) intact.
    None on unbalanced quotes.

    DO NOT add `;` to lex.whitespace: `;` is already a punctuation operator, and
    demoting it to whitespace makes shlex DROP it, so `foo; git commit --no-verify`
    merges into ONE group whose first word is `foo` and the git command is never
    seen — a critical verify-hook bypass (TASK-571; the regression this fixes)."""
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError:
        return None


def command_groups(command: str, _depth: int = 0) -> list[list[str]]:
    """Every command in `command` as a quote-aware token list, with nested
    `sh -c '<inner>'` expanded. Falls back to the crude regex segmenter on a
    shlex failure (unbalanced quotes) so the dominant forms are still seen."""
    toks = _punct_tokens(command)
    if toks is None:
        return [seg.split() for seg in all_segments(command)]
    groups: list[list[str]] = []
    cur: list[str] = []
    for t in toks:
        if _is_operator(t):
            if cur:
                groups.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        groups.append(cur)
    if _depth < _MAX_NEST_DEPTH:  # descend into nested commands, bounded
        for g in groups:
            g2 = strip_env_vars(g)
            if len(g2) >= 3 and g2[0] in _NESTED_SHELLS and g2[1] == "-c":
                groups = groups + command_groups(g2[2], _depth + 1)
        # Backtick substitution `cmd` EXECUTES cmd (unquoted / inside "…"); shlex
        # leaves it glued (`echo \`git commit\`` → ['echo','`git','commit`']), so a
        # `\`git commit --no-verify\`` would slip. Extract + recurse like sh -c.
        for m in _BACKTICK_RE.finditer(command):
            groups = groups + command_groups(m.group(1), _depth + 1)
    return groups


def git_invocations(command: str) -> list[GitInvocation]:
    """Every real `git` invocation in `command`, fully tokenized. A `git commit`
    that is actually an argument to `echo`/`python -c` (its command word is not
    `git`) is correctly excluded — only groups whose first word IS git count.
    Path-qualified (`/usr/bin/git`) and `env`-wrapped invocations ARE counted."""
    out: list[GitInvocation] = []
    for g in command_groups(normalize(command)):
        env, rest = resolve_command(g)
        if not rest or not is_git_word(rest[0]):
            continue
        after_git = rest[1:]
        sub = strip_git_globals(after_git)
        if not sub:
            continue
        globals_ = after_git[: len(after_git) - len(sub)]
        out.append(GitInvocation(env=env, globals=globals_, subcmd=sub[0], args=sub[1:]))
    return out
