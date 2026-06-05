"""Tests for src/scripts/refresh_skill_versions.py — pure layer + write path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "scripts"))

import refresh_skill_versions as rsv  # noqa: E402


def _entry(version: str = "1.0.0") -> dict:
    return {"ecosystem": "npm", "package": "next", "version": version,
            "source": "https://registry.npmjs.org/next", "checked": "2026-01-01"}


def test_validate_entry_accepts_well_formed() -> None:
    rsv.validate_entry("next", _entry())


@pytest.mark.parametrize("entry,needle", [
    ({"ecosystem": "npm", "package": "next"}, "missing required"),
    ({"ecosystem": "frobnicate", "package": "x", "version": "1"}, "unknown ecosystem"),
    ("not-a-dict", "must be an object"),
])
def test_validate_entry_rejects_bad(entry: object, needle: str) -> None:
    with pytest.raises(rsv.SchemaError) as exc:
        rsv.validate_entry("k", entry)
    assert needle in str(exc.value)


@pytest.mark.parametrize("pinned,latest,drift", [
    ("1.0.0", "1.0.0", False),
    ("v1.0.0", "1.0.0", False),   # v-prefix normalized
    ("1.0.0", "1.0.1", True),
    (" 1.0.0 ", "1.0.0", False),  # whitespace tolerant
])
def test_is_drift(pinned: str, latest: str, drift: bool) -> None:
    assert rsv.is_drift(pinned, latest) is drift


@pytest.mark.parametrize("tag,expected", [
    ("v1.2.3", "1.2.3"),
    ("cli-2.6.0", "2.6.0"),        # maestro tags releases as cli-<ver>
    ("docker-v29.5.3", "29.5.3"),  # moby tags releases as docker-v<ver>
    ("3.13.1", "3.13.1"),          # bare version, no prefix
    ("nightly", "nightly"),        # no number → returned as-is
])
def test_tag_version_strips_project_prefixes(tag: str, expected: str) -> None:
    assert rsv._tag_version(tag) == expected


def test_load_manifest_round_trips(tmp_path: Path) -> None:
    p = tmp_path / "versions.json"
    p.write_text(json.dumps({"next": _entry()}), encoding="utf-8")
    assert rsv.load_manifest(p)["next"]["package"] == "next"


def test_load_manifest_rejects_non_object(tmp_path: Path) -> None:
    p = tmp_path / "versions.json"
    p.write_text("[1,2,3]", encoding="utf-8")
    with pytest.raises(rsv.SchemaError):
        rsv.load_manifest(p)


def test_find_manifests_skips_node_modules(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "versions.json").write_text("{}", encoding="utf-8")
    nm = tmp_path / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "versions.json").write_text("{}", encoding="utf-8")
    found = rsv.find_manifests(tmp_path, None)
    assert len(found) == 1 and "node_modules" not in found[0].parts


def test_refresh_offline_is_schema_only(tmp_path: Path) -> None:
    p = tmp_path / "versions.json"
    p.write_text(json.dumps({"next": _entry()}), encoding="utf-8")
    rows = rsv.refresh_manifest(p, offline=True, write=False, timeout=1, log=lambda _m: None)
    assert rows[0]["status"] == "schema-ok"


def test_refresh_write_updates_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "versions.json"
    p.write_text(json.dumps({"next": _entry("1.0.0")}), encoding="utf-8")
    monkeypatch.setitem(rsv.FETCHERS, "npm", lambda _pkg, _t: "2.0.0")
    rows = rsv.refresh_manifest(p, offline=False, write=True, timeout=1, log=lambda _m: None)
    assert rows[0]["status"] == "drift"
    written = json.loads(p.read_text(encoding="utf-8"))
    assert written["next"]["version"] == "2.0.0"
    assert written["next"]["checked"] != "2026-01-01"


def test_refresh_reports_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = tmp_path / "versions.json"
    p.write_text(json.dumps({"next": _entry()}), encoding="utf-8")

    def _boom(_pkg: str, _t: float) -> str:
        raise rsv.urllib.error.URLError("offline")

    monkeypatch.setitem(rsv.FETCHERS, "npm", _boom)
    rows = rsv.refresh_manifest(p, offline=False, write=False, timeout=1, log=lambda _m: None)
    assert rows[0]["status"] == "unreachable"
