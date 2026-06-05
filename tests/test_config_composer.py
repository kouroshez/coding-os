"""Unit tests for the data-driven config composer (config-composition.md)."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from cli.config_composer import (
    RAG_SPEC,
    SCRUMBAN_SPEC,
    compose,
    compose_coding_os_configs,
    recompose_for_added_stack,
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
    assert [s["id"] for s in out["swimlanes"]] == ["docs", "frontend", "backend"]  # both stacks kept


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
    written = compose_coding_os_configs(
        tmp_path / "proj", state, ["mystack"], templates_dir=tdir
    )
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
