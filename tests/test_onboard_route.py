"""TASK-246 — POST /api/cognition/onboard runs the onboarder docs-scoped.

The streaming SDK path needs a live Claude, so we cover the deterministic guards
plus the pure write-permission contract (_onboard_write_allowed) that the
PreToolUse hook enforces — that contract IS the acceptance criteria.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    state = tmp_path / ".coding-os"
    (state / "claude").mkdir(parents=True)
    monkeypatch.setenv("COS_STATE_DIR", str(state))
    with TestClient(create_app()) as c:
        yield c


def test_onboard_empty_prompt_rejected(client):
    r = client.post("/api/cognition/onboard", json={"prompt": "   "})
    assert r.json()["error"]["category"] == "validation"


def test_onboard_unavailable_without_sdk(client, monkeypatch):
    patched = False
    for modname in ("web.routes.cognition", "core.web.routes.cognition"):
        mod = sys.modules.get(modname)
        if mod is not None:
            monkeypatch.setattr(mod, "_claude_sdk", lambda: None, raising=False)
            patched = True
    assert patched, "cognition module not loaded"
    r = client.post("/api/cognition/onboard", json={"prompt": "set up my docs"})
    assert r.json()["error"]["category"] == "unavailable"


class TestDocsScopeContract:
    """_onboard_write_allowed is the enforced acceptance contract."""

    def _cog(self):
        from core.web.routes import cognition

        return cognition

    def test_write_under_docs_allowed(self, tmp_path):
        (tmp_path / "docs").mkdir()
        cog = self._cog()
        assert cog._onboard_write_allowed({"file_path": "docs/prd/01-snapshot.md"}, tmp_path)
        assert cog._onboard_write_allowed(
            {"file_path": str(tmp_path / "docs" / "architecture" / "x.md")}, tmp_path
        )

    def test_write_outside_docs_denied(self, tmp_path):
        (tmp_path / "docs").mkdir()
        cog = self._cog()
        assert not cog._onboard_write_allowed({"file_path": "src/cli/main.py"}, tmp_path)
        assert not cog._onboard_write_allowed({"file_path": "README.md"}, tmp_path)
        assert not cog._onboard_write_allowed(
            {"file_path": str(tmp_path / "src" / "evil.py")}, tmp_path
        )

    def test_path_traversal_escape_denied(self, tmp_path):
        (tmp_path / "docs").mkdir()
        cog = self._cog()
        # docs/../src climbs out of docs/ → must deny.
        assert not cog._onboard_write_allowed({"file_path": "docs/../src/x.py"}, tmp_path)
        assert not cog._onboard_write_allowed({"file_path": "/etc/passwd"}, tmp_path)

    def test_missing_or_bad_input_denied(self, tmp_path):
        cog = self._cog()
        assert not cog._onboard_write_allowed({}, tmp_path)
        assert not cog._onboard_write_allowed({"file_path": ""}, tmp_path)
        assert not cog._onboard_write_allowed("not-a-dict", tmp_path)

    def test_notebook_path_key_supported(self, tmp_path):
        (tmp_path / "docs").mkdir()
        cog = self._cog()
        assert cog._onboard_write_allowed({"notebook_path": "docs/nb.ipynb"}, tmp_path)
        assert not cog._onboard_write_allowed({"notebook_path": "nb.ipynb"}, tmp_path)
