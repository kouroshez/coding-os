"""All shipped per-stack scrumban-config.yaml files must parse cleanly."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.board_os.config import parse_config


REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATES = REPO_ROOT / "templates"
META = REPO_ROOT / ".coding-os" / "scrumban-config.yaml"


def _all_shipped_configs() -> list[Path]:
    paths: list[Path] = [META]  # coding-os meta-project itself
    paths.append(TEMPLATES / "_base" / "scaffold" / ".coding-os" / "scrumban-config.yaml")
    for stack in ("django", "fastapi", "go", "go-fiber", "nextjs"):
        p = TEMPLATES / stack / "scaffold" / ".coding-os" / "scrumban-config.yaml"
        if p.exists():
            paths.append(p)
    return paths


@pytest.mark.parametrize(
    "config_path",
    _all_shipped_configs(),
    ids=lambda p: str(p.relative_to(REPO_ROOT)),
)
def test_shipped_config_parses_cleanly(config_path: Path):
    assert config_path.exists(), f"{config_path} missing"
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    cfg = parse_config(data, source_path=config_path)
    # Sanity: at least 2 swimlanes, includes infra or docs lane somewhere.
    assert len(cfg.swimlanes) >= 2
    ids = cfg.swimlane_ids
    assert "docs" in ids or "infra" in ids, (
        f"{config_path}: should include either 'docs' or 'infra' swimlane "
        f"by convention (got {sorted(ids)})"
    )


def test_meta_repo_has_board_os_swimlane():
    """coding-os itself must have a board_os lane to track Phase L slices."""
    data = yaml.safe_load(META.read_text(encoding="utf-8"))
    cfg = parse_config(data)
    assert "board_os" in cfg.swimlane_ids
    assert "graph_os" in cfg.swimlane_ids
    assert "thinking_os" in cfg.swimlane_ids


def test_django_has_backend_swimlane():
    p = TEMPLATES / "django" / "scaffold" / ".coding-os" / "scrumban-config.yaml"
    cfg = parse_config(yaml.safe_load(p.read_text(encoding="utf-8")))
    assert "backend" in cfg.swimlane_ids


def test_nextjs_has_frontend_swimlane():
    p = TEMPLATES / "nextjs" / "scaffold" / ".coding-os" / "scrumban-config.yaml"
    cfg = parse_config(yaml.safe_load(p.read_text(encoding="utf-8")))
    assert "frontend" in cfg.swimlane_ids


def test_all_configs_have_one_in_progress_wip_default():
    """Plan §3 P-L-4: solo-dev defense is in_progress=1 by default."""
    for path in _all_shipped_configs():
        cfg = parse_config(yaml.safe_load(path.read_text(encoding="utf-8")))
        assert cfg.wip_limits.in_progress == 1, (
            f"{path}: in_progress WIP must default to 1 "
            f"(perfectionism defense, P-L-4)"
        )
