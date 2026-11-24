"""A cache or bytecode a local tool run left in a template tree never reaches a project."""

from __future__ import annotations

import shutil
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
