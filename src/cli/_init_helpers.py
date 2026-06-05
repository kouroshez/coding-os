"""Helpers for `cos init` — target resolution, name validation, git init.

Separated from main.py to keep init logic testable and linear.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli._data_types import AggregatedWorld

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
DEBUG_DIR = CODING_OS_ROOT / ".build" / "debug"
DEFAULT_DEBUG_NAME = "the-script-output"

NAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class InitExit(IntEnum):
    """Stable exit codes for `cos init` error paths.

    FLAG_CONFLICT — mutually exclusive flags or unmet preconditions
    TARGET_STATE  — target exists non-empty, is a file, or OS error
    BAD_NAME      — --name does not match NAME_REGEX
    """

    FLAG_CONFLICT = 2
    TARGET_STATE = 3
    BAD_NAME = 4


class InitError(ValueError):
    """Raised when init flags / target state are invalid."""

    def __init__(self, message: str, exit_code: int = InitExit.FLAG_CONFLICT) -> None:
        super().__init__(message)
        self.exit_code = int(exit_code)


@dataclass(frozen=True)
class InitTarget:
    path: Path
    debug: bool
    forced_empty: bool  # True if we removed an existing non-empty dir
    nested_in_git: bool  # True if target sits inside an existing git repo


def validate_name(name: str) -> None:
    """Raise InitError if `name` doesn't match the allowed regex."""
    if not NAME_REGEX.match(name):
        raise InitError(
            f"invalid --name '{name}': must match ^[a-z0-9][a-z0-9._-]{{0,63}}$ "
            "(lowercase, digits, dot/underscore/hyphen, no slashes/spaces)",
            exit_code=InitExit.BAD_NAME,
        )


def _safe_remove_tree(path: Path) -> None:
    """Remove path whether it's a regular dir, symlink, or file.

    shutil.rmtree on a symlink follows the link and wipes its destination,
    which is dangerous. Detect symlinks and unlink them instead.
    """
    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _cwd_inside_coding_os(cwd: Path) -> bool:
    """Return True if `cwd` is the coding-os source repo or inside it."""
    try:
        cwd.resolve().relative_to(CODING_OS_ROOT)
        return True
    except ValueError:
        return False


def _is_nested_in_git(path: Path) -> bool:
    """Return True if `path` has a git repo as an ancestor.

    Walks up from path looking for a `.git` directory. Stops at filesystem
    root. Note: checks ancestors, not `path` itself — a fresh empty dir is
    not considered "nested" unless a parent has `.git`.
    """
    for ancestor in [path, *path.parents]:
        if ancestor == path:
            continue
        if (ancestor / ".git").exists():
            return True
    return False


def _is_dir_empty(path: Path) -> bool:
    return not any(path.iterdir())


def resolve_init_target(
    *,
    name: str | None,
    project_dir: str | None,
    debug: bool,
    force: bool,
    cwd: Path,
    pre_wipe_hook: object | None = None,
) -> InitTarget:
    """Compute the final target directory for `cos init`.

    Resolution order (see plan D1/D5/D6):
      1. --debug:
         - must be inside coding-os repo
         - --project-dir is mutually exclusive
         - name = --name or DEFAULT_DEBUG_NAME
         - target = <repo>/.build/debug/<name>
      2. --name: parent = --project-dir or cwd, target = parent/name
      3. --project-dir alone: target = that path
      4. else: target = cwd
    """
    if debug:
        if project_dir is not None:
            raise InitError(
                "--debug and --project-dir are mutually exclusive",
                exit_code=InitExit.FLAG_CONFLICT,
            )
        if not _cwd_inside_coding_os(cwd):
            raise InitError(
                "--debug requires running inside the coding-os source repo. "
                f"Current cwd {cwd} is outside {CODING_OS_ROOT}. "
                "Use --project-dir instead.",
                exit_code=InitExit.FLAG_CONFLICT,
            )
        effective_name = name or DEFAULT_DEBUG_NAME
        validate_name(effective_name)
        target = DEBUG_DIR / effective_name
    elif name is not None:
        validate_name(name)
        parent = Path(project_dir).absolute() if project_dir else cwd
        target = parent / name
    elif project_dir is not None:
        target = Path(project_dir).absolute()
    else:
        target = cwd

    # Use absolute() (not resolve()) so we can detect symlinks before they
    # collapse. Only resolve AFTER the symlink rejection check below.
    target = target.absolute()

    forced_empty = False
    try:
        if target.is_symlink():
            raise InitError(
                f"target {target} is a symlink; refusing to scaffold into symlinked paths",
                exit_code=InitExit.TARGET_STATE,
            )
        if target.exists():
            if target.is_file():
                raise InitError(
                    f"target {target} exists and is a file, not a directory",
                    exit_code=InitExit.TARGET_STATE,
                )
            # Fire pre-wipe hook BEFORE any destructive action so the caller
            # can refuse operations on the coding-os repo itself (or any
            # other sentinel target) without losing files.
            if pre_wipe_hook is not None:
                pre_wipe_hook(target)  # type: ignore[misc]
            if not _is_dir_empty(target):
                if not force:
                    raise InitError(
                        f"target {target} is not empty. Use --force to overwrite.",
                        exit_code=InitExit.TARGET_STATE,
                    )
                _safe_remove_tree(target)
                target.mkdir(parents=True)
                forced_empty = True
        else:
            target.mkdir(parents=True)
    except OSError as exc:
        raise InitError(
            f"filesystem error preparing target {target}: {exc}",
            exit_code=InitExit.TARGET_STATE,
        ) from exc

    return InitTarget(
        path=target,
        debug=debug,
        forced_empty=forced_empty,
        nested_in_git=_is_nested_in_git(target),
    )


@dataclass(frozen=True)
class GitInitResult:
    ran: bool
    skipped_reason: str | None
    error: str | None


def maybe_git_init(target: InitTarget, *, enabled: bool) -> GitInitResult:
    """Run `git init -q` unless disabled or target is nested in git.

    Per plan D7/D21: nested-in-git → skip silently; command failure → WARN
    (caller decides how to surface), not FAIL.
    """
    if not enabled:
        return GitInitResult(ran=False, skipped_reason="--no-git flag", error=None)
    if target.nested_in_git:
        return GitInitResult(ran=False, skipped_reason="nested in existing git repo", error=None)
    if (target.path / ".git").exists():
        return GitInitResult(ran=False, skipped_reason="already a git repo", error=None)
    try:
        proc = subprocess.run(
            ["git", "init", "-q"],
            cwd=str(target.path),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return GitInitResult(ran=False, skipped_reason=None, error=str(exc))
    if proc.returncode != 0:
        return GitInitResult(
            ran=False,
            skipped_reason=None,
            error=(proc.stderr or proc.stdout or "non-zero exit").strip(),
        )
    return GitInitResult(ran=True, skipped_reason=None, error=None)


# Mirrors the meta-repo .gitignore's runtime-ignore intent, minus the
# meta-specific lines (web/ui build, scaffold un-ignores, golden un-ignores).
# SSOT for "what a coding-os project tracks": machine-local cognitive state
# (DB + WAL, traces, panels) and rendered agent adapters stay out of history;
# the three tracked .coding-os/ config files stay versioned.
CONSUMER_GITIGNORE = """\
# coding-os project .gitignore — generated by `cos init`.

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
.mypy_cache/
.pytest_cache/
.ruff_cache/
.coverage
.coverage.*
htmlcov/
coverage.xml

# Node / frontend build output
node_modules/
dist/
build/

# Secrets & environment
.env
.env.*
!.env.example
*.pem
*.key

# Databases (runtime — coding-os cognitive DB + WAL sidecars)
*.db
*.db-shm
*.db-wal
*.db.backup-*

# coding-os runtime state — keep only the tracked config files
.coding-os/*
!.coding-os/rag-config.yaml
!.coding-os/domain-config.json
!.coding-os/scrumban-config.yaml

# Rendered agent adapters — regenerated by `cos update`; they hold
# machine-absolute symlink paths that do not survive a clone.
.claude/
.codex/
.cursor/
.mcp.json

# Editor / OS noise
.idea/
.vscode/
*.swp
*.swo
.DS_Store
Thumbs.db

# Logs
*.log
changes.log
"""

_BASELINE_COMMIT_MESSAGE = "chore: scaffold coding-os project"


def ensure_gitignore(project: Path) -> bool:
    """Write a coding-os `.gitignore` if the project has none. Idempotent.

    Never overwrites a user-authored file — the `exists` guard lets `init`
    call this safely even on a re-run or a nested-in-git target.
    """
    gitignore = project / ".gitignore"
    if gitignore.exists():
        return False
    gitignore.write_text(CONSUMER_GITIGNORE, encoding="utf-8")
    return True


@dataclass(frozen=True)
class InitialCommitResult:
    committed: bool
    skipped_reason: str | None
    error: str | None


def maybe_initial_commit(target: InitTarget, *, enabled: bool) -> InitialCommitResult:
    """Stage the freshly-scaffolded tree and make one baseline commit.

    Runs only when `cos init` itself created the repo (caller passes
    `git and git_result.ran`); a nested / pre-existing repo is left
    untouched so we never sweep a parent project's working tree. Fail-open:
    a missing committer identity falls back to a tool identity so a headless
    / CI consumer still gets a clean baseline; any other failure is reported
    (WARN), never fatal.
    """
    if not enabled:
        return InitialCommitResult(committed=False, skipped_reason="no fresh repo", error=None)
    try:
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target.path),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if add.returncode != 0:
            return InitialCommitResult(
                committed=False,
                skipped_reason=None,
                error=(add.stderr or add.stdout or "git add failed").strip(),
            )
        commit_args = ["commit", "-q", "-m", _BASELINE_COMMIT_MESSAGE]
        commit = subprocess.run(
            ["git", *commit_args],
            cwd=str(target.path),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if commit.returncode != 0:
            # Most common cause: no user.name/user.email configured. Retry
            # once with a tool identity so the baseline always lands.
            commit = subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=coding-os",
                    "-c",
                    "user.email=init@coding-os.local",
                    *commit_args,
                ],
                cwd=str(target.path),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        if commit.returncode != 0:
            return InitialCommitResult(
                committed=False,
                skipped_reason=None,
                error=(commit.stderr or commit.stdout or "git commit failed").strip(),
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return InitialCommitResult(committed=False, skipped_reason=None, error=str(exc))
    return InitialCommitResult(committed=True, skipped_reason=None, error=None)


def ensure_agents_md(project: Path, world: AggregatedWorld) -> bool:
    """Generate AGENTS.md from fragments if missing. Idempotent.

    Returns True if the file was just created, False if it already existed.
    Never overwrites user-customized AGENTS.md — the `if not exists` guard
    is the contract that lets `init`, `add-adapter`, and `update` all call
    this safely without clobbering edits.
    """
    from cli.renderer import render_agents_md

    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        return False
    agents_md.write_text(render_agents_md(world), encoding="utf-8")
    return True
