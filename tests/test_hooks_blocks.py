"""
Tests for core/hooks/ — parameterization, syntax, and COS_STATE_DIR support.

Covers:
  - All hooks pass bash -n syntax check
  - cos-env.sh sets correct defaults
  - cos-env.sh respects COS_STATE_DIR override
  - write-state.sh and check-state.sh round-trip
  - Gate hooks respond to correct state values
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks"


def run_hook(
    hook_name: str,
    stdin: str = "",
    env_overrides: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    """Run a hook script with optional stdin and environment overrides."""
    hook_path = HOOKS_DIR / hook_name
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["bash", str(hook_path)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=10,
    )


REPO_SRC = HOOKS_DIR.parent.parent  # <repo>/src — for the canonical Python resolver


def _resolve_cos_var(
    var: str,
    cwd: str,
    env_overrides: dict[str, str] | None = None,
    strip: tuple[str, ...] = ("CLAUDE_PROJECT_DIR", "COS_PROJECT_ROOT", "COS_STATE_DIR"),
) -> str:
    """Source cos-env.sh from `cwd` and echo one exported var. The anchor env
    vars in `strip` are removed first so the upward marker-walk path runs."""
    env = {k: v for k, v in os.environ.items() if k not in strip}
    if env_overrides:
        env.update(env_overrides)
    script = 'source "{}"; echo "${}"'.format(HOOKS_DIR / "cos-env.sh", var)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=10,
    ).stdout.strip()


def _python_resolve_root(cwd: str) -> str:
    """Project root per the canonical Python resolver, run from `cwd`."""
    import sys

    code = (
        f"import sys; sys.path.insert(0, {str(REPO_SRC)!r}); "
        "from core.thinking_os._db_paths import _find_project_root_from_cwd; "
        "print(_find_project_root_from_cwd())"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=30,
    ).stdout.strip()


# ---------------------------------------------------------------------------
# Syntax validation — all hooks must pass bash -n
# ---------------------------------------------------------------------------


class TestBlockSecrets:
    def test_blocks_env_file(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git add backend/.env"},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_env_example(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git add .env.example"},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0

    def test_blocks_private_key_in_code(self) -> None:
        # A bare PEM header with no key material — SECURITY.md § Test fixtures
        # for secret detection.
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "app/config.py",
                    "new_string": "-----BEGIN RSA PRIVATE KEY-----",
                },
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_secret_patterns_in_docs(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": "docs/security.md",
                    "new_string": "sk_live_example",
                },
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0

    def test_blocks_no_verify_flag(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit --no-verify -m "x"'},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    def test_allows_no_verify_inside_commit_message(self) -> None:
        # The flag named inside the -m message must NOT trip the flag block.
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": 'git commit -m "docs: --no-verify is blocked now"'},
            }
        )
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0

    def test_fail_closed_when_bypass_helper_crashes(self, tmp_path: Path) -> None:
        # TASK-572: if check_git_bypass.py cannot run (a broken python3 shim), a
        # git-commit command must FAIL CLOSED (block), never silently allow — a
        # mutation flipping the error-default to allow would otherwise pass unseen.
        shim = tmp_path / "bin"
        shim.mkdir()
        (shim / "python3").write_text("#!/bin/sh\nexit 1\n")
        (shim / "python3").chmod(0o755)
        env = {"PATH": f"{shim}:{os.environ.get('PATH', '')}"}
        blocked = run_hook(
            "block-secrets.sh",
            stdin=json.dumps(
                {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}}
            ),
            env_overrides=env,
        )
        assert blocked.returncode == 2  # fail-closed on the unverifiable commit
        # A non-commit git op under the same broken helper is scoped to allow.
        allowed = run_hook(
            "block-secrets.sh",
            stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git add README.md"}}),
            env_overrides=env,
        )
        assert allowed.returncode == 0

    # TASK-563: the anchored `^git commit … --no-verify` regex missed every shape
    # below; each must now BLOCK without breaking a clean `git commit`.
    @pytest.mark.parametrize(
        "command",
        [
            "git commit -n -m x",  # -n short flag
            "git commit -nm x",  # bundled -n -m
            "/usr/bin/git commit --no-verify",  # leading absolute path
            "cd d && git commit --no-verify",  # cd … && prefix
            "env GIT_X=1 git commit --no-verify",  # env-assignment prefix
            "git -c core.hooksPath=/dev/null commit",  # hooks-disabling config
            "git config core.hooksPath /dev/null",  # persistent hooks disable
            "git -c foo=bar commit -n",  # -c <kv> global before commit (TASK-565)
            "git -c a.b=c commit --no-verify",  # value-taking global splits git…commit
            "git  commit -n -m x",  # double space (non-contiguous git commit)
            # TASK-567: quote-splice collapses to the real flag at exec time — the
            # old quote-STRIPPED regex deleted the spliced char and missed these.
            'git commit --no-ver"i"fy -m x',  # splice inside the flag
            'git commit "--no-verify" -m x',  # whole flag quoted
            'git commit "-n" -m x',  # short form quoted
            'git commit --"no-verify" -m x',  # partial quote
            # TASK-567: GIT_CONFIG_* env injection disables core.hooksPath.
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
            "GIT_CONFIG_GLOBAL=/dev/null git commit -m x",
            "env GIT_CONFIG_GLOBAL=/dev/null git commit -m x",
            # TASK-571: `;`/newline/backtick/brace separators must split like `&&` —
            # the shipped tokenizer demoted `;` to whitespace and swallowed it, so a
            # one-token `true;` prefix bypassed the whole gate (critical regression).
            "true; git commit --no-verify",
            "git status; git commit --no-verify -m x",
            "echo hi; git commit --no-verify",
            "true\ngit commit --no-verify",
            "x=`git commit --no-verify`",
            "{ git commit --no-verify; }",
            "true; git -c core.hooksPath=/dev/null commit -m x",
            "true; GIT_CONFIG_GLOBAL=/dev/null git commit -m x",
            # TASK-571: GIT_CONFIG_GLOBAL/SYSTEM redirecting to a CUSTOM file (not only
            # /dev/null) can carry a hooksPath override — block the whole class.
            "GIT_CONFIG_GLOBAL=/tmp/x.cfg git commit -m x",
            "GIT_CONFIG_SYSTEM=/tmp/x.cfg git commit -m x",
            # TASK-612: git resolves any unambiguous long-option prefix, so a
            # --no-verify ABBREVIATION skips the verify hooks just as well — the old
            # literal `--no-verify` match missed every prefix from the --no-verbose
            # disambiguation point onward.
            "git commit --no-veri -m x",  # min unambiguous prefix
            "git commit --no-verif -m x",
            'git commit --no-ver"i"fy -m x',  # already covered above; abbrev sibling
            'git commit --no-ver"i" -m x',  # splice collapses to --no-veri
            "cd d && git commit --no-veri -m x",  # compound prefix
            "true; git commit --no-veri -m x",  # separator prefix
        ],
    )
    def test_blocks_no_verify_bypass_shapes(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 2

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m x",  # clean commit
            "git commit --amend",  # n-letters but no -n
            'git commit -am "msg"',  # -a -m bundle, no n
            "git commit -m x && echo --no-verify",  # flag in an UNRELATED segment
            "git -c foo=bar commit -m x",  # clean commit WITH a -c global (TASK-565)
            "git log --grep core.hooksPath",  # read-only git mentioning the token
            "git commit-graph write",  # 'commit' substring, not a commit
            # TASK-567: a message body that merely MENTIONS the flag stays a value token.
            'git commit -m "-n is the short form for --no-verify"',
            # TASK-567: an UNRELATED GIT_CONFIG_* injection (not core.hooksPath) is fine.
            "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=x git commit -m ok",
            # TASK-571: an ATTACHED `-m<message>` whose value contains 'n' is NOT -n —
            # real git reads `-mnope` as -m with message "nope" (the old commit_flags
            # added every cluster letter and false-blocked these).
            "git commit -mnope",
            "git commit -mnow-fixing-things",
            # TASK-571: a message containing `;` and parens must not split/false-block.
            'git commit -m "refactor; drop (legacy) path"',
            # TASK-571: `git config --get core.hooksPath` is a READ, sets nothing.
            "git config --get core.hooksPath",
            "git config --list",
            # TASK-612: `--no-ver` is AMBIGUOUS between --no-verify and --no-verbose,
            # so git itself rejects it — the gate must NOT block (no false positive),
            # and `--no-verbose`/`--no-edit` are unrelated --no-* options.
            "git commit --no-ver -m x",
            "git commit --no-verbose -m x",
            "git commit --no-edit",
        ],
    )
    def test_allows_clean_commit_shapes(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook("block-secrets.sh", stdin=payload)
        assert result.returncode == 0


class TestBlockDangerousCommands:
    def test_blocks_force_push_main(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 2

    # TASK-571: git ignores flag position and resolves qualified refspecs, so the
    # force-push-to-main guard must catch every order/qualification, not just the
    # canonical `--force` before `main`.
    @pytest.mark.parametrize(
        "command",
        [
            "git push origin main --force",  # flag AFTER the refspec
            "git push origin main -f",  # short flag after refspec
            "git push -f origin main",
            "git push origin +main",  # refspec force
            "git push origin +HEAD:main",
            "git push origin +refs/heads/main",  # fully-qualified force refspec
        ],
    )
    def test_blocks_force_push_main_all_orders(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook(
            "block-dangerous-commands.sh",
            stdin=payload,
            env_overrides={"COS_ALLOW_FORCE_PUSH_MAIN": "0"},
        )
        assert result.returncode == 2

    @pytest.mark.parametrize(
        "command",
        [
            "git push origin main",  # normal (non-force) trunk publish
            "git pull --rebase origin main && git push origin main",
            "git push --force origin feature",  # force to a non-main branch
            "git push --force-with-lease origin agents/x",  # the safe variant on a feature branch
        ],
    )
    def test_allows_non_force_or_non_main_push(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook(
            "block-dangerous-commands.sh",
            stdin=payload,
            env_overrides={"COS_ALLOW_FORCE_PUSH_MAIN": "0"},
        )
        assert result.returncode == 0

    def test_blocks_rm_rf(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf backend"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 2

    # TASK-612: git resolves any unambiguous long-option prefix and accepts split
    # short clusters, so `reset --hard` / `clean -f` must match by SHAPE — the old
    # literal greps (`git reset --hard`, `git clean\s+-[a-z]*f`) missed the
    # abbreviation (`--har`, `--for`, `--f`) and the split cluster (`-d -f`).
    @pytest.mark.parametrize(
        "command",
        [
            "git reset --hard",  # exact
            "git reset --har HEAD~1",  # --hard abbrev
            "git reset --ha",  # shorter abbrev
            "git clean -f",  # exact short
            "git clean -fd",  # bundled short
            "git clean -df build",  # bundled, other order
            "git clean -d -f",  # split cluster
            "git clean -x -d -f",  # fully split
            "git clean --force",  # exact long
            "git clean --for",  # long abbrev
            "git clean --f",  # min long abbrev
        ],
    )
    def test_blocks_git_destructive_abbreviations(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 2

    @pytest.mark.parametrize(
        "command",
        [
            "git clean -n",  # dry-run short — no force
            "git clean --dry-run",  # dry-run long
            "git clean -d",  # remove dirs but NOT forced
            "git clean -i",  # interactive, no force
            "git reset --soft HEAD~1",  # soft reset is not the data-loss --hard
            "git reset --mixed HEAD",  # default mode, no -hard
        ],
    )
    def test_allows_non_destructive_git_clean_reset(self, command: str) -> None:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 0

    # TASK-567 (F3): an inline `COS_ALLOW_FORCE_PUSH_MAIN=1 git push …` prefix
    # must NOT self-grant the override — the assignment has not executed when the
    # PreToolUse hook reads its own env, so an agent cannot bypass from the
    # command string. Only a real session-env export opens it.
    @pytest.mark.parametrize(
        "command",
        [
            "COS_ALLOW_FORCE_PUSH_MAIN=1 git push --force origin main",
            "cd x && COS_ALLOW_FORCE_PUSH_MAIN=1 git push --force origin main",
        ],
    )
    def test_inline_force_push_override_is_rejected(self, command: str) -> None:
        # Explicitly 0 in the process env: the ONLY way to grant the override is a
        # real export — so this isolates whether the inline prefix self-grants it.
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        result = run_hook(
            "block-dangerous-commands.sh",
            stdin=payload,
            env_overrides={"COS_ALLOW_FORCE_PUSH_MAIN": "0"},
        )
        assert result.returncode == 2

    def test_session_export_force_push_override_allows(self) -> None:
        payload = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
        )
        result = run_hook(
            "block-dangerous-commands.sh",
            stdin=payload,
            env_overrides={"COS_ALLOW_FORCE_PUSH_MAIN": "1"},
        )
        assert result.returncode == 0

    def test_allows_normal_git_push(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git push origin feature-branch"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 0

    def test_allows_normal_commands(self) -> None:
        payload = json.dumps(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "ls -la"},
            }
        )
        result = run_hook("block-dangerous-commands.sh", stdin=payload)
        assert result.returncode == 0
