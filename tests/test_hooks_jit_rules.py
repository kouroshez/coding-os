"""Behavior tests for the jit-recall convention-rule reminder path (jit-rules.tsv)."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "jit-recall.sh"


def _run_hook(file_path: str, panel_dir: Path) -> tuple[int, str]:
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=json.dumps({"tool_input": {"file_path": file_path}}).encode(),
        capture_output=True,
        timeout=10,
        env={
            **os.environ,
            "COS_PANEL_DIR": str(panel_dir),
            "COS_DB_PATH": str(panel_dir / "absent.db"),
        },
    )
    return proc.returncode, proc.stderr.decode()


def test_matching_path_surfaces_rule_once(tmp_path: Path) -> None:
    target = "/repo/src/core/web/ui/src/components/GraphPanel.tsx"

    code, err = _run_hook(target, tmp_path)
    assert code == 0
    assert "api-contract-discipline" in err

    code, err = _run_hook(target, tmp_path)
    assert code == 0
    assert "api-contract-discipline" not in err


def test_non_matching_path_is_silent(tmp_path: Path) -> None:
    code, err = _run_hook("/repo/src/core/thinking_os/server.py", tmp_path)
    assert code == 0
    assert "[rule]" not in err


def test_adapter_path_gets_adapter_rule(tmp_path: Path) -> None:
    code, err = _run_hook("/repo/src/adapters/claude/install.sh", tmp_path)
    assert code == 0
    assert "reader hook" in err


def test_relative_path_matches_like_absolute(tmp_path: Path) -> None:
    code, err = _run_hook("src/core/web/ui/src/api/client.ts", tmp_path)
    assert code == 0
    assert "api-contract-discipline" in err
