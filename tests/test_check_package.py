"""Tests for the node-backend check_package.py auditor."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]
                       / "src" / "core" / "skills" / "node-backend" / "scripts"))

import check_package as cp  # noqa: E402


def test_healthy_package_clean() -> None:
    pkg = {"engines": {"node": ">=24"}, "scripts": {"start": "node dist/server.js"}}
    assert cp.audit(pkg, has_lockfile=True) == []


def test_missing_engines_flagged() -> None:
    pkg = {"scripts": {"start": "node ."}}
    findings = cp.audit(pkg, has_lockfile=True)
    assert any("engines.node" in f for f in findings)


def test_missing_lockfile_flagged() -> None:
    pkg = {"engines": {"node": ">=24"}, "scripts": {"start": "node ."}}
    findings = cp.audit(pkg, has_lockfile=False)
    assert any("lockfile" in f for f in findings)


def test_npm_install_in_script_flagged() -> None:
    pkg = {"engines": {"node": ">=24"}, "scripts": {"start": "node .", "ci": "npm install && test"}}
    findings = cp.audit(pkg, has_lockfile=True)
    assert any("npm ci" in f for f in findings)


def test_missing_start_flagged() -> None:
    pkg = {"engines": {"node": ">=24"}, "scripts": {"build": "tsc"}}
    findings = cp.audit(pkg, has_lockfile=True)
    assert any("'start'" in f for f in findings)
