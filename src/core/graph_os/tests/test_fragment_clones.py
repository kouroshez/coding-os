"""The fragment pass on its own: what it blanks, how a repeat splits, and its bounds."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from graph_os.tools import _graph_fragments
from graph_os.tools._graph_fragments import fragment_clones

BODY = """\
  const rows = items.filter((item) => item.active)
  let total = 0
  for (const row of rows) {
    total += row.price * row.quantity
    if (row.discount) total -= row.discount
  }
  const report = { total, count: rows.length, currency: "EUR" }
  return report
"""


def _write(root: Path, files: dict[str, str]) -> list[str]:
    for relative, text in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(text, encoding="utf-8")
    return list(files)


def _copies(found: list[dict]) -> list[set[tuple[str, tuple[int, int]]]]:
    return [{(m["file"], tuple(m["lines"])) for m in group["members"]} for group in found]


def test_an_exported_function_without_semicolons_keeps_its_body(tmp_path: Path):
    paths = _write(
        tmp_path,
        {
            "a.ts": "export function invoiceTotal(items) {\n" + BODY + "}\n",
            "b.ts": "export function cartTotal(items, user) {\n  log(user)\n" + BODY + "}\n",
        },
    )

    found, complete = fragment_clones(tmp_path, paths, {})

    assert complete
    assert {("a.ts", (2, 10)), ("b.ts", (3, 11))} in _copies(found)


def test_a_shared_import_list_is_no_fragment(tmp_path: Path):
    imports = "".join(f'import {{ helper{n}, other{n} }} from "./lib/m{n}"\n' for n in range(8))
    paths = _write(
        tmp_path,
        {"a.ts": imports + "export const a = 1\n", "b.ts": imports + "export const b = 2\n"},
    )

    assert fragment_clones(tmp_path, paths, {})[0] == []


def test_export_lines_without_a_quote_are_read_in_linear_time(tmp_path: Path):
    paths = _write(
        tmp_path, {"constants.ts": "".join(f"export const VALUE_{n} = {n}\n" for n in range(8000))}
    )

    started = time.monotonic()
    fragment_clones(tmp_path, paths, {})

    assert time.monotonic() - started < 2.0


def test_a_block_repeated_back_to_back_lists_every_copy(tmp_path: Path):
    block = "function step() {\n" + BODY + "}\n"
    paths = _write(tmp_path, {"steps.ts": "let ready = true\n" + block * 3})

    found, _ = fragment_clones(tmp_path, paths, {})

    assert len(found) == 1
    assert len(found[0]["members"]) == 3


def test_a_focus_keeps_only_copies_that_touch_it_and_is_read_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    other = """\
  const names = people.map((person) => person.name.trim()).filter(Boolean)
  const seen = new Set()
  for (const name of names) {
    if (seen.has(name)) console.warn("duplicate", name)
    seen.add(name.toLowerCase())
  }
  return { names: [...seen], size: seen.size, sorted: true }
"""
    paths = _write(
        tmp_path,
        {
            "app/page.ts": "export function page(items) {\n" + BODY + "}\n",
            "lib/copy.ts": "export function copy(items) {\n" + BODY + "}\n",
            "x/one.ts": "export function one(items) {\n" + other + "}\n",
            "x/two.ts": "export function two(items) {\n" + other + "}\n",
        },
    )

    found, complete = fragment_clones(tmp_path, paths, {}, focus={"app/page.ts"})

    assert complete
    assert [{file for file, _ in copy} for copy in _copies(found)] == [
        {"app/page.ts", "lib/copy.ts"}
    ]

    monkeypatch.setattr(_graph_fragments, "MAX_TOKENS", 100)
    found, complete = fragment_clones(tmp_path, paths, {}, focus={"x/two.ts"})

    assert not complete
    assert found == []
