# Splitting a File Without Breaking It

Depth behind [clean-code](../SKILL.md) §4 "File Design". The SKILL states the
budgets and the cohesion rule; this file is the procedure for the moment you
actually move code — read it *before* the first cut, not after the suite goes
red.

## Find the seam by asking what changes together

| Seam | Split into |
|---|---|
| Public surface vs implementation | facade module + private `_impl` siblings |
| Independent feature groups | one module per group, re-exported from the facade |
| Shared helpers pulled by both | a leaf `_shared` module that imports neither |

Keep the facade's importable names identical so callers, tests, and
monkeypatches never notice — a split that changes the public surface is a
refactor plus a breaking change, and should not be one commit.

## A split changes six resolution mechanisms at once

No linter sees any of them. Verify each by executing, not by reading:

| Mechanism | How it breaks | Check |
|---|---|---|
| Import binding | flat vs package vs path-loaded imports resolve differently | run each entry point |
| Monkeypatch target | the moved function reads its OWN module globals, so a patch on the facade misses half the call sites | have siblings call facade helpers through the module object |
| Decorator registration | an ImportError silently drops a command or route — no crash, no failing test | count registered commands/routes before and after |
| Test fixtures | a split test file loses its `conn`-style fixtures, reported only at run time | run the suite, not just collection |
| Derived artifacts | openapi.json, generated types, golden snapshots drift | regenerate and re-check |
| Statement order | a module-level side effect (`if __name__`, router include, cache priming) left above an appended registration block runs too early | invoke the delivered entry point, not an import |

There is a seventh that lives outside the language: **literal filenames in CI
config, the Makefile, and scan-ignore lists**. Renaming a test module leaves a
green local run and a red CI job pointing at a path that no longer exists —
grep the repo for the old basename before committing.

Module-level state must move **with** the function that declares `global` on it
— an AST scan reports nothing, because `global x` marks the name local.
Anything two siblings need goes in a leaf module that imports neither.

## Then prove the move was a move

A suite can stay green while a moved body quietly lost a line: a dropped
`return` on a `-> dict` function made every caller compare `None != None`, and
`cos doctor` reported a broken adapter as healthy. One command, seconds not
minutes:

```bash
uv run python src/scripts/check_split_parity.py <pre-split-ref> <old-path> <package-dir>
```

It reports any function that vanished or whose body is no longer
byte-identical. Pass the **directory** so nothing is missed. Deliberate edits
are reported too — that is correct: land them as their own commit, never inside
the move.

## The companion budgets — a file rule alone is gameable

A 280-line file holding one 230-line function passes every file check and is
still unmaintainable. Four budgets carry equal weight, and the *tightest* one
that trips is the one to act on:

| Budget | Limit | Enforced by |
|---|---|---|
| File length | 500 (see the tiers in the SKILL) | `block-bad-patterns.sh`, `make check-file-size`, CI ratchet |
| Function length | ~20 lines; 50 is the hard smell | review + `PLR0915` (statements) |
| Cyclomatic complexity | 10 preferred, 20 hard | ruff `C901`, `PLR0912` (branches) |
| Parameters | 3-4; use an options object beyond | ruff `PLR0913` |
| Module dependencies | if a file imports from >6 sibling modules, it is probably a coordinator that should delegate | review |

Ruff carries a per-file baseline for the first four in `pyproject.toml`; it may
only shrink. A new violation is a design signal, not a number to baseline away.
