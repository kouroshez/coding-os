"""TASK-247 — GET /api/cognition/onboarding-status readiness signal."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.server import create_app  # noqa: E402

_PLACEHOLDER = "# Snapshot\n\n_TODO: write the elevator pitch._\n- _TODO: Year 1._\n"
_AUTHORED = "# Snapshot\n\nWe build X for Y. Year 1: ship. Year 2: grow.\n"


def _seed(tmp_path: Path, prd_text: str | None) -> None:
    if prd_text is not None:
        prd = tmp_path / "docs" / "prd"
        prd.mkdir(parents=True)
        (prd / "01-snapshot-vision.md").write_text(prd_text)
    (tmp_path / ".coding-os").mkdir(exist_ok=True)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COS_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("COS_STATE_DIR", str(tmp_path / ".coding-os"))
    with TestClient(create_app()) as c:
        yield c


def _status(client) -> dict:
    r = client.get("/api/cognition/onboarding-status")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_incomplete_when_placeholders_remain(client, tmp_path):
    _seed(tmp_path, _PLACEHOLDER)
    data = _status(client)
    assert data["complete"] is False
    assert data["placeholders_remaining"] == 2
    assert data["source"] == "placeholder_scan"


def test_complete_when_placeholders_authored(client, tmp_path):
    _seed(tmp_path, _AUTHORED)
    data = _status(client)
    assert data["complete"] is True
    assert data["placeholders_remaining"] == 0


def test_complete_when_no_prd_scaffold(client, tmp_path):
    _seed(tmp_path, None)  # no docs/prd at all
    data = _status(client)
    assert data["complete"] is True
    assert data["source"] == "no_prd"


def test_onboarding_json_override_wins(client, tmp_path):
    _seed(tmp_path, _PLACEHOLDER)  # placeholders remain...
    (tmp_path / ".coding-os" / "onboarding.json").write_text(json.dumps({"completed": True}))
    data = _status(client)
    assert data["complete"] is True  # ...but the explicit marker overrides
    assert data["source"] == "onboarding_json"


def test_helper_counts_across_prd_dir(tmp_path):
    from core.web.routes.cognition import _onboarding_state

    prd = tmp_path / "docs" / "prd"
    prd.mkdir(parents=True)
    (prd / "01-snapshot-vision.md").write_text("_TODO: a._\n_TODO: b._")
    (prd / "02-goals.md").write_text("_TODO: c._")
    state = tmp_path / ".coding-os"
    state.mkdir()
    out = _onboarding_state(tmp_path, state)
    assert out["complete"] is False
    assert out["placeholders_remaining"] == 3


def test_intake_seeded_prd_still_reads_as_pending(tmp_path):
    # The one signal: an intake-seeded PRD keeps _TODO: markers, so the scan
    # sees an unauthored PRD without a second completion flag to keep in sync.
    from cli.setup import seed_prd_from_text
    from core.web.routes.cognition import _onboarding_state

    (tmp_path / ".coding-os").mkdir(parents=True)
    seed_prd_from_text(tmp_path, "A booking app for indie venues.")
    out = _onboarding_state(tmp_path, tmp_path / ".coding-os")
    assert out["complete"] is False
    assert out["placeholders_remaining"] > 0


def test_authoring_over_the_intake_completes_onboarding(tmp_path):
    from cli.setup import seed_prd_from_text
    from core.web.routes.cognition import _onboarding_state

    (tmp_path / ".coding-os").mkdir(parents=True)
    seed_prd_from_text(tmp_path, "A booking app for indie venues.")
    vision = tmp_path / "docs" / "prd" / "01-snapshot-vision.md"
    vision.write_text(vision.read_text().replace("_TODO:", "Answered:"))
    assert _onboarding_state(tmp_path, tmp_path / ".coding-os")["complete"] is True


def test_dismiss_persists_completion(client, tmp_path):
    _seed(tmp_path, _PLACEHOLDER)
    assert _status(client)["complete"] is False
    resp = client.post("/api/cognition/onboarding-status/dismiss", json={})
    assert resp.status_code == 200, resp.text
    assert _status(client)["complete"] is True
