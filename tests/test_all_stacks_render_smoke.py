"""All-stacks render smoke (audit-2026-06 R9, TASK-438).

For every registered stack, build the aggregated world and render AGENTS.md.
Asserts the render succeeds (StrictUndefined => no missing substitution key)
and leaves no surviving Jinja delimiters ({{ }} / {% %}) — the "a botched
re-render ships to every consumer" failure mode (audit failure-scenario #1).

Pure in-memory: _build_world reads only project.name, so no `cos init`
sandbox is needed. Fast + CI-gateable (NOT slow-marked, unlike the byte-exact
golden-parity suite).

Run: uv run pytest tests/test_all_stacks_render_smoke.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cli.main import _build_world, _get_stack_registry
from cli.renderer import render_agents_md

# Any unrendered Jinja delimiter surviving into the output is a render bug.
_JINJA_DELIMITER = re.compile(r"\{\{|\}\}|\{%|%\}")
# _build_world consumes only `.name`; the path need not exist on disk.
_PROJECT = Path("smoke-test-project")
_FIXED_DATE = "2026-01-01"  # deterministic; aggregate() is pure given `today`


def _stack_ids() -> list[str]:
    return sorted(_get_stack_registry().keys())


STACK_IDS = _stack_ids()


def test_stack_registry_nonempty() -> None:
    """Sanity: stacks must load, else the parametrize below is a silent no-op."""
    assert len(STACK_IDS) >= 10, (
        f"only {len(STACK_IDS)} stacks discovered — registry load broken"
    )


@pytest.mark.parametrize("stack_id", STACK_IDS)
def test_agents_md_renders_clean(stack_id: str) -> None:
    """Each stack renders AGENTS.md with no surviving Jinja delimiters."""
    world = _build_world("claude", (stack_id,), _PROJECT, today=_FIXED_DATE)
    rendered = render_agents_md(world)
    survivors = _JINJA_DELIMITER.findall(rendered)
    assert not survivors, (
        f"stack '{stack_id}': {len(survivors)} surviving Jinja delimiter(s) "
        f"in rendered AGENTS.md — a substitution or conditional did not resolve."
    )


def test_disabling_tasks_module_drops_its_agents_md_fragments() -> None:
    """Audit F2: disabling a module strips its AGENTS.md prose. Tasks off ⇒ the
    task-authoring + task-logging fragments are absent; on (default) ⇒ present.
    Byte-identity of the on-branch is guarded separately by golden-parity."""
    world = _build_world("claude", ("python",), _PROJECT, today=_FIXED_DATE)
    enabled = render_agents_md(world)
    disabled = render_agents_md(world, active_modules={"tasks": False})

    assert "## Task Authoring" in enabled and "## Task Logging" in enabled
    assert "## Task Authoring" not in disabled, "tasks off must drop task-authoring"
    assert "## Task Logging" not in disabled, "tasks off must drop task-logging"
    assert not _JINJA_DELIMITER.findall(disabled), "gate left a stray Jinja delimiter"
