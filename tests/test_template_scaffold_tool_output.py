"""A cache or bytecode a local tool run left in a template tree never reaches a project."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from cli import _init_scaffold
from cli._init_registries import TEMPLATES_DIR

PLANTED = (
    "scaffold/__pycache__/leftover.cpython-313.pyc",
    "scaffold/docs/.DS_Store",
    "lang/python/.ruff_cache/CACHEDIR.TAG",
    "lang/python/.pytest_cache/README.md",
    "scaffold/.env",
    "scaffold/.venv/pyvenv.cfg",
    "scaffold/node_modules/left/index.js",
)
TOOL_OUTPUT = {
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".DS_Store",
    ".env",
    ".venv",
    "node_modules",
}


def test_overlay_copies_no_tool_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    templates = tmp_path / "templates"
    shutil.copytree(
        TEMPLATES_DIR / "_base", templates / "_base", ignore=shutil.ignore_patterns(*TOOL_OUTPUT)
    )
    for planted in PLANTED:
        path = templates / "_base" / planted
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("left by a local run\n", encoding="utf-8")
    monkeypatch.setattr(_init_scaffold, "TEMPLATES_DIR", templates)
    project = tmp_path / "project"
    project.mkdir()

    _init_scaffold._overlay_scaffold(project, ("fastapi",), {})

    assert (project / "docs" / "00-index.md").is_file(), "overlay copied nothing"
    leaked = [str(p.relative_to(project)) for p in project.rglob("*") if p.name in TOOL_OUTPUT]
    assert leaked == []
    assert (project / "src" / "backend" / ".env.example").is_file(), ".env.example must ship"


def test_applying_a_template_keeps_no_copy_of_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _init_scaffold._get_stack_registry()
    stack = tmp_path / "fastapi"
    shutil.copytree(
        registry["fastapi"].source_dir, stack, ignore=shutil.ignore_patterns(*TOOL_OUTPUT)
    )
    skill = next(path for path in (stack / "skills").iterdir() if path.is_dir())
    for planted in (
        skill / "__pycache__" / "x.pyc",
        stack / "rules" / ".DS_Store",
        skill / ".venv" / "cfg",
    ):
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text("left by a local run\n", encoding="utf-8")
    patched = {**registry, "fastapi": replace(registry["fastapi"], source_dir=stack)}
    monkeypatch.setattr(_init_scaffold, "_get_stack_registry", lambda: patched)
    project = tmp_path / "project"
    project.mkdir()

    _init_scaffold._apply_template("fastapi", project, agent="claude")

    # No mirror under .coding-os/src, and only the stack's .md rules (this copy
    # lives outside the install, so they are copied like an overlay stack's).
    assert not (project / ".coding-os" / "src").exists()
    rules = [rule.name for rule in (project / ".claude" / "rules").iterdir()]
    assert rules == ["fastapi-backend.md"]
