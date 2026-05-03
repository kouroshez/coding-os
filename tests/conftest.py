"""Global pytest fixtures for coding-os test suite.

Isolates side-effectful global state so tests never pollute the real
~/.coding-os/registry.json. Every test that calls `cos init` (directly or
via the CLI runner) writes to COS_REGISTRY_PATH — this autouse fixture
redirects that to a per-test tmp file, matching the pattern already used in
tests/test_registry.py.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_registry(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect global registry to a temp file for every test.

    Prevents cos init / add_project() from writing to ~/.coding-os/registry.json.
    The env var COS_REGISTRY_PATH is honoured by cli.registry.registry_path().
    """
    tmp_reg = tmp_path_factory.mktemp("registry", numbered=True) / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_reg))
