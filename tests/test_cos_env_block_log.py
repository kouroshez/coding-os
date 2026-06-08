"""cos_log_hook must mirror every 'block' action into a block-only durable log
($COS_HOOK_BLOCK_LOG), so rare block events survive the high-volume main log's
500-line cap and reach learn_extract's hook-block miner. This guards the WRITE
side (the miner-read side is covered by test_learning.TestHookBlockLessons)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COS_ENV = REPO_ROOT / "src" / "core" / "hooks" / "cos-env.sh"


def _run(state_dir: Path, calls: list[tuple[str, str, str]]) -> None:
    """Source cos-env.sh and fire a sequence of cos_log_hook calls."""
    script = f"source '{COS_ENV}'\n" + "\n".join(
        f"cos_log_hook {hook} {action} '{detail}'" for hook, action, detail in calls
    )
    base_env = {k: v for k, v in os.environ.items() if not k.startswith("COS_")}
    base_env.update(
        {
            "COS_STATE_DIR": str(state_dir),
            "COS_AGENT": "claude",
            "COS_SKIP_OVERRIDE_CHECK": "1",  # bypass the per-project disable check (tests)
        }
    )
    subprocess.run(["bash", "-c", script], env=base_env, check=True, capture_output=True, text=True)


def test_block_lines_mirrored_to_durable_log(tmp_path: Path) -> None:
    _run(
        tmp_path,
        [
            ("enforce-skill", "fire", "noise"),
            ("enforce-skill", "block", "rule=no-domain-skill"),
            ("thinking_os-gate", "ok", "fine"),
            ("thinking_os-gate", "block", "rule=gate-not-recorded"),
        ],
    )
    main_log = (tmp_path / ".hooks.log").read_text().splitlines()
    block_log = (tmp_path / ".hook-blocks.log").read_text().splitlines()

    assert len(main_log) == 4  # every action lands in the main log
    assert len(block_log) == 2  # ONLY the two blocks reach the durable log
    assert all("[block]" in line for line in block_log)  # block-only — no fire/ok noise
    assert any("rule=no-domain-skill" in line for line in block_log)
    assert any("rule=gate-not-recorded" in line for line in block_log)


def test_durable_log_absent_when_no_blocks(tmp_path: Path) -> None:
    # Mock data: only non-block actions → expected output is NO block log file
    # at all (the durable log is never created on the happy path).
    _run(tmp_path, [("h1", "fire", ""), ("h2", "ok", "done"), ("h3", "enter", "")])
    assert (tmp_path / ".hooks.log").exists()
    assert not (tmp_path / ".hook-blocks.log").exists()
