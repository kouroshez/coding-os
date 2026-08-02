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
# task_analyzer — all under thinking_os/; misc helpers under hooks/_helpers/)
# are imported with no package prefix. conftest.py loads before collection, so
# inserting the dirs here covers every test file.
#
# IMPORTANT: do NOT add src/core/board_os or src/core/graph_os here — they each
# ship a `tools/` subpackage that collides with thinking_os/tools when both
# parents are on sys.path (graph_os code does a flat `from tools import _shared`
# resolving to thinking_os/tools). board_os/graph_os are imported package-
# qualified via `src/core` on the path instead.
REPO_ROOT = Path(__file__).resolve().parent.parent

# Golden fixtures are scaffold snapshots, not this repo's tests — every
# section ships a sample suite (test_health.py etc.) whose duplicate basenames
# collide at collection ("import file mismatch"). Their gates run inside real
# scaffolds via scaffold-verify.yml, never from here.
collect_ignore = ["golden"]

for _p in (
    REPO_ROOT,
    REPO_ROOT / "src",
    REPO_ROOT / "src" / "core",
    REPO_ROOT / "src" / "core" / "thinking_os",
    REPO_ROOT / "src" / "core" / "hooks" / "_helpers",
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


# Runtime session-identity vars an agent runtime (Claude Code, Codex)
# exports into every child process. When pytest runs INSIDE a live agent
# session these leak into test subprocesses — cos-env.sh's panel resolver
# checks them (CLAUDE_CODE_SESSION_ID first), so a test's own fixture session
# id loses to the ambient one and scaffold/doctor/panel tests fail. CI has
# none of these set, so the leak is invisible there. Scrubbing them makes the
# suite hermetic in-session too.
_LEAKY_SESSION_ENV = (
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CODEX_SESSION_ID",
    "GEMINI_SESSION_ID",
    "ANTHROPIC_SESSION_ID",
    "COS_PANEL_ID",
    "COS_AGENT_SESSION_ID",
)


@pytest.fixture(autouse=True)
def _isolate_registry(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect global registry to a temp file + scrub ambient session ids.

    Prevents cos init / add_project() from writing to ~/.coding-os/registry.json
    (COS_REGISTRY_PATH is honoured by cli.registry.registry_path()), and removes
    the agent-runtime session-identity vars so tests stay hermetic when run
    inside a live Claude/Codex session.
    """
    tmp_reg = tmp_path_factory.mktemp("registry", numbered=True) / "registry.json"
    monkeypatch.setenv("COS_REGISTRY_PATH", str(tmp_reg))
    for _var in _LEAKY_SESSION_ENV:
        monkeypatch.delenv(_var, raising=False)
