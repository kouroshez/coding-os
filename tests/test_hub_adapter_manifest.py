"""Tests for hub_adapter_manifest — adapter list for Hub board API."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from board_os import hub_adapter_manifest as ham  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_manifest_cache():
    ham.invalidate_agent_manifest_cache()
    yield
    ham.invalidate_agent_manifest_cache()


def test_list_agent_manifest_rows_includes_known_adapters():
    rows = ham.list_agent_manifest_rows()
    ids = {r["id"] for r in rows}
    assert "claude" in ids
    assert "codex" in ids
    for r in rows:
        assert "glyph" in r and "color" in r and r["color"].startswith("#")
        assert r["session"] == f"ses-{r['id']}"


def test_list_agent_ids_includes_known_adapters():
    ids = ham.list_agent_ids()
    assert "claude" in ids
    assert "codex" in ids


def test_list_agent_ids_discovers_new_adapter_with_no_code_edit(tmp_path, monkeypatch):
    adapters = tmp_path / "src" / "adapters"
    (adapters / "gemini").mkdir(parents=True)
    (adapters / "gemini" / "adapter.yaml").write_text(
        yaml.safe_dump(
            {"version": 1, "id": "gemini", "label": "Gemini", "install_script": "install.sh"},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COS_CODING_OS_ROOT", str(tmp_path))
    ham.invalidate_agent_manifest_cache()
    assert "gemini" in ham.list_agent_ids()


def test_hub_glyph_from_yaml(tmp_path, monkeypatch):
    adapters = tmp_path / "src" / "adapters"
    (adapters / "zeta").mkdir(parents=True)
    manifest = {
        "version": 1,
        "id": "zeta",
        "label": "Zeta Agent",
        "install_script": "install.sh",
        "presence": {"hub_glyph": "Zt", "hub_color": "#abcdef"},
    }
    (adapters / "zeta" / "adapter.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("COS_CODING_OS_ROOT", str(tmp_path))
    ham.invalidate_agent_manifest_cache()
    rows = ham.list_agent_manifest_rows()
    z = next(x for x in rows if x["id"] == "zeta")
    assert z["glyph"] == "Zt"
    assert z["color"].lower() == "#abcdef"
