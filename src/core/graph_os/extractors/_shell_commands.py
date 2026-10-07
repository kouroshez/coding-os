"""graph_os — what one shell command depends on.

A `source` makes the script depend on a file; `bash x.sh`, `python3 -W ignore
x.py`, `uv run x.py`, `node --require r.js x.mjs`, `deno run -A x.ts`, an
extensionless script run by path or shell, and the same behind `sudo`, `xargs`,
`timeout 5s` and friends run another file; a call to a function this file does
not define names one a sourced library defines — the linker binds that
`code:external:shfn:<name>` stub to the one real definition. `command -v NAME`
looks a function up without calling it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any

from ..ingest.base import is_shell_script
from ..types import EvidenceSignal, GraphEdge
from ._code_shell_emit import EXTRACTOR_ID, _emit_log_hook_edge
from ._shell_paths import ShellScope, directive_paths, resolve
from .md_links import ExtractionResult

SHELL_FUNCTION_STUB = "code:external:shfn:"
SOURCE_CONFIDENCE = {True: 0.9, False: 0.7}
RUN_CONFIDENCE = {True: 0.85, False: 0.7}
MODULE_RUN_CONFIDENCE = 0.6
LOCAL_CALL_CONFIDENCE = 0.9
FUNCTION_STUB_CONFIDENCE = 0.5

_BUILTINS = frozenset(
    {
        "alias", "bg", "bind", "break", "builtin", "caller", "cd", "command", "compgen",
        "complete", "compopt", "continue", "declare", "dirs", "disown", "echo", "enable",
        "eval", "exec", "exit", "export", "false", "fc", "fg", "getopts", "hash", "help",
        "history", "jobs", "kill", "let", "local", "logout", "mapfile", "popd", "printf",
        "pushd", "pwd", "read", "readarray", "readonly", "return", "set", "shift", "shopt",
        "source", "suspend", "test", "times", "trap", "true", "type", "typeset", "ulimit",
        "umask", "unalias", "unset", "wait", "[", "[[", ":", ".", "time", "coproc",
        # Keywords: a construct tree-sitter cannot parse leaves them as words.
        "if", "then", "else", "elif", "fi", "case", "esac", "for", "while", "until", "do",
        "done", "in", "function", "select",
    }
)  # fmt: skip
_WRAPPERS = frozenset(
    {"exec", "nice", "nohup", "time", "command", "env", "timeout", "sudo", "xargs"}
)
_WRAPPER_VALUE_FLAGS = {
    "sudo": frozenset({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U"}),
    "xargs": frozenset({"-n", "-I", "-P", "-L", "-d", "-s", "-E", "-a"}),
    "timeout": frozenset({"-k", "-s", "--kill-after", "--signal"}),
    "nice": frozenset({"-n"}),
}
_DURATION_RE = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_JS_RUNNERS = frozenset({"node", "tsx", "ts-node", "bun", "deno"})
_PACKAGE_RUNNERS = frozenset({"npx", "pnpx", "bunx"})
_UV_VALUE_FLAGS = frozenset({"--extra", "--with", "--project", "--directory", "--python", "-p"})
# Per runner: flags that take a value, and flags whose value is inline code (no file runs).
_RUNNER_FLAGS = {
    "python": (frozenset({"-W", "-X", "-Q"}), frozenset({"-c", "-m"})),
    "node": (
        frozenset({"-r", "--require", "--import", "--loader", "--experimental-loader", "-C"}),
        frozenset({"-e", "--eval", "-p", "--print"}),
    ),
    "shell": (frozenset({"-o", "-O"}), frozenset({"-c"})),
}
_PYTHON_RE = re.compile(r"^python(?:\d+(?:\.\d+)?)?$")
# `$PY`, `${PYTHON:-python3}`, `$VENV_PYTHON`, `$PY3` — not `$COPY_CMD` or `$PYTHONPATH`.
_PYTHON_VARIABLE_RE = re.compile(
    r"^\$\{?(?:\w+_)?PY(?:THON)?[\d.]*(?:_\w+)?(?::-[^}]*)?\}?$", re.IGNORECASE
)
_FUNCTION_NAME_RE = re.compile(r"^[A-Za-z_][\w:.-]*$")
_FUNCTION_WORD_RE = re.compile(r"[A-Za-z_][\w:.-]*")
_RUNNABLE_SUFFIXES = (".py", ".mjs", ".cjs", ".js", ".ts", ".mts", ".cts")
_SHELL_SUFFIXES = (".sh", ".bash", ".zsh")


@dataclass
class ShellFile:
    path: str
    module_uid: str
    root: Path | None
    scope: ShellScope
    local_functions: dict[str, str]
    loops: dict[tuple[int, int], tuple[str, list[str]]]
    directives: dict[int, list[str]]
    result: ExtractionResult
    seen: set[tuple[str, str, str]] = field(default_factory=set)


def handle_command(node: Any, text_of: Any, caller_uid: str, file: ShellFile) -> None:
    """Emit the edges one `command` node implies."""
    words = _strip_wrappers(_command_words(node, text_of))
    if not words:
        return
    name, args = words[0], words[1:]
    line = node.start_point[0] + 1
    if name in ("source", "."):
        _emit_sources(node, args, line, file)
    elif name == "cos_log_hook":
        if args and re.fullmatch(r"[A-Za-z0-9_-]+", args[0]):
            _emit_log_hook_edge(args[0], line, file.path, file.result, file.module_uid)
        _emit_function_call(name, caller_uid, line, file)
    elif name in _SHELLS or name in _JS_RUNNERS or _is_python(name):
        _emit_run(node, _script_argument(name, args), caller_uid, line, file, extensionless=True)
        _emit_module_run(name, args, caller_uid, line, file)
    elif name == "trap" and args:
        _emit_registered(_FUNCTION_WORD_RE.findall(args[0]), caller_uid, line, file)
    elif name == "uv" and args[:1] == ["run"]:
        handle_words(node, _after_uv_run(args[1:]), caller_uid, file)
    elif name in _PACKAGE_RUNNERS:
        handle_words(node, _drop_leading_flags(args), caller_uid, file)
    elif name in ("pnpm", "yarn", "npm") and args[:1] in (["exec"], ["dlx"]):
        handle_words(node, _drop_leading_flags(args[1:]), caller_uid, file)
    elif name in ("pnpm", "yarn") and args[:1] and args[0] in _JS_RUNNERS:
        handle_words(node, args, caller_uid, file)
    elif "/" in name or name.endswith(_SHELL_SUFFIXES):
        _emit_run(node, name, caller_uid, line, file, extensionless=True)
    else:
        _emit_function_call(name, caller_uid, line, file)


def handle_declaration(node: Any, text_of: Any, caller_uid: str, file: ShellFile) -> None:
    """`export -f greet` makes the function a dependency of the script."""
    words = text_of(node).split()
    if words[:2] == ["export", "-f"]:
        _emit_registered(words[2:], caller_uid, node.start_point[0] + 1, file)


def handle_words(node: Any, words: list[str], caller_uid: str, file: ShellFile) -> None:
    """Re-dispatch the tail of a runner command (`uv run python x.py`) as its own command."""
    if not words:
        return
    name, args = words[0], words[1:]
    line = node.start_point[0] + 1
    if name in _SHELLS or name in _JS_RUNNERS or _is_python(name):
        _emit_run(node, _script_argument(name, args), caller_uid, line, file, extensionless=True)
        _emit_module_run(name, args, caller_uid, line, file)
    elif "/" in name or name.endswith(_RUNNABLE_SUFFIXES + _SHELL_SUFFIXES):
        # `uv run tools/report.py` runs the script with the project's Python.
        _emit_run(node, name, caller_uid, line, file)


def _emit_sources(node: Any, args: list[str], line: int, file: ShellFile) -> None:
    targets = _expand_all(node, args[0], file) if args else []
    if not targets:
        targets = list(file.directives.get(line - 1, []))
    for expanded in targets:
        resolved = resolve(file.path, expanded, file.root)
        if resolved is not None:
            path, anchored = resolved
            _add_edge(
                file,
                file.module_uid,
                f"code:file:{path}",
                "imports",
                SOURCE_CONFIDENCE[anchored],
                "shell_source",
                line,
            )


def _emit_run(
    node: Any,
    target: str,
    caller_uid: str,
    line: int,
    file: ShellFile,
    *,
    extensionless: bool = False,
) -> None:
    if not target:
        return
    for expanded in _expand_all(node, target, file):
        # Checked after expansion: `"$HELPER"` only shows its `.py` once the
        # variable it names is substituted.
        suffixed = expanded.endswith(_RUNNABLE_SUFFIXES + _SHELL_SUFFIXES)
        if not suffixed and not (extensionless and not PurePosixPath(expanded).suffix):
            continue
        resolved = resolve(file.path, expanded, file.root)
        if resolved is None or resolved[0] == file.path:
            continue
        path, anchored = resolved
        # An extensionless target is a script only when its shebang says so,
        # which is also what makes the walk index it.
        if not suffixed and (file.root is None or not is_shell_script(file.root / path)):
            continue
        # A file this script already sources is a dependency once, not twice.
        if (file.module_uid, f"code:file:{path}", "imports") not in file.seen:
            _add_edge(
                file,
                caller_uid,
                f"code:file:{path}",
                "calls",
                RUN_CONFIDENCE[anchored],
                "shell_runs_file",
                line,
            )


def _emit_module_run(
    name: str, args: list[str], caller_uid: str, line: int, file: ShellFile
) -> None:
    if _is_python(name) and "-m" in args[:-1]:
        module = args[args.index("-m") + 1]
        if re.fullmatch(r"[A-Za-z_][\w.]*", module):
            _add_edge(
                file,
                caller_uid,
                f"code:module:{module}",
                "calls",
                MODULE_RUN_CONFIDENCE,
                "shell_runs_module",
                line,
            )


def _emit_function_call(name: str, caller_uid: str, line: int, file: ShellFile) -> None:
    if name in file.local_functions:
        target = file.local_functions[name]
        if target != caller_uid:
            _add_edge(
                file, caller_uid, target, "calls", LOCAL_CALL_CONFIDENCE, "shell_local_call", line
            )
    elif _FUNCTION_NAME_RE.match(name) and name not in _BUILTINS:
        _add_edge(
            file,
            caller_uid,
            f"{SHELL_FUNCTION_STUB}{name}",
            "calls",
            FUNCTION_STUB_CONFIDENCE,
            "shell_external_command",
            line,
        )


def _emit_registered(names: list[str], caller_uid: str, line: int, file: ShellFile) -> None:
    # `trap cleanup EXIT` and `export -f greet` hand a function over to run
    # later by name; without the edge it read as dead code.
    for name in names:
        target = file.local_functions.get(name)
        if target is not None and target != caller_uid:
            _add_edge(
                file,
                caller_uid,
                target,
                "dispatches",
                LOCAL_CALL_CONFIDENCE,
                "shell_registers_function",
                line,
            )


def _add_edge(
    file: ShellFile,
    source: str,
    target: str,
    edge_type: str,
    confidence: float,
    signal: str,
    line: int,
) -> None:
    key = (source, target, edge_type)
    if key in file.seen:
        return
    file.seen.add(key)
    file.result.edges.append(
        GraphEdge(
            source_uid=source,
            target_uid=target,
            edge_type=edge_type,
            extractor=EXTRACTOR_ID,
            confidence=confidence,
            source_span=f"{file.path}:{line}",
            evidence=(EvidenceSignal(signal, confidence),),
        )
    )


def _expand_all(node: Any, text: str, file: ShellFile) -> list[str]:
    readings: list[str] = []
    for binding in _loop_bindings(node, file):
        readings.extend(file.scope.expand_all(text, extra=binding))
    return readings


def _loop_bindings(node: Any, file: ShellFile) -> list[dict[str, str]]:
    loops: list[tuple[str, list[str]]] = []
    current = node.parent
    while current is not None:
        loop = file.loops.get((current.start_byte, current.end_byte))
        if loop is not None:
            loops.append(loop)
        current = current.parent
    if not loops:
        return [{}]
    names = [name for name, _ in loops]
    return [dict(zip(names, values, strict=True)) for values in product(*(w for _, w in loops))]


def _command_words(node: Any, text_of: Any) -> list[str]:
    # Quotes never change a path, and `"$DIR"/x.sh` is one word to the shell.
    name = node.child_by_field_name("name")
    if name is None:
        return []
    arguments = node.children_by_field_name("argument")
    return [text_of(part).replace('"', "").replace("'", "") for part in (name, *arguments)]


def _strip_wrappers(words: list[str]) -> list[str]:
    while words and words[0] in _WRAPPERS:
        wrapper, words = words[0], words[1:]
        if wrapper == "command" and words[:1] in (["-v"], ["-V"]):
            return []
        value_flags = _WRAPPER_VALUE_FLAGS.get(wrapper, frozenset())
        while words and (
            words[0].startswith("-") or "=" in words[0] or _DURATION_RE.match(words[0])
        ):
            words = words[2:] if words[0] in value_flags else words[1:]
    return words


def _after_uv_run(args: list[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 2 if args[index] in _UV_VALUE_FLAGS else 1
    return args[index:]


def _script_argument(runner: str, args: list[str]) -> str:
    if runner in ("bun", "deno") and args[:1] == ["run"]:
        args = args[1:]
    kind = "python" if _is_python(runner) else "node" if runner in _JS_RUNNERS else "shell"
    value_flags, code_flags = _RUNNER_FLAGS[kind]
    index = 0
    while index < len(args):
        if args[index] in code_flags:
            return ""
        if not args[index].startswith("-"):
            return args[index]
        index += 2 if args[index] in value_flags else 1
    return ""


def _drop_leading_flags(args: list[str]) -> list[str]:
    index = 0
    while index < len(args) and args[index].startswith("-"):
        index += 1
    return args[index:]


def _is_python(name: str) -> bool:
    return bool(_PYTHON_RE.match(name) or _PYTHON_VARIABLE_RE.match(name))


def collect_directives(root: Any, text_of: Any) -> dict[int, list[str]]:
    """`# shellcheck source=` directives keyed by the line they sit on."""
    directives: dict[int, list[str]] = {}
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "comment":
            paths = directive_paths(text_of(node))
            if paths:
                directives[node.start_point[0] + 1] = paths
        stack.extend(node.children)
    return directives
