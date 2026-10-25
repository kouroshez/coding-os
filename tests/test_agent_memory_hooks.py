"""The two hooks that bring .agents/memory to each agent.

ensure-agent-memory-link (Claude) points the harness memory dir at the repo;
prime-memory-codex (Codex) hands the index over once per session.
Spec: src/core/rules/memory.md § How each agent reaches it.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK_HOOK = ROOT / "src" / "adapters" / "claude" / "hooks" / "ensure-agent-memory-link.sh"
PRIME_HOOK = ROOT / "src" / "adapters" / "codex" / "hooks" / "prime-memory-codex.sh"


def _repo(tmp_path: Path, name: str = "my.app") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    return repo.resolve()


def _run(hook: Path, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(hook)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=20,
        cwd=str(cwd),
        env={**os.environ, "COS_STATE_DIR": str(cwd / ".coding-os"), **env},
    )


def test_link_maps_dots_in_the_path_like_claude_does(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    home = tmp_path / "home"
    result = _run(LINK_HOOK, repo, {"HOME": str(home)})
    assert result.returncode == 0, result.stderr
    slug = str(repo).replace("/", "-").replace(".", "-")
    link = home / ".claude" / "projects" / slug / "memory"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == repo / ".agents" / "memory"


def test_link_migrates_existing_notes_without_clobbering_the_repo(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    home = tmp_path / "home"
    slug = str(repo).replace("/", "-").replace(".", "-")
    harness = home / ".claude" / "projects" / slug / "memory"
    harness.mkdir(parents=True)
    (harness / "local-only.md").write_text("from this machine\n")
    (harness / "MEMORY.md").write_text("machine index\n")
    repo_mem = repo / ".agents" / "memory"
    repo_mem.mkdir(parents=True)
    (repo_mem / "MEMORY.md").write_text("repo index\n")

    assert _run(LINK_HOOK, repo, {"HOME": str(home)}).returncode == 0
    assert (repo_mem / "local-only.md").read_text() == "from this machine\n"
    assert (repo_mem / "MEMORY.md").read_text() == "repo index\n"
    assert harness.is_symlink()


def _prime(repo: Path, panel: Path) -> subprocess.CompletedProcess[str]:
    return _run(PRIME_HOOK, repo, {"COS_AGENT": "codex", "COS_PANEL_DIR": str(panel)})


def test_prime_hands_codex_the_index_once_per_session(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / ".agents" / "memory").mkdir(parents=True)
    (repo / ".agents" / "memory" / "MEMORY.md").write_text("- [A](a.md) — rule a\n")
    panel = tmp_path / "panel"

    first = _prime(repo, panel)
    assert first.returncode == 0, first.stderr
    payload = json.loads(first.stdout)["hookSpecificOutput"]
    assert payload["hookEventName"] == "UserPromptSubmit"
    assert "- [A](a.md) — rule a" in payload["additionalContext"]

    second = _prime(repo, panel)
    assert second.returncode == 0 and second.stdout == ""


def test_prime_is_silent_without_an_index(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    result = _prime(repo, tmp_path / "panel")
    assert result.returncode == 0 and result.stdout == ""
    assert not (tmp_path / "panel" / ".memory-primed").exists()


def test_codex_dispatcher_lifts_the_context_limit_for_the_index() -> None:
    template = json.loads((ROOT / "src/adapters/codex/hooks.template.json").read_text())
    handlers = [h for g in template["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
    assert [h.get("additionalContextLimit") for h in handlers] == [10000]
