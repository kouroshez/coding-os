# Python Library / CLI Playbook

Project: {{PROJECT_NAME}} · Stack: {{STACK}} · Updated: {{DATE}}

## When to use

Use this playbook for any task that creates or modifies Python modules,
CLI commands, or MCP tools in this project — packaging, public API shape,
and test layout decisions all route here.

## Always read

1. `docs/engineering/python-rules.md` — canonical Python policy for this project
2. `AGENTS.md` § critical rules — workflow contract

## Recipe — add a module / public function

1. Place code under the package root (`src/<package>/`); never grow a flat
   `utils.py` — name modules by domain.
2. Public API is exported explicitly (`__all__` or package `__init__`);
   everything else is private by underscore convention.
3. Type-hint every public signature; run the project's type checker if configured.
4. Write the test FIRST for bug fixes (red → green) and alongside for features:
   `tests/test_<module>.py`, mirroring the package layout.

## Recipe — add a CLI command

1. One command = one function with explicit params; parse with the project's
   CLI framework (argparse/click/typer) — never `sys.argv` by hand.
2. Errors exit non-zero with an actionable one-line message on stderr.
3. Cover happy path + each error path with CliRunner-style tests.

## Verify

`pytest tests/ -q` for the touched module (targeted file first, then the suite).
