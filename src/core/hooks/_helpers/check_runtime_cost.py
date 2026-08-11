"""Warn-tier detector for the runtime-cost shapes an AST can see with certainty.

Reads pending Python source on stdin, prints one warning line per finding to
stdout, and always exits 0 — the caller decides what to do with the text. Only
Python is parsed: a regex pass over TypeScript flagged legitimate small-n loops,
and a gate that cries wolf gets routed around. Critical Rule 27.
"""

from __future__ import annotations

import ast
import sys

IO_CALL_ATTRIBUTES = frozenset(
    {
        "execute",
        "executemany",
        "executescript",
        "fetchone",
        "fetchall",
        "fetchmany",
        "check_output",
        "check_call",
        "urlopen",
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
    }
)

IO_CALL_DOTTED = frozenset(
    {
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_output",
        "subprocess.check_call",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.delete",
        "httpx.get",
        "httpx.post",
    }
)

LOOP_NODES = (ast.For, ast.AsyncFor, ast.While)

INLINE_LIST_SCAN_FLOOR = 8

DEPTH_HINT = "  Depth: src/core/skills/clean-code/references/algorithmic-efficiency.md"
SMALL_N_ESCAPE = "  If n is genuinely small (<=100) this is fine — the budget cuts both ways."


def _dotted_name(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _list_valued_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        value = node.value
        is_list = isinstance(value, (ast.List, ast.ListComp)) or (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id in {"list", "sorted"}
        )
        if not is_list:
            continue
        names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return names


def _io_calls_in(loop: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(loop):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted_name(node.func)
        attribute = node.func.attr if isinstance(node.func, ast.Attribute) else ""
        if dotted in IO_CALL_DOTTED or attribute in IO_CALL_ATTRIBUTES:
            found.append((node.lineno, dotted or attribute))
    return found


def _list_membership_in(loop: ast.AST, list_names: set[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(loop):
        if not isinstance(node, ast.Compare):
            continue
        for operator, comparator in zip(node.ops, node.comparators, strict=True):
            if not isinstance(operator, (ast.In, ast.NotIn)):
                continue
            if isinstance(comparator, ast.Name) and comparator.id in list_names:
                found.append((node.lineno, comparator.id))
            elif isinstance(comparator, ast.List) and len(comparator.elts) > INLINE_LIST_SCAN_FLOOR:
                found.append((node.lineno, "an inline list literal"))
    return found


def _string_concat_in(loop: ast.AST) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(loop)
        if isinstance(node, ast.AugAssign)
        and isinstance(node.op, ast.Add)
        and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.JoinedStr)
    ]


def collect_warnings(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    list_names = _list_valued_names(tree)
    warnings: set[str] = set()

    for loop in (node for node in ast.walk(tree) if isinstance(node, LOOP_NODES)):
        for line, name in _io_calls_in(loop):
            warnings.add(
                f"  line {line}: `{name}(...)` runs inside a loop — the N+1 shape, "
                "costing n x round-trip. Batch it into one call, or hoist it out."
            )
        for line, name in _list_membership_in(loop, list_names):
            warnings.add(
                f"  line {line}: membership test against `{name}` inside a loop scans "
                "linearly — the pair is O(n x m). Build a set/dict once above the loop."
            )
        for line in _string_concat_in(loop):
            warnings.add(
                f"  line {line}: `+=` string accumulation inside a loop copies the "
                "accumulator each pass. Collect into a list and join once."
            )

    return sorted(warnings)


def main() -> int:
    warnings = collect_warnings(sys.stdin.read())
    if warnings:
        print("Runtime-cost shapes detected (Critical Rule 27, clean-code section 8):")
        print("\n".join(warnings))
        print(SMALL_N_ESCAPE)
        print(DEPTH_HINT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
