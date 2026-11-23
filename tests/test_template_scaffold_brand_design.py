"""brand-design: a non-code stack (docs/playbooks/template-authoring.md § Non-code stacks)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli._init_preview import _scaffold_tree_preview
from cli.main import cli
from cli.stack_lint import lint_all

pytestmark = pytest.mark.slow  # scaffolds sandboxes

SOFTWARE_ONLY_DOCS = (
    "docs/_meta/feature-dependency-tree.md",
    "docs/api-contracts/00-index.md",
    "docs/architecture/adr/00-index.md",
    "docs/engineering/00-index.md",
    "docs/insights/00-index.md",
    "docs/ops/runbooks/00-index.md",
    "docs/governance/risk-register.md",
    "docs/governance/_templates/runbook-template.md",
    "docs/playbooks/security-review.md",
    "src/shared/README.md",
)
BRAND_INDEXES = ("docs/00-index.md", "docs/_meta/foundation-map.md", "docs/playbooks/00-index.md")
_LINK_RE = re.compile(r"\]\(([^)#\s]+)")
_REF_TARGET_RE = re.compile(r"→ `(\.{1,2}/[^`]+)`")


def _init(root: Path, *templates: str) -> Path:
    project = root / "proj"
    project.mkdir()
    args = [
        "init",
        "--agent",
        "claude",
        "-d",
        str(project),
        "--no-git",
        "--no-index",
        "--no-register",
    ]
    for template in templates:
        args += ["-t", template]
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    return project


@pytest.fixture(scope="module")
def brand_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _init(tmp_path_factory.mktemp("brand"), "brand-design")


def test_ships_no_software_docs(brand_project: Path) -> None:
    assert [rel for rel in SOFTWARE_ONLY_DOCS if (brand_project / rel).exists()] == []
    assert not (brand_project / "src").exists()


def test_ships_the_brand_ssot_and_asset_folders(brand_project: Path) -> None:
    assert (brand_project / "docs/brand.md").is_file()
    assert (brand_project / "assets/reference/.gitignore").is_file()
    assert (brand_project / "assets/generated/.gitignore").is_file()
    assert (brand_project / "assets/export").is_dir()


@pytest.mark.parametrize("index", BRAND_INDEXES)
def test_every_index_link_resolves(brand_project: Path, index: str) -> None:
    path = brand_project / index
    text = path.read_text(encoding="utf-8")
    targets = _LINK_RE.findall(text) + _REF_TARGET_RE.findall(text)
    dangling = [t for t in targets if not (path.parent / t).exists()]
    assert targets and dangling == []


def test_board_and_verify_are_brand_only(brand_project: Path) -> None:
    board = yaml.safe_load((brand_project / ".coding-os/scrumban-config.yaml").read_text())
    assert [lane["id"] for lane in board["swimlanes"]] == ["brand", "design", "channels", "tooling"]
    assert "replace_keys" not in board
    config = yaml.safe_load((brand_project / ".coding-os.yaml").read_text())
    assert config["verify"] == {"docs": "make docs-lint"}


def test_agents_md_carries_the_brand_sections(brand_project: Path) -> None:
    agents = (brand_project / "AGENTS.md").read_text(encoding="utf-8")
    assert "Stack: Brand & design (no application code)." in agents
    assert "## Project Rules" in agents
    assert "`docs/brand.md`" in agents
    assert "src/shared/contracts" not in agents
    assert "| (none) |" not in agents


def test_production_rules_live_only_in_the_brand_ssot(brand_project: Path) -> None:
    rule = "Raster art (photos, illustrations, backdrops)"
    assert rule not in (brand_project / "AGENTS.md").read_text(encoding="utf-8")
    assert rule in (brand_project / "docs" / "brand.md").read_text(encoding="utf-8")
    assert "§ Production rules" in (brand_project / "AGENTS.md").read_text(encoding="utf-8")


def test_preview_matches_the_exclusions() -> None:
    paths, _ = _scaffold_tree_preview(("brand-design",))
    assert "docs/brand.md" in paths
    assert [rel for rel in SOFTWARE_ONLY_DOCS if rel in paths] == []


def test_a_code_stack_alongside_keeps_the_software_docs(tmp_path: Path) -> None:
    project = _init(tmp_path, "brand-design", "python")
    assert (project / "docs/api-contracts/00-index.md").is_file()
    assert "## API Contracts" in (project / "docs/00-index.md").read_text(encoding="utf-8")
    assert (project / "docs/brand.md").is_file()


def test_factory_lint_passes() -> None:
    report = lint_all()["brand-design"]
    assert report.passed, report.hard
