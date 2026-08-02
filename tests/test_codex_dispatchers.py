from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "src" / "adapters" / "codex" / "hooks"

PRETOOL = HOOKS_DIR / "codex-pretool-dispatch.sh"
PREEDIT = HOOKS_DIR / "codex-preedit-dispatch.sh"
POSTEDIT = HOOKS_DIR / "codex-postedit-dispatch.sh"
SESSIONSTART = HOOKS_DIR / "codex-sessionstart-dispatch.sh"
STOP = HOOKS_DIR / "codex-stop-dispatch.sh"
NORMALIZER = HOOKS_DIR / "codex-normalize-edit.py"
MERGER = HOOKS_DIR / "codex-merge-hook-output.py"


def _invoke(
    hook: Path, payload: dict, env: dict | None = None, cwd: Path | None = None
) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=20,
        env=full_env,
        cwd=str(cwd) if cwd else None,
    )


def test_codex_pretool_dispatch_allows_safe_bash(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-safe\n")
    result = _invoke(
        PRETOOL,
        {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert json.loads(result.stdout) == {}


def test_codex_pretool_dispatch_propagates_delegate_block(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-block\n")
    result = _invoke(
        PRETOOL,
        {"tool_name": "Bash", "tool_input": {"command": "git reset --hard HEAD~1"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "reset --hard" in result.stderr


def test_codex_edit_normalizer_expands_every_patch_path() -> None:
    patch = """*** Begin Patch
*** Add File: src/new.py
+new_value = 1
*** Update File: src/old.py
-old_name = 1
+new_name = 1
*** Move to: src/moved.py
*** Delete File: src/deleted.py
-obsolete = True
*** End Patch"""
    result = subprocess.run(
        ["python3", str(NORMALIZER)],
        input=json.dumps({"tool_name": "apply_patch", "tool_input": {"command": patch}}),
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    payloads = [json.loads(line) for line in result.stdout.splitlines()]
    assert [item["tool_input"]["file_path"] for item in payloads] == [
        "src/new.py",
        "src/old.py",
        "src/moved.py",
        "src/deleted.py",
    ]
    assert all(item["tool_name"] == "Edit" for item in payloads)
    assert payloads[1]["tool_input"]["old_string"] == "old_name = 1"
    assert payloads[1]["tool_input"]["new_string"] == "new_name = 1"


def test_codex_preedit_dispatch_blocks_protected_patch(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    patch = "*** Begin Patch\n*** Update File: changes.log\n-old\n+new\n*** End Patch"
    result = _invoke(
        PREEDIT,
        {"tool_name": "apply_patch", "tool_input": {"command": patch}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "changes.log" in result.stderr


def test_codex_preedit_dispatch_fails_closed_on_unparseable_patch(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    result = _invoke(
        PREEDIT,
        {"tool_name": "apply_patch", "tool_input": {"command": "*** Begin Patch"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "no affected file path" in result.stderr


def test_codex_postedit_dispatch_fails_open_on_unparseable_patch(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    result = _invoke(
        POSTEDIT,
        {"tool_name": "apply_patch", "tool_input": {"command": "invalid"}},
        env={"COS_STATE_DIR": str(state)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}


def test_codex_output_merger_preserves_context_and_stop_block(tmp_path: Path) -> None:
    context_file = tmp_path / "context.json"
    context_file.write_text(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": "resume TASK-808",
                }
            }
        )
    )
    block_file = tmp_path / "block.json"
    block_file.write_text(json.dumps({"decision": "block", "reason": "verification pending"}))
    result = subprocess.run(
        ["python3", str(MERGER), "Stop", str(context_file), str(block_file)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "block"
    assert payload["reason"] == "verification pending"
    assert payload["hookSpecificOutput"]["additionalContext"] == "resume TASK-808"


def test_codex_userprompt_dispatch_forwards_delegate_context(tmp_path: Path) -> None:
    hook_dir = tmp_path / "hooks"
    hook_dir.mkdir()
    dispatcher = hook_dir / "codex-userpromptsubmit-dispatch.sh"
    shutil.copy(HOOKS_DIR / dispatcher.name, dispatcher)
    shutil.copy(MERGER, hook_dir / MERGER.name)
    (hook_dir / "cos-env.sh").write_text("")
    delegates = [
        "session-context.sh",
        "classify-task-mode.sh",
        "nudge-thinking-os.sh",
        "nudge-graph-os.sh",
        "nudge-model-routing.sh",
        "nudge-git-mode.sh",
        "nudge-reentry.sh",
        "nudge-task-discovery.sh",
        "nudge-docs-first.sh",
        "auto-compose-roles.sh",
        "agent-presence.sh",
    ]
    for delegate in delegates:
        script = hook_dir / delegate
        if delegate == "nudge-model-routing.sh":
            script.write_text(
                "#!/bin/sh\nprintf '%s\\n' "
                '\'{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit",'
                '"additionalContext":"route now"}}\'\n'
            )
        else:
            script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)

    result = _invoke(dispatcher, {"hook_event_name": "UserPromptSubmit"}, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert payload["hookSpecificOutput"]["additionalContext"] == "route now"


def test_codex_sessionstart_dispatch_creates_session_id(tmp_path: Path) -> None:
    """session-id is panel-scoped since TASK-035 — written under
    COS_AGENT_DIR/panels/<panel-id>/session-id so two panels of the same
    agent never collide. See docs/engineering/state-files.md."""
    state = tmp_path / ".coding-os"
    state.mkdir()
    # Pin COS_AGENT so the test runner's env doesn't flip detection.
    result = _invoke(
        SESSIONSTART,
        {"source": "startup"},
        env={
            "COS_STATE_DIR": str(state),
            "COS_AGENT": "codex",
            "CODEX_HOME": str(tmp_path / "home"),
        },
        cwd=tmp_path,
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    # panel-id is resolved at runtime (non-deterministic), so locate the
    # session-id under panels/<panel-id>/ rather than the legacy agent path.
    session_files = list((state / "codex").glob("panels/*/session-id"))
    assert session_files, "no panel session-id written"
    # Session-id is agent-prefixed so downstream log lines are self-describing.
    assert session_files[0].read_text().strip().startswith("ses-codex-")


def test_codex_stop_dispatch_returns_valid_json(tmp_path: Path) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "session-id").write_text("ses-stop\n")
    db = state / "coding-os.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE observations (id INTEGER PRIMARY KEY, session_id TEXT, body TEXT)")
    conn.commit()
    conn.close()

    result = _invoke(
        STOP,
        {"hook_event_name": "Stop"},
        env={"COS_STATE_DIR": str(state), "COS_DB_PATH": str(db)},
        cwd=tmp_path,
    )
    assert result.returncode == 0
    assert json.loads(result.stdout) == {}
