"""TASK-245 — onboarder is a chat-only role and must NOT perturb the 11-role
formula chain (it carries no canonical_order)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core", _REPO_ROOT / "src" / "core" / "thinking_os"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app  # noqa: E402


def test_onboarder_file_exists_with_no_canonical_order():
    import yaml

    md = _REPO_ROOT / "src" / "core" / "thinking_os" / "agents" / "onboarder.md"
    assert md.exists()
    parts = md.read_text(encoding="utf-8").split("---", 2)
    assert len(parts) >= 3, "onboarder.md needs YAML frontmatter"
    meta = yaml.safe_load(parts[1]) or {}
    # The loader keys on the parsed `canonical_order` value; a mention in a
    # comment is fine, the actual YAML key must be absent.
    assert "canonical_order" not in meta, "onboarder must NOT carry a canonical_order key"
    assert meta.get("id") == "onboarder"


def test_formula_chain_order_unbroken_by_onboarder():
    from thinking_os.formula_composer import _CANONICAL_ORDER_FALLBACK, _load_canonical_order

    order = _load_canonical_order()
    assert "onboarder" not in order
    assert len(order) == len(_CANONICAL_ORDER_FALLBACK) == 11
    assert set(order) == set(_CANONICAL_ORDER_FALLBACK)
    # researcher leads, refactorer is last — the canonical bookends hold.
    assert order[0] == "researcher"


def test_onboarder_listed_as_chat_role():
    with TestClient(create_app()) as client:
        resp = client.get("/api/cognition/roles")
    assert resp.status_code == 200
    roles = resp.json()["data"]["roles"]
    assert "onboarder" in roles
    # the 11 semantic roles are still all present alongside it
    for r in ("researcher", "implementer", "reviewer", "refactorer"):
        assert r in roles


def test_onboarder_excluded_from_formula_registry():
    from thinking_os.cognition import load_agent_registry

    reg = load_agent_registry()
    # chat_only roles are kept OUT of the formula registry so the 11-formula
    # contract (test_agent_registry_has_11_formulas) holds.
    assert "onboarder" not in reg
    assert len(reg) == 11
