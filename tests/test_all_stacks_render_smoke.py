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
    assert len(STACK_IDS) >= 10, f"only {len(STACK_IDS)} stacks discovered — registry load broken"


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


def test_disabling_module_drops_its_retrieval_routing_row() -> None:
    """Audit F2: a disabled module's retrieval-routing row (and its docs-specific
    freshness prose) drop, the table stays Jinja-clean, and OTHER modules' rows
    survive. Asserts on row-unique phrases, not tool names (which legitimately
    recur in other fragments — full per-module prose gating is out of scope here)."""
    world = _build_world("claude", ("python",), _PROJECT, today=_FIXED_DATE)
    enabled = render_agents_md(world)
    no_docs = render_agents_md(world, active_modules={"docs": False})
    no_mem = render_agents_md(world, active_modules={"memory": False})

    assert "Embedding index finds chunks" in enabled  # docs row present by default
    assert "Embedding index finds chunks" not in no_docs, "docs off drops its row + freshness prose"
    assert "5-signal ranking + spaced repetition" not in no_mem, (
        "memory off drops its retrieval row"
    )
    # Cross-module isolation: turning docs off must NOT drop the memory/tasks rows.
    assert "5-signal ranking + spaced repetition" in no_docs
    assert "dependency JSON walks" in no_docs
    assert not _JINJA_DELIMITER.findall(no_docs)
    assert not _JINJA_DELIMITER.findall(no_mem)


def test_disabling_module_drops_core_loop_and_handoff_tool_refs() -> None:
    """Audit B-5/B-6 (RGC-B): the Core-Loop + Session-Handoff tool references must
    track their owning module, so a disabled subsystem is never commanded by the
    rendered AGENTS.md while its MCP surface is gated off. memory off ⇒ Memory
    Check + cos_learn_* gone; observability off ⇒ cos_metric_record gone; each
    leaves the other module's refs intact."""
    world = _build_world("claude", ("python",), _PROJECT, today=_FIXED_DATE)
    enabled = render_agents_md(world)
    no_mem = render_agents_md(world, active_modules={"memory": False})
    no_obs = render_agents_md(world, active_modules={"observability": False})

    assert "Memory Check" in enabled and "cos_metric_record" in enabled
    # memory off: its Core-Loop step + learn refs drop; observability ref survives
    assert "Memory Check" not in no_mem, "memory off must drop the Core-Loop Memory Check"
    assert "cos_learn_extract" not in no_mem and "cos_learn_narrative" not in no_mem
    assert "cos_metric_record" in no_mem, "observability ref must survive memory off"
    # observability off: metric ref drops; memory refs survive
    assert "cos_metric_record" not in no_obs, "observability off must drop cos_metric_record"
    assert "Memory Check" in no_obs and "cos_learn_extract" in no_obs
    assert not _JINJA_DELIMITER.findall(no_mem)
    assert not _JINJA_DELIMITER.findall(no_obs)
