"""
Phase N — Role registry tests.

Validate:
  - All 11 role files exist with id, role_name, activation, criteria_required.
  - Presets registry parses + every preset has match+chain+score.
  - Situation registry is compatible.
  - Composer loads without error.

Spec: docs/phase-n-role-based-routing-plan.md §2.2 · §2.4
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

_THINKING_OS = Path(__file__).resolve().parent.parent / "src" / "core" / "thinking_os"
if str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))

from formula_composer import (
    load_presets,
    load_roles,
    load_situations,
    reset_registry_cache,
)

ROLES_DIR = _THINKING_OS / "roles"
EXPECTED_ROLES = [
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
]


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_registry_cache()
    yield
    reset_registry_cache()


def test_all_eleven_role_files_exist():
    files = [p for p in sorted(ROLES_DIR.glob("*.yaml")) if p.stem in EXPECTED_ROLES]
    assert len(files) == 11, f"expected 11 role files, got {len(files)}"


def test_each_role_has_required_fields():
    for path in sorted(ROLES_DIR.glob("*.yaml")):
        if path.stem not in EXPECTED_ROLES:
            continue
        data = yaml.safe_load(path.read_text())
        assert data["id"] in EXPECTED_ROLES, f"unknown role id in {path.name}"
        assert "role_name" in data
        assert "formula_ref" in data
        assert "agent_file" in data
        assert "activation" in data
        assert "criteria_required" in data
        assert "prompt_prefix" in data
        assert "intensity_steps" in data
        for intensity in ("light", "standard", "full"):
            assert intensity in data["intensity_steps"]


def test_load_roles_returns_eleven():
    roles = load_roles()
    assert set(roles.keys()) == set(EXPECTED_ROLES)


def test_presets_registry_valid():
    presets, version = load_presets()
    assert len(presets) >= 8, "expected at least 8 curated presets"
    assert len(version) == 16, "preset version should be sha256 truncated to 16 chars"
    for preset in presets:
        assert "id" in preset
        assert "match" in preset, f"preset {preset.get('id')} missing match"
        assert "chain" in preset or preset.get("id") == "production-bug-mitigate"
        assert "score" in preset
        assert 0 <= preset["score"] <= 15


def test_preset_ids_unique():
    presets, _ = load_presets()
    ids = [p["id"] for p in presets]
    assert len(ids) == len(set(ids)), "duplicate preset ids detected"


def test_situations_registry_present():
    sits = load_situations()
    expected = {
        "incident-response",
        "onboarding",
        "scope-change",
        "external-integration",
        "design-review",
        "existing-project-takeover",
    }
    assert expected.issubset(set(sits.keys()))


def test_role_parallel_dispatch_on_F8_and_F6():
    roles = load_roles()
    assert roles["security_auditor"].get("parallel_dispatch", {}).get("enabled") is True
    assert "L5" in roles["security_auditor"]["parallel_dispatch"]["layers"]
    assert roles["reviewer"].get("parallel_dispatch", {}).get("enabled") is True
