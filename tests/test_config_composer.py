"""Unit tests for the data-driven config composer (config-composition.md)."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
import yaml

from cli.config_composer import (
    RAG_SPEC,
    SCRUMBAN_SPEC,
    compose,
    compose_coding_os_configs,
    recompose_for_added_stack,
    recompose_for_removed_stack,
)


def test_union_by_id_overrides_and_appends() -> None:
    base = {"swimlanes": [{"id": "backend", "label": "Backend"}, {"id": "docs", "label": "Docs"}]}
    overlay = {"swimlanes": [{"id": "backend", "label": "Django"}, {"id": "api", "label": "API"}]}
    out = compose(base, [overlay], SCRUMBAN_SPEC)
    by_id = {s["id"]: s["label"] for s in out["swimlanes"]}
    assert by_id == {"backend": "Django", "docs": "Docs", "api": "API"}  # override + keep + append


def test_sources_union_by_path() -> None:
    base = {"sources": [{"path": "docs/prd/", "type": "prd", "priority": 0.5}]}
    overlay = {
        "sources": [
            {"path": "docs/prd/", "type": "prd", "priority": 0.9},  # collision → override
            {"path": "docs/design/", "type": "design"},  # new → append
        ]
    }
    out = compose(base, [overlay], RAG_SPEC)
    by_path = {s["path"]: s.get("priority") for s in out["sources"]}
    assert by_path == {"docs/prd/": 0.9, "docs/design/": None}


def test_exclude_union_dedupes() -> None:
    base = {"sources": [], "exclude": ["docs/tasks/", "docs/_meta/"]}
    overlay = {"exclude": ["docs/_meta/", "docs/build/"]}
    out = compose(base, [overlay], RAG_SPEC)
    assert out["exclude"] == ["docs/tasks/", "docs/_meta/", "docs/build/"]


def test_graph_enforce_context_on_list_union() -> None:
    base = {"sources": [], "graph": {"enforce_context_on": ["*a.py"]}}
    overlay = {"graph": {"enforce_context_on": ["*a.py", "*b.tsx"]}}
    out = compose(base, [overlay], RAG_SPEC)
    assert out["graph"]["enforce_context_on"] == ["*a.py", "*b.tsx"]


def test_wip_limits_dict_scalar_override() -> None:
    base = {"swimlanes": [], "wip_limits": {"in_progress": 1, "testing": 3}}
    overlay = {"wip_limits": {"testing": 5}}
    out = compose(base, [overlay], SCRUMBAN_SPEC)
    assert out["wip_limits"] == {"in_progress": 1, "testing": 5}


def test_multi_stack_composition_order() -> None:
    base = {"swimlanes": [{"id": "docs", "label": "Docs"}]}
    s1 = {"swimlanes": [{"id": "frontend", "label": "FE"}]}
    s2 = {"swimlanes": [{"id": "backend", "label": "BE"}]}
    out = compose(base, [s1, s2], SCRUMBAN_SPEC)
    assert [s["id"] for s in out["swimlanes"]] == [
        "docs",
        "frontend",
        "backend",
    ]  # both stacks kept


def test_compose_coding_os_configs_writes_merged(tmp_path: Path) -> None:
    # Minimal fake templates tree: _base + one stack overlay.
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    stack = tdir / "mystack" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    stack.mkdir(parents=True)
    (base / "rag-config.yaml").write_text(
        yaml.safe_dump({"sources": [{"path": "docs/prd/", "type": "prd"}], "exclude": ["a"]}),
        encoding="utf-8",
    )
    (stack / "rag-config.yaml").write_text(
        yaml.safe_dump({"sources": [{"path": "docs/x/", "type": "x"}]}), encoding="utf-8"
    )

    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    written = compose_coding_os_configs(tmp_path / "proj", state, ["mystack"], templates_dir=tdir)
    assert "rag-config.yaml" in written
    merged = yaml.safe_load((state / "rag-config.yaml").read_text())
    paths = {s["path"] for s in merged["sources"]}
    assert paths == {"docs/prd/", "docs/x/"}  # base + stack merged


def test_compose_is_idempotent_never_clobbers(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    (base / "rag-config.yaml").write_text(yaml.safe_dump({"sources": []}), encoding="utf-8")
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    (state / "rag-config.yaml").write_text("USER EDITED\n", encoding="utf-8")
    written = compose_coding_os_configs(tmp_path / "proj", state, [], templates_dir=tdir)
    assert "rag-config.yaml" not in written
    assert (state / "rag-config.yaml").read_text() == "USER EDITED\n"  # untouched


def test_domain_config_json_roundtrip(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    stack = tdir / "s" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    stack.mkdir(parents=True)
    (base / "domain-config.json").write_text(
        json.dumps({"refs_by_tag": {"DOCS": ["a"]}, "default_domain": "ALL"}), encoding="utf-8"
    )
    (stack / "domain-config.json").write_text(
        json.dumps({"refs_by_tag": {"DOCS": ["b"], "MOBILE": ["m"]}}), encoding="utf-8"
    )
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    compose_coding_os_configs(tmp_path / "proj", state, ["s"], templates_dir=tdir)
    merged = json.loads((state / "domain-config.json").read_text())
    assert merged["refs_by_tag"]["DOCS"] == ["a", "b"]  # per-tag list union
    assert merged["refs_by_tag"]["MOBILE"] == ["m"]  # new tag
    assert merged["default_domain"] == "ALL"  # base scalar kept


def test_recompose_added_stack_preserves_prior_and_adds_new(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    go = tdir / "go" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    go.mkdir(parents=True)
    (base / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "docs", "label": "Docs"}]}), encoding="utf-8"
    )
    (go / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "backend", "label": "Go"}]}), encoding="utf-8"
    )
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    # existing composed config already has a prior stack's frontend lane
    (state / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {"swimlanes": [{"id": "docs", "label": "Docs"}, {"id": "frontend", "label": "FE"}]}
        ),
        encoding="utf-8",
    )
    recompose_for_added_stack(tmp_path / "proj", state, "go", templates_dir=tdir)
    merged = yaml.safe_load((state / "scrumban-config.yaml").read_text())
    ids = [s["id"] for s in merged["swimlanes"]]
    assert ids == ["docs", "frontend", "backend"]  # prior lanes kept + new stack appended


def test_recompose_removed_stack_drops_only_that_stacks_lanes(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    go = tdir / "go" / "scaffold" / ".coding-os"
    nextjs = tdir / "nextjs" / "scaffold" / ".coding-os"
    for d in (base, go, nextjs):
        d.mkdir(parents=True)
    (base / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "docs", "label": "Docs"}]}), encoding="utf-8"
    )
    (go / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "backend", "label": "Go"}]}), encoding="utf-8"
    )
    (nextjs / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "frontend", "label": "Next"}]}), encoding="utf-8"
    )
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    # Composed config currently reflects both go + nextjs installed.
    (state / "scrumban-config.yaml").write_text(
        yaml.safe_dump(
            {
                "swimlanes": [
                    {"id": "docs", "label": "Docs"},
                    {"id": "backend", "label": "Go"},
                    {"id": "frontend", "label": "Next"},
                ]
            }
        ),
        encoding="utf-8",
    )
    # Remove go → recompose from base + remaining (nextjs).
    written = recompose_for_removed_stack(tmp_path / "proj", state, ["nextjs"], templates_dir=tdir)
    assert "scrumban-config.yaml" in written
    merged = yaml.safe_load((state / "scrumban-config.yaml").read_text())
    ids = [s["id"] for s in merged["swimlanes"]]
    assert ids == ["docs", "frontend"]  # go's backend lane dropped; base + nextjs kept


def test_recompose_removed_stack_is_noop_when_unchanged(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    (base / "rag-config.yaml").write_text(
        yaml.safe_dump({"sources": [{"path": "docs/", "type": "prd"}]}), encoding="utf-8"
    )
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    # Already equals base + no stacks → recompose produces identical content.
    from cli.config_composer import _dump  # local: assert the no-op path

    (state / "rag-config.yaml").write_text(
        _dump({"sources": [{"path": "docs/", "type": "prd"}]}, "yaml"), encoding="utf-8"
    )
    written = recompose_for_removed_stack(tmp_path / "proj", state, [], templates_dir=tdir)
    assert written == []  # no rewrite when recompose matches the current file


def test_malformed_config_raises_clear_error(tmp_path: Path) -> None:
    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    (base / "rag-config.yaml").write_text("sources: [unclosed\n", encoding="utf-8")  # bad YAML
    state = tmp_path / "proj" / ".coding-os"
    state.mkdir(parents=True)
    with pytest.raises(click.ClickException) as exc_info:
        compose_coding_os_configs(tmp_path / "proj", state, [], templates_dir=tdir)
    assert "not valid YAML" in str(exc_info.value)  # clear message, not a raw traceback


# ---------------------------------------------------------------------------
# Conflict surfacing + dry-config preview — TASK-356
# (config-composition.md § Merge preview + conflict surfacing)
# ---------------------------------------------------------------------------


def test_conflicts_recorded_between_overlays_with_winner() -> None:
    base = {"swimlanes": [{"id": "docs", "label": "Docs"}]}
    first = {"swimlanes": [{"id": "shared", "label": "Shared / Pkg"}]}
    second = {"swimlanes": [{"id": "shared", "label": "Shared / Schemas"}]}
    conflicts: list[str] = []
    out = compose(
        base,
        [first, second],
        SCRUMBAN_SPEC,
        overlay_names=["go-fiber", "fastapi"],
        conflicts=conflicts,
    )
    assert len(conflicts) == 1
    assert "swimlanes[shared]" in conflicts[0]
    assert "(winner: fastapi)" in conflicts[0]
    by_id = {s["id"]: s["label"] for s in out["swimlanes"]}
    assert by_id["shared"] == "Shared / Schemas"  # later-wins resolution unchanged


def test_base_delta_is_not_a_conflict() -> None:
    """A single stack overriding the BASE default is the designed contract."""
    base = {"swimlanes": [{"id": "backend", "label": "Backend"}], "wip_limits": {"wip": 1}}
    overlay = {"swimlanes": [{"id": "backend", "label": "Django"}], "wip_limits": {"wip": 3}}
    conflicts: list[str] = []
    compose(base, [overlay], SCRUMBAN_SPEC, overlay_names=["django"], conflicts=conflicts)
    assert conflicts == []


def test_nested_dict_merge_conflict_has_dotted_path() -> None:
    base: dict = {}
    first = {"wip_limits": {"in_progress": 1}}
    second = {"wip_limits": {"in_progress": 2}}
    conflicts: list[str] = []
    compose(
        base,
        [first, second],
        SCRUMBAN_SPEC,
        overlay_names=["a", "b"],
        conflicts=conflicts,
    )
    assert conflicts == ["wip_limits.in_progress: 1 → 2 (winner: b)"]


def test_identical_overlay_values_do_not_conflict() -> None:
    first = {"swimlanes": [{"id": "api", "label": "API"}]}
    conflicts: list[str] = []
    compose({}, [first, dict(first)], SCRUMBAN_SPEC, conflicts=conflicts)
    assert conflicts == []


def test_preview_returns_merged_and_conflicts_without_writing(tmp_path: Path) -> None:
    from cli.config_composer import preview_coding_os_configs

    tdir = tmp_path / "templates"
    base = tdir / "_base" / "scaffold" / ".coding-os"
    base.mkdir(parents=True)
    (base / "scrumban-config.yaml").write_text(
        yaml.safe_dump({"swimlanes": [{"id": "docs", "label": "Docs"}]}), encoding="utf-8"
    )
    for stack, label in (("alpha", "A"), ("beta", "B")):
        overlay_dir = tdir / stack / "scaffold" / ".coding-os"
        overlay_dir.mkdir(parents=True)
        (overlay_dir / "scrumban-config.yaml").write_text(
            yaml.safe_dump({"swimlanes": [{"id": "shared", "label": label}]}), encoding="utf-8"
        )
    merged, conflicts = preview_coding_os_configs(["alpha", "beta"], templates_dir=tdir)
    assert "scrumban-config.yaml" in merged
    lane_ids = [s["id"] for s in merged["scrumban-config.yaml"]["swimlanes"]]
    assert lane_ids == ["docs", "shared"]
    assert conflicts == [
        'scrumban-config.yaml: swimlanes[shared]: {"id": "shared", "label": "A"} → '
        '{"id": "shared", "label": "B"} (winner: beta)'
    ]
    assert not list((tmp_path / "templates").rglob("*.generated"))  # nothing written anywhere
    assert not (tmp_path / ".coding-os").exists()
