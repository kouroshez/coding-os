"""
Tests for Phase A — Template Completion.

Verifies that `coding-os init` produces a complete production-grade scaffold
with governance, playbooks, engineering rules, foundation map, and resolved
AGENTS.md placeholders.

Covers:
  - Generic _base scaffold (governance, PRD/architecture/api-contracts/ops indexes)
  - Django stack overlay (backend playbook, backend-rules, etc.)
  - Next.js stack overlay (frontend playbook, design system, etc.)
  - Multi-template merge (django + nextjs)
  - AGENTS.md placeholder substitution (no `{{...}}` left after init)
  - Stack-specific Makefile targets reachable
  - Workflow docs copied (thinking_os-final-edition.md from core/docs/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

# Make cli module importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.main import cli

pytestmark = pytest.mark.slow  # whole file scaffolds sandboxes / spawns subprocesses


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Return a clean temporary project directory."""
    target = tmp_path / "test-project"
    target.mkdir()
    return target


def _init_project(
    runner: CliRunner,
    project_dir: Path,
    *templates: str,
    agent: str = "claude",
) -> None:
    """Run `coding-os init` and assert success."""
    args = ["init", "--agent", agent, "-d", str(project_dir)]
    for tpl in templates:
        args += ["-t", tpl]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"init failed: {result.output}"


def _class_scaffold(tmp_path_factory: pytest.TempPathFactory, name: str, *templates: str) -> Path:
    """Scaffold one cos-init project shared across a class of read-only tests.

    Class-scoped fixtures run before the function-scoped _isolate_registry
    autouse fixture, so this re-isolates COS_REGISTRY_PATH itself via a
    standalone MonkeyPatch — otherwise `cos init` would write the real
    ~/.coding-os/registry.json.
    """
    base = tmp_path_factory.mktemp(name)
    project = base / "test-project"
    project.mkdir()
    mp = pytest.MonkeyPatch()
    mp.setenv("COS_REGISTRY_PATH", str(base / "registry.json"))
    try:
        _init_project(CliRunner(), project, *templates)
    finally:
        mp.undo()
    return project


# ---------------------------------------------------------------------------
# Base scaffold (every init creates these)
# ---------------------------------------------------------------------------


_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "templates"


def _stack_dirs() -> list[Path]:
    return [
        d
        for d in sorted(_TEMPLATES_DIR.iterdir())
        if d.is_dir() and d.name != "_base" and (d / "stack.yaml").exists()
    ]


def test_every_dimension_read_file_resolves() -> None:
    # D2-F1: a stack's dimensions[].read_files must resolve in that stack's
    # scaffold OR _base's scaffold — no dangling Read List entries (the
    # go-fiber security-review.md class of bug).
    base_scaffold = _TEMPLATES_DIR / "_base" / "scaffold"
    repo_root = _TEMPLATES_DIR.parent.parent
    dangling: list[str] = []
    for stack in _stack_dirs():
        spec = yaml.safe_load((stack / "stack.yaml").read_text(encoding="utf-8")) or {}
        # `meta` is the dogfood stack — its read_files point at the live repo
        # (docs/, src/core/), not a scaffold tree; resolve those at repo root.
        bases = [repo_root] if stack.name == "meta" else [stack / "scaffold", base_scaffold]
        for dim in spec.get("dimensions", []) or []:
            for rf in dim.get("read_files", []) or []:
                if not any((b / rf).exists() for b in bases):
                    dangling.append(f"{stack.name}:{dim.get('name')} -> {rf}")
    assert not dangling, "Dangling dimension read_files:\n" + "\n".join(dangling)


def test_no_engineering_doc_filename_collision_across_stacks() -> None:
    # D2-F4: two stacks must not ship the same docs/engineering/*.md filename —
    # `cos add-stack` of a second stack would overwrite the first's copy
    # (the accessibility-checklist.md collision). Shared docs belong in _base.
    seen: dict[str, str] = {}
    collisions: list[str] = []
    for stack in _stack_dirs():
        eng = stack / "scaffold" / "docs" / "engineering"
        if not eng.is_dir():
            continue
        for md in sorted(eng.glob("*.md")):
            if md.name in seen:
                collisions.append(f"{md.name}: {seen[md.name]} vs {stack.name}")
            else:
                seen[md.name] = stack.name
    assert not collisions, "Colliding engineering doc filenames across stacks:\n" + "\n".join(
        collisions
    )


class TestTagDrivenDocs:
    def test_default_scaffold_strips_tags_and_keeps_everything(self, tmp_path):
        from click.testing import CliRunner

        from cli.main import cli

        project = tmp_path / "alltags"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        vision = (project / "docs" / "prd" / "01-snapshot-vision.md").read_text(encoding="utf-8")
        index = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        lifecycle = (project / "docs" / "governance" / "task-lifecycle.md").read_text(
            encoding="utf-8"
        )
        assert "[PRD Index](./prd/00-index.md)" in index  # gated link present by default
        for rendered in (vision, index, lifecycle):
            assert "module:" not in rendered.split("\n")[0]  # tag stripped from header
            assert "if-module" not in rendered and "end-if" not in rendered  # markers stripped

    def test_docs_module_disabled_drops_tagged_tree_and_index_link(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        import cli.subsystems as subsystems_module
        from cli.main import cli
        from cli.subsystems import load_subsystems

        # Docs (and its dependent tasks) disabled before the scaffold copy —
        # the wizard/preset path writes this state pre-overlay.
        def _docs_off(project_root, modules=None):
            modules = modules or load_subsystems()
            return {mid: mid not in {"docs", "tasks"} for mid in modules}

        monkeypatch.setattr(subsystems_module, "module_state", _docs_off)

        project = tmp_path / "nodocs"
        project.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "init",
                "--agent",
                "claude",
                "-d",
                str(project),
                "--yes",
                "--no-index",
                "--no-register",
            ],
        )
        assert result.exit_code == 0, result.output
        assert not (project / "docs" / "prd" / "01-snapshot-vision.md").exists()
        assert not (project / "docs" / "prd" / "00-index.md").exists()
        assert not (project / "docs" / "governance" / "task-lifecycle.md").exists()
        index = (project / "docs" / "00-index.md").read_text(encoding="utf-8")
        assert "[PRD Index]" not in index  # no dangling link
        assert "[Risk Register]" in index  # untagged kernel docs remain

    def test_stack_conditional_blocks_render_both_branches(self):
        from cli.main import _apply_doc_conditions

        doc = (
            "<!-- domain:X | layer:y | updated:1 -->\n"
            "intro\n"
            "<!-- if-stack:go-fiber,fastapi -->\n"
            "backend guidance\n"
            "<!-- end-if -->\n"
            "outro\n"
        )
        skip, with_stack = _apply_doc_conditions(doc, set(), {"go-fiber"})
        assert skip is False
        assert "backend guidance" in with_stack and "if-stack" not in with_stack

        skip, without_stack = _apply_doc_conditions(doc, set(), {"nextjs"})
        assert skip is False
        assert "backend guidance" not in without_stack
        assert "intro" in without_stack and "outro" in without_stack

    def test_module_block_and_file_tag_semantics(self):
        from cli.main import _apply_doc_conditions

        tagged = "<!-- domain:X | module:docs -->\nbody\n"
        assert _apply_doc_conditions(tagged, {"docs"}, set()) == (True, "")
        skip, kept = _apply_doc_conditions(tagged, set(), set())
        assert skip is False and "module:docs" not in kept and "body" in kept

        block = "head\n<!-- if-module:tasks -->\ntask hint\n<!-- end-if -->\ntail\n"
        _, disabled = _apply_doc_conditions(block, {"tasks"}, set())
        assert "task hint" not in disabled
        _, enabled = _apply_doc_conditions(block, set(), set())
        assert "task hint" in enabled
