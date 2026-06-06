"""Coverage for the per-file git diff endpoints (TASK-174):
/api/board/commit/{sha} and /api/board/diff.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.dev")
    _git(repo, "config", "user.name", "Test")
    (repo / "hello.py").write_text("print('a')\nprint('b')\n")
    _git(repo, "add", "hello.py")
    _git(repo, "commit", "-q", "-m", "add hello")
    sha = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("COS_PROJECT_ROOT", str(repo))
    monkeypatch.setenv("COS_STATE_DIR", str(repo / ".coding-os"))
    with TestClient(create_app()) as c:
        yield c, sha


def test_commit_lists_changed_files(client):
    c, sha = client
    resp = c.get(f"/api/board/commit/{sha}")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["subject"] == "add hello"
    paths = {f["path"]: f for f in data["files"]}
    assert "hello.py" in paths
    assert paths["hello.py"]["added"] == 2


def test_diff_returns_unified_patch(client):
    c, sha = client
    resp = c.get("/api/board/diff", params={"sha": sha, "file": "hello.py"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["file"] == "hello.py"
    assert "+print('a')" in data["diff"]
    assert data["added"] == 2
    assert data["removed"] == 0


def test_invalid_sha_is_rejected(client):
    c, _ = client
    assert c.get("/api/board/commit/not-a-sha").status_code == 400


def test_file_outside_repo_is_rejected(client):
    c, sha = client
    resp = c.get("/api/board/diff", params={"sha": sha, "file": "../../../etc/passwd"})
    assert resp.status_code == 400


def test_unknown_commit_is_not_found(client):
    c, _ = client
    resp = c.get("/api/board/commit/" + "0" * 40)
    assert resp.status_code == 404
