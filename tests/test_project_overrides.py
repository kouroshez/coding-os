"""TASK-256 — per-project hook/skill override layer.

Covers the primitive (safety hooks non-disableable, derived allowlist) AND the
cos-env.sh runtime self-skip that consumes the derived allowlist.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from cli import project_overrides as po  # noqa: E402
from cli.hook_renderer import load_registry  # noqa: E402

_COS_ENV = _REPO_ROOT / "src" / "core" / "hooks" / "cos-env.sh"


def _pick_hooks():
    reg = load_registry(po._default_registry_path())
    safety = next(h for h in reg if h.category == "safety")
    nonsafety = next(h for h in reg if h.category != "safety")
    return safety, nonsafety


def _write_override(root: Path, ids: list[str]) -> None:
    state = root / ".coding-os"
    state.mkdir(parents=True, exist_ok=True)
    (state / "hook-overrides.json").write_text(json.dumps({"disabled": ids}))


class TestPrimitive:
    def test_empty_when_no_file(self, tmp_path):
        assert po.load_hook_overrides(tmp_path) == set()
        assert po.effective_disabled_hooks(tmp_path) == set()

    def test_safety_hook_is_non_disableable(self, tmp_path):
        safety, nonsafety = _pick_hooks()
        _write_override(tmp_path, [safety.id, nonsafety.id, "no-such-hook"])
        eff = po.effective_disabled_hooks(tmp_path)
        assert nonsafety.id in eff
        assert safety.id not in eff  # safety is refused
        assert "no-such-hook" not in eff  # unknown id dropped
        assert po.refused_safety_hooks(tmp_path) == {safety.id}

    def test_runtime_allowlist_excludes_safety_scripts(self, tmp_path):
        safety, nonsafety = _pick_hooks()
        _write_override(tmp_path, [safety.id, nonsafety.id])
        out = po.write_runtime_allowlist(tmp_path)
        lines = out.read_text().split()
        assert nonsafety.script in lines
        assert safety.script not in lines

    def test_skill_overrides_load(self, tmp_path):
        state = tmp_path / ".coding-os"
        state.mkdir()
        (state / "skill-overrides.json").write_text(json.dumps({"disabled": ["performance"]}))
        assert po.load_skill_overrides(tmp_path) == {"performance"}


class TestRuntimeSelfSkip:
    def _run_hook(self, root: Path, script_name: str, listed: list[str]) -> str:
        state = root / ".coding-os"
        state.mkdir(parents=True, exist_ok=True)
        (state / "disabled-hook-scripts").write_text("\n".join(listed) + "\n")
        hook = root / script_name
        hook.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'source "{_COS_ENV}" 2>/dev/null || true\n'
            "echo HOOK_BODY_RAN\n"
        )
        env = {**os.environ, "COS_STATE_DIR": str(state)}
        env.pop("COS_SKIP_OVERRIDE_CHECK", None)
        proc = subprocess.run(
            ["bash", str(hook)], capture_output=True, text=True, env=env, timeout=10
        )
        return proc.stdout

    def test_disabled_hook_self_skips(self, tmp_path):
        out = self._run_hook(tmp_path, "myhook.sh", ["myhook.sh"])
        assert "HOOK_BODY_RAN" not in out  # cos-env.sh exited the hook early

    def test_unlisted_hook_runs(self, tmp_path):
        out = self._run_hook(tmp_path, "other.sh", ["myhook.sh"])
        assert "HOOK_BODY_RAN" in out  # not disabled → body runs
