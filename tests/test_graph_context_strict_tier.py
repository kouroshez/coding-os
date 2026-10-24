"""enforce-graph-context blocks a shared file and only warns on a load-bearing one.

Spec: docs/engineering/graph_os-queries.md § Graph-context gate, two tiers.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "src" / "core" / "hooks" / "enforce-graph-context.sh"
TEMPLATE = REPO_ROOT / "src" / "templates" / "_base" / "scaffold" / ".coding-os" / "rag-config.yaml"

pytestmark = pytest.mark.skipif(
    shutil.which("cos") is None, reason="the glob helper needs PyYAML from the cos interpreter"
)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir()
    rag = TEMPLATE.read_text(encoding="utf-8").replace(
        "enforce_context_on: []", 'enforce_context_on:\n    - "*src/app/*"'
    )
    (state / "rag-config.yaml").write_text(rag, encoding="utf-8")
    return tmp_path


def _edit(project: Path, relative: str, **env: str) -> subprocess.CompletedProcess:
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(project / relative)}}
    base = {k: v for k, v in os.environ.items() if not k.startswith(("COS_", "CLAUDE_"))}
    base |= {"COS_STATE_DIR": str(project / ".coding-os"), "COS_AGENT": "claude", **env}
    return subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=60,
        env=base,
        cwd=project,
    )


def test_a_shared_file_blocks_without_a_consult(project: Path) -> None:
    proc = _edit(project, "src/shared/contracts/order.ts")
    assert proc.returncode == 2
    assert "cos_graph_context" in proc.stderr


def test_a_load_bearing_file_only_warns(project: Path) -> None:
    proc = _edit(project, "src/app/page.ts")
    assert proc.returncode == 0
    assert proc.stderr.startswith("warning:")


def test_an_ordinary_file_is_silent(project: Path) -> None:
    proc = _edit(project, "src/backend/main.go")
    assert proc.returncode == 0
    assert proc.stderr == ""


def test_off_disables_the_strict_tier(project: Path) -> None:
    proc = _edit(project, "src/shared/contracts/order.ts", COS_ENFORCE_GRAPH_CONTEXT="off")
    assert proc.returncode == 0
