"""
Tests for cli/main.py — init, add-adapter, health, materialize, eject commands.

Covers:
  - init creates state dir, config, database, scaffold files, Makefile, AGENTS.md
  - add-adapter adds second adapter, updates config
  - health reports status correctly
  - materialize converts symlinks to real files; eject removes coding-os
  - hooks-dir prints core hooks path
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

# Ensure the cli module and the _cli_suite package are importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _cli_suite.shared import init_phase_module
from cli.main import cli

pytestmark = pytest.mark.slow  # dominated by cos-init / subprocess tests


@pytest.fixture(autouse=True)
def _stub_initial_indexing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must not run the real doc/graph index on every `cos init` — it
    loads the embedding model and walks the scaffold (minutes across the suite)
    and both are covered by their own tests. Stub them to no-ops (TASK-423)."""
    monkeypatch.setattr(init_phase_module, "_initial_doc_index", lambda *a, **k: None)
    monkeypatch.setattr(init_phase_module, "_initial_graph_index", lambda *a, **k: None)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Return a clean temporary project directory."""
    return tmp_path / "test-project"


@pytest.fixture
def initialized_project(runner: CliRunner, project_dir: Path) -> Path:
    """Return a project directory after running init."""
    project_dir.mkdir()
    result = runner.invoke(cli, ["init", "--agent", "claude", "-d", str(project_dir)])
    assert result.exit_code == 0, f"init failed: {result.output}"
    return project_dir


# ---------------------------------------------------------------------------
# Test classes live in tests/_cli_suite/ part modules; importing them here
# keeps every historical node id (tests/test_cli.py::<Class>) collecting
# under this module, and module-level fixtures above still apply to them.
# ---------------------------------------------------------------------------
from _cli_suite.init_install import (  # noqa: F401
    TestAddAdapter,
    TestCodexMcpInstall,
    TestEject,
    TestHealth,
    TestHooksDir,
    TestInit,
    TestInstallResilience,
    TestLanguageLayer,
    TestMakefileMaterialization,
    TestMaterialize,
    TestRefuseSelfInit,
    TestResolveProjectDir,
    TestServerStart,
    TestVersion,
)
from _cli_suite.misc import (  # noqa: F401
    TestAdopt,
    TestBrainSweepChangelog,
    TestDoctorTokens,
    TestGraphReindexFailureClassification,
    TestModuleEntrypointParity,
    TestProjectExtraSkills,
)
from _cli_suite.pr_bootstrap import TestCosPrBootstrap  # noqa: F401
from _cli_suite.pr_land import TestCosPrLand  # noqa: F401
from _cli_suite.pr_lifecycle import TestCosPrLifecycle  # noqa: F401
from _cli_suite.pr_reap import TestCosPrReap  # noqa: F401
from _cli_suite.pr_reap_recovery import TestCosPrReapRecovery  # noqa: F401
from _cli_suite.pr_settings import TestCosPrSettings  # noqa: F401
from _cli_suite.pr_status import TestCosPrStatus  # noqa: F401
from _cli_suite.pr_submit import TestCosPrSubmit  # noqa: F401
from _cli_suite.pr_triage import TestCosPrTriage  # noqa: F401
from _cli_suite.presets_skills import (  # noqa: F401
    TestCliOnboardingParity,
    TestDescriptionSeeding,
    TestDoctorAgentSdk,
    TestDoctorBootstrap,
    TestPresets,
    TestSkillCatalog,
)
from _cli_suite.scaffold import (  # noqa: F401
    TestCiWorkflow,
    TestDockerfile,
    TestProjectAnatomy,
    TestRegenChainRelocation,
)
from _cli_suite.subsystems import (  # noqa: F401
    TestFlagshipHexagonalPreset,
    TestModuleCli,
    TestModuleLifecycle,
    TestPresetAuthoring,
    TestPresetCatalogV1,
    TestSkillStandard,
    TestSubsystems,
    TestSupervisionCli,
)
