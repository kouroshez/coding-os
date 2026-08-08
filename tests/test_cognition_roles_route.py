"""Coverage for GET /api/cognition/roles + the _role_names filter (TASK-197)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes.cognition import _role_names
from core.web.server import create_app

_CANONICAL = {
    "researcher",
    "analyst",
    "architect",
    "documenter",
    "implementer",
    "reviewer",
    "debugger",
    "security_auditor",
    "deployer",
    "observer",
    "refactorer",
}


def test_role_names_filters_non_roles(tmp_path):
    for name in (
        "researcher.md",
        "security_auditor.md",
        "README.md",  # uppercase → excluded
        "_shared.md",  # leading underscore helper → excluded
        "Architect.md",  # uppercase → excluded
        "notes.txt",  # not *.md → excluded
    ):
        (tmp_path / name).write_text("x")
    assert _role_names(tmp_path) == ["researcher", "security_auditor"]


def test_role_names_missing_dir(tmp_path):
    assert _role_names(tmp_path / "does-not-exist") == []


def test_roles_endpoint_lists_canonical_roles():
    with TestClient(create_app()) as c:
        r = c.get("/api/cognition/roles")
    assert r.status_code == 200
    roles = r.json()["data"]["roles"]
    # The real producer dir must carry at least the 11 canonical roles.
    assert set(roles) >= _CANONICAL
    assert all(name.islower() and not name.startswith("_") for name in roles)
    assert "README" not in roles
