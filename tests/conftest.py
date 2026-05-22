"""Global pytest fixtures for coding-os test suite.

Isolates side-effectful global state so tests never pollute the real
~/.coding-os/registry.json. Every test that calls `cos init` (directly or
via the CLI runner) writes to COS_REGISTRY_PATH — this autouse fixture
redirects that to a per-test tmp file, matching the pattern already used in
tests/test_registry.py.

Also bootstraps sys.path once for the whole tests/ tree so individual files
need not each re-insert the flat-module dirs (cognition_schemas, database,
formula_composer, …) — see REPO_ROOT below.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# --- Shared path bootstrap -------------------------------------------------
# Flat-module imports (cognition_schemas, database, capture, formula_composer,
# task_analyzer, …) live under src/core/<subsystem>/ and are imported with no
# package prefix. conftest.py loads before collection, so inserting the dirs
# here covers every test file — replacing ~28 per-file sys.path.insert hacks.
REPO_ROOT = Path(__file__).resolve().parent.parent

for _p in (
    REPO_ROOT,
    REPO_ROOT / "src",
    REPO_ROOT / "src" / "core",
    REPO_ROOT / "src" / "core" / "thinking_os",
    REPO_ROOT / "src" / "core" / "board_os",
    REPO_ROOT / "src" / "core" / "graph_os",
):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


@pytest.fixture
def cli_runner():
    """Shared Click CliRunner — replaces inline CliRunner() instantiation."""
    from click.testing import CliRunner

    return CliRunner()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-sdk-e2e",
        action="store_true",
        default=False,
        help="Run sdk_e2e-marked tests (require ANTHROPIC_API_KEY, nightly only)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip sdk_e2e tests unless --run-sdk-e2e is passed."""
    if config.getoption("--run-sdk-e2e"):
        return
    skip_e2e = pytest.mark.skip(reason="pass --run-sdk-e2e to run SDK end-to-end tests")
    for item in items:
        if item.get_closest_marker("sdk_e2e"):
            item.add_marker(skip_e2e)


@pytest.fixture(autouse=True)
def _isolate_registry(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect global registry to a temp file for every test.

    Prevents cos init / add_project() from writing to ~/.coding-os/registry.json.
    The env var COS_REGISTRY_PATH is honoured by cli.registry.registry_path().
    """
    tmp_reg = tmp_path_factory.mktemp("registry", numbered=True) / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_reg))
