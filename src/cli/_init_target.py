"""Target-directory resolution for `cos init` — flags in, one prepared path out.

Owns the error taxonomy (`InitExit` / `InitError`), the name regex, and the
destructive-preparation guards (symlink refusal, force-wipe, nested-git
detection). Imports no sibling, so the git and materialize leaves can both
build on it.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
DEBUG_DIR = CODING_OS_ROOT / ".build" / "debug"
DEFAULT_DEBUG_NAME = "the-script-output"

NAME_REGEX = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def is_coding_os_source_tree(project: Path) -> bool:
    """True when `project` is the coding-os meta-repo source tree itself.

    The source tree ships a hand-written AGENTS.md (CLAUDE.md symlinks to it);
    any scaffold path (init, add/remove-stack, module toggle) must detect this
    and refuse to clobber it. Same telltale markers used by the init guard."""
    return (project / "src" / "core" / "thinking_os" / "server.py").exists() and (
        project / "src" / "cli" / "main.py"
    ).exists()


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
    adopt: bool = False,
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
            # adopt overlays onto an existing repo: keep its contents in place,
            # never refuse and never wipe (brownfield user code must survive).
            if not _is_dir_empty(target) and not adopt:
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
