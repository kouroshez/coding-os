"""TASK-672 — hook behavior-parity harness.

Captures each representative hook's (exit-code, stderr-present, additionalContext-
present) signature for a fixed (event, stdin) input, asserted against a checked-in
golden. A hook MERGE — or any edit — that changes a captured signature fails here:
the de-risking contract for hook consolidation. Regenerate the golden with:
    COS_UPDATE_HOOK_PARITY=1 uv run pytest tests/test_hook_parity.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_HOOKS = _REPO / "src" / "core" / "hooks"
_GOLDEN = _REPO / "tests" / "golden" / "hook_parity_baseline.json"

# (case_id, hook_file, event, stdin_payload). Chosen for determinism: pure
# stdin-driven observability/nudge hooks that fail-open without a DB (each records
# an exit-0 / no-output no-op signature), plus two safety-gate cases that MUST
# block — those two supply the golden's discriminating power. Each case runs in its
# own fresh COS_AGENT_DIR so per-session debounce markers never cross-contaminate.
CASES: list[tuple[str, str, dict]] = [
    ("reentry-noop", "nudge-reentry.sh", {"user_prompt": "hi"}),
    ("abandoned-noop", "warn-abandoned-task.sh", {}),
    ("thinking-noop", "nudge-thinking-os.sh", {"user_prompt": "hi"}),
    ("docs-first-noop", "nudge-docs-first.sh", {"user_prompt": "hi"}),
    # Discriminating cases: safety gates that MUST block (exit 2 + stderr) — a
    # merge that silences either is a security regression the harness catches.
    (
        "secrets-noverify-block",
        "block-secrets.sh",
        {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}},
    ),
    (
        "commit-msg-bad-block",
        "enforce-commit-message.sh",
        {
            "tool_name": "Bash",
            "tool_input": {
                "command": (
                    'git commit -m "not a conventional title and also far past the hundred '
                    'character ceiling the contract strictly enforces for every commit line"'
                )
            },
        },
    ),
]


def _signature(hook_file: str, payload: dict, agent_dir: Path) -> dict:
    # Strip any ambient COS_PANEL_* so a live agent session's panel dir cannot
    # redirect the hooks' marker/debounce files and flip a case's signature (the
    # hooks resolve markers via ${COS_PANEL_DIR:-$COS_AGENT_DIR}).
    env = {k: v for k, v in os.environ.items() if not k.startswith("COS_PANEL")}
    env.update(
        {
            "COS_AGENT_DIR": str(agent_dir),
            "COS_STATE_DIR": str(agent_dir),
            "COS_PANEL_ID": "parity",
            # Non-existent DB so DB-gated branches fail-open deterministically
            # instead of touching the real board.
            "COS_DB_PATH": str(agent_dir / "no-such.db"),
        }
    )
    proc = subprocess.run(
        ["bash", str(_HOOKS / hook_file)],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=20,
    )
    return {
        "exit": proc.returncode,
        "stderr": bool(proc.stderr.decode(errors="ignore").strip()),
        "additionalContext": "additionalContext" in proc.stdout.decode(errors="ignore"),
    }


def _current(tmp_path: Path) -> dict:
    result: dict[str, dict] = {}
    for case_id, hook_file, payload in CASES:
        d = tmp_path / case_id
        d.mkdir(parents=True, exist_ok=True)
        result[case_id] = _signature(hook_file, payload, d)
    return result


def test_hook_parity_matches_golden(tmp_path):
    current = _current(tmp_path)
    if os.environ.get("COS_UPDATE_HOOK_PARITY") == "1":
        _GOLDEN.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert _GOLDEN.exists(), (
        "seed the golden first: COS_UPDATE_HOOK_PARITY=1 uv run pytest tests/test_hook_parity.py -q"
    )
    golden = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert current == golden, (
        "hook parity divergence — a hook's (exit, stderr, additionalContext) signature "
        "changed. If intended, regenerate: "
        "COS_UPDATE_HOOK_PARITY=1 uv run pytest tests/test_hook_parity.py -q"
    )
