"""Tests for `scripts/regen_doc_index.py` (TASK-157)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "src" / "scripts" / "regen_doc_index.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("regen_doc_index", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["regen_doc_index"] = module
    spec.loader.exec_module(module)
    return module


def _make_doc(
    path: Path,
    *,
    title: str,
    layer: str,
    domain: str = "DOCS",
    updated: str = "2026-04-28",
    tokens: int | None = None,
) -> Path:
    parts = [f"domain:{domain}", f"layer:{layer}", "ssot:true", f"updated:{updated}"]
    if tokens is not None:
        parts.append(f"tokens:{tokens}")
    fm = " | ".join(parts)
    body = f"<!-- {fm} -->\n# {title}\n\nPurpose: x.\nRead when: x.\nSkip when: x.\nRead next: x.\n"
    path.write_text(body, encoding="utf-8")
    return path


def test_first_time_index_has_full_frontmatter(tmp_path: Path) -> None:
    module = _load_module()
    _make_doc(tmp_path / "a.md", title="Alpha", layer="policy")
    _make_doc(tmp_path / "b.md", title="Beta", layer="reference")
    body = module.regenerate(tmp_path, write=True)
    assert body is not None
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    assert out.startswith("<!--")
    assert "layer:index" in out
    assert "Alpha" in out
    assert "Beta" in out
    assert "BEGIN auto-index" in out
    assert "END auto-index" in out


def test_groups_by_layer_with_canonical_order(tmp_path: Path) -> None:
    module = _load_module()
    _make_doc(tmp_path / "policy-1.md", title="P1", layer="policy")
    _make_doc(tmp_path / "playbook-1.md", title="PB1", layer="playbook")
    _make_doc(tmp_path / "ref-1.md", title="R1", layer="reference")
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    # Policy comes before Playbook, Playbook before Reference per _LAYER_ORDER.
    pos_policy = out.index("### Policy")
    pos_playbook = out.index("### Playbook")
    pos_reference = out.index("### Reference")
    assert pos_policy < pos_playbook < pos_reference


def test_preserves_hand_authored_prose_outside_markers(tmp_path: Path) -> None:
    module = _load_module()
    _make_doc(tmp_path / "a.md", title="Alpha", layer="policy")
    # Pre-existing index with hand-authored intro paragraph.
    (tmp_path / "00-index.md").write_text(
        "<!-- domain:DOCS | layer:index | ssot:true | updated:2026-04-01 -->\n"
        "# Hand Index\n\n"
        "Hand prose stays.\n\n"
        "<!-- BEGIN auto-index -->\n"
        "stale\n"
        "<!-- END auto-index -->\n\n"
        "Trailing prose stays too.\n",
        encoding="utf-8",
    )
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    assert "Hand prose stays." in out
    assert "Trailing prose stays too." in out
    assert "stale" not in out
    assert "Alpha" in out


def test_returns_none_when_no_canonical_docs(tmp_path: Path) -> None:
    module = _load_module()
    # Plain markdown with no frontmatter.
    (tmp_path / "plain.md").write_text("# plain\nbody\n", encoding="utf-8")
    body = module.regenerate(tmp_path, write=True)
    assert body is None
    # Index file must NOT have been created.
    assert not (tmp_path / "00-index.md").exists()


def test_skips_index_self_reference(tmp_path: Path) -> None:
    module = _load_module()
    _make_doc(tmp_path / "a.md", title="Alpha", layer="policy")
    _make_doc(tmp_path / "00-index.md", title="Index Self", layer="index")
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    # The auto-section must list `a.md` but NOT `00-index.md`.
    assert "a.md" in out
    assert "Index Self" not in out


def test_mixed_domain_dir_uses_domain_all_in_new_index(tmp_path: Path) -> None:
    # TASK-162 fix #7 — first-time index for a dir holding multiple domains
    # MUST emit `domain:ALL` in its synthesized frontmatter.
    module = _load_module()
    _make_doc(tmp_path / "a.md", title="A", layer="policy", domain="DOCS")
    _make_doc(tmp_path / "b.md", title="B", layer="policy", domain="BACKEND")
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    assert "domain:ALL" in out.splitlines()[0]


def test_homogeneous_domain_dir_keeps_specific_domain(tmp_path: Path) -> None:
    # The opposite of fix #7 — when every doc shares a domain, the index
    # should keep that domain so frontmatter-filter routing stays tight.
    module = _load_module()
    _make_doc(tmp_path / "a.md", title="A", layer="policy", domain="BACKEND")
    _make_doc(tmp_path / "b.md", title="B", layer="reference", domain="BACKEND")
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    assert "domain:BACKEND" in out.splitlines()[0]


def test_token_tag_present_when_frontmatter_carries_tokens(tmp_path: Path) -> None:
    module = _load_module()
    _make_doc(tmp_path / "big.md", title="Big Doc", layer="spec", tokens=2400)
    module.regenerate(tmp_path, write=True)
    out = (tmp_path / "00-index.md").read_text(encoding="utf-8")
    assert "~2400t" in out
