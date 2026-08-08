"""Tests for core.board_os.config — scrumban-config.yaml schema."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    STATUS_ENUM,
    ConfigValidationError,
    ScrumbanConfig,
    WipLimits,
    load_config,
    parse_config,
)

# ---------------------------------------------------------------------------
# Closed enums
# ---------------------------------------------------------------------------


def test_kind_enum_is_eight_values_in_fixed_order():
    assert KIND_ENUM == (
        "feature",
        "bug",
        "chore",
        "spike",
        "docs",
        "refactor",
        "test",
        "security",
    )


def test_status_enum_has_seven_workflow_columns():
    """'ready' was folded into a label on icebox rows — seven columns remain."""
    assert set(STATUS_ENUM) == {
        "icebox",
        "emergency",
        "in_progress",
        "testing",
        "complete",
        "blocked",
        "archive",
    }


def test_priority_enum_p0_to_p3():
    assert PRIORITY_ENUM == ("P0", "P1", "P2", "P3")


# ---------------------------------------------------------------------------
# Appetite regex
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["30m", "1h", "2h", "1d", "3d", "1w", "2w", "1cy", "6w", "12h"],
)
def test_appetite_accepts_valid(value: str):
    assert APPETITE_RE.match(value)


@pytest.mark.parametrize(
    "value",
    ["", "1", "1y", "1.5d", "30 m", "h", "1mo", "P1", "1q"],
)
def test_appetite_rejects_invalid(value: str):
    assert APPETITE_RE.match(value) is None


# ---------------------------------------------------------------------------
# parse_config — happy path
# ---------------------------------------------------------------------------


def _minimal_dict() -> dict:
    return {
        "swimlanes": [
            {"id": "backend", "label": "Backend", "color": "#3b82f6"},
        ],
    }


def test_parse_minimal_config():
    cfg = parse_config(_minimal_dict())
    assert isinstance(cfg, ScrumbanConfig)
    assert len(cfg.swimlanes) == 1
    assert cfg.swimlanes[0].id == "backend"
    assert cfg.wip_limits == WipLimits()  # defaults


def test_parse_config_with_all_fields():
    data = {
        "swimlanes": [
            {"id": "backend", "label": "Backend", "color": "#3b82f6", "description": "Server-side"},
            {"id": "frontend", "label": "Frontend", "color": "#22c55e"},
        ],
        "wip_limits": {"in_progress": 2, "testing": 5, "emergency": 3},
        "label_families": [
            {"name": "infra", "color": "#78716c", "emoji": "🟫"},
        ],
    }
    cfg = parse_config(data)
    assert len(cfg.swimlanes) == 2
    assert cfg.wip_limits.in_progress == 2
    assert cfg.wip_limits.testing == 5
    assert cfg.wip_limits.emergency == 3
    assert len(cfg.label_families) == 1
    assert cfg.label_families[0].name == "infra"


def test_swimlane_lookup_helpers():
    cfg = parse_config(_minimal_dict())
    assert cfg.swimlane_ids == {"backend"}
    assert cfg.get_swimlane("backend") is not None
    assert cfg.get_swimlane("frontend") is None


def test_kind_color_returns_stable_palette():
    cfg = parse_config(_minimal_dict())
    # All KIND_ENUM values must have a colour
    for kind in KIND_ENUM:
        c = cfg.kind_color(kind)
        assert c.startswith("#"), f"kind={kind} got non-hex {c!r}"
        assert len(c) == 7, f"kind={kind} got non-6-digit {c!r}"
    # Unknown kind falls back to gray (does NOT raise)
    assert cfg.kind_color("unknown-kind") == "#6b7280"


def test_wip_cap_for_each_column():
    cfg = parse_config(_minimal_dict())
    assert cfg.wip_limits.cap_for("in_progress") == 1
    assert cfg.wip_limits.cap_for("testing") == 3
    assert cfg.wip_limits.cap_for("emergency") == 2
    assert cfg.wip_limits.cap_for("icebox") is None
    assert cfg.wip_limits.cap_for("ready") is None


# ---------------------------------------------------------------------------
# parse_config — validation errors
# ---------------------------------------------------------------------------


def test_swimlanes_required_non_empty():
    with pytest.raises(ConfigValidationError) as exc:
        parse_config({"swimlanes": []})
    assert "swimlanes must be a non-empty list" in str(exc.value)


def test_swimlanes_must_be_list_not_mapping():
    with pytest.raises(ConfigValidationError):
        parse_config({"swimlanes": {"backend": "Backend"}})


def test_swimlane_id_must_match_id_regex():
    with pytest.raises(ConfigValidationError) as exc:
        parse_config({"swimlanes": [{"id": "Backend", "color": "#3b82f6"}]})
    assert "id" in str(exc.value)


def test_swimlane_color_must_be_hex():
    with pytest.raises(ConfigValidationError) as exc:
        parse_config({"swimlanes": [{"id": "x", "color": "blue"}]})
    assert "color" in str(exc.value)


def test_swimlane_color_3char_hex_accepted():
    cfg = parse_config({"swimlanes": [{"id": "x", "color": "#abc"}]})
    assert cfg.swimlanes[0].color == "#abc"


def test_duplicate_swimlane_ids_rejected():
    with pytest.raises(ConfigValidationError) as exc:
        parse_config(
            {
                "swimlanes": [
                    {"id": "a", "color": "#aaa"},
                    {"id": "a", "color": "#bbb"},
                ]
            }
        )
    assert "duplicated" in str(exc.value)


def test_wip_limits_must_be_int_non_negative():
    with pytest.raises(ConfigValidationError):
        parse_config(
            {
                "swimlanes": [{"id": "x", "color": "#aaa"}],
                "wip_limits": {"in_progress": -1},
            }
        )


def test_wip_limits_partial_override_uses_defaults_for_rest():
    cfg = parse_config(
        {
            "swimlanes": [{"id": "x", "color": "#aaa"}],
            "wip_limits": {"in_progress": 5},
        }
    )
    assert cfg.wip_limits.in_progress == 5
    assert cfg.wip_limits.testing == 3  # default
    assert cfg.wip_limits.emergency == 2  # default


def test_label_families_cannot_collide_with_kind_enum():
    """Critical: labels family `bug` would shadow kind=bug — rejected."""
    with pytest.raises(ConfigValidationError) as exc:
        parse_config(
            {
                "swimlanes": [{"id": "x", "color": "#aaa"}],
                "label_families": [{"name": "bug", "color": "#dc2626"}],
            }
        )
    assert "kind, not labels" in str(exc.value).lower() or "KIND_ENUM" in str(exc.value)


def test_multiple_errors_reported_together():
    with pytest.raises(ConfigValidationError) as exc:
        parse_config(
            {
                "swimlanes": [
                    {"id": "Bad-Cap", "color": "not-hex"},
                ],
            }
        )
    msg = str(exc.value)
    # Both id-shape AND color errors should appear in the same exception
    assert msg.count("- ") >= 2


# ---------------------------------------------------------------------------
# load_config — file I/O
# ---------------------------------------------------------------------------


def test_load_config_missing_file_raises_filenotfound(tmp_path: Path):
    with pytest.raises(FileNotFoundError) as exc:
        load_config(tmp_path)
    assert "scrumban-config.yaml not found" in str(exc.value)
    assert "cos board-config --init" in str(exc.value)


def test_load_config_round_trip(tmp_path: Path):
    cfg_dir = tmp_path / ".coding-os"
    cfg_dir.mkdir()
    (cfg_dir / "scrumban-config.yaml").write_text(yaml.safe_dump(_minimal_dict()), encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.swimlanes[0].id == "backend"
    assert (
        cfg.source_path == (cfg_dir / "scrumban-config.yaml").resolve()
        or cfg.source_path == cfg_dir / "scrumban-config.yaml"
    )


def test_load_config_top_level_must_be_mapping(tmp_path: Path):
    cfg_dir = tmp_path / ".coding-os"
    cfg_dir.mkdir()
    (cfg_dir / "scrumban-config.yaml").write_text("- not a mapping\n", encoding="utf-8")
    with pytest.raises(ConfigValidationError) as exc:
        load_config(tmp_path)
    assert "top-level YAML must be a mapping" in str(exc.value)


# ---------------------------------------------------------------------------
# Persian / RTL — R-L-22 fixture
# ---------------------------------------------------------------------------


def test_persian_label_in_swimlane_preserved(tmp_path: Path):
    """R-L-22: Persian labels survive UTF-8 round-trip."""
    data = {
        "swimlanes": [
            {"id": "backend", "label": "بک‌اند فارسی", "color": "#3b82f6"},
        ],
    }
    cfg_dir = tmp_path / ".coding-os"
    cfg_dir.mkdir()
    (cfg_dir / "scrumban-config.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    cfg = load_config(tmp_path)
    assert cfg.swimlanes[0].label == "بک‌اند فارسی"
