"""Where the coding-os database lives — project-root discovery and path rules.

Leaf module: no migration or connection code imports back into it, so the
"which project am I in" question is answerable without loading the schema.
"""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar
from pathlib import Path

logger = logging.getLogger("thinking_os.db")

# When the CV is None (MCP server, CLI, hooks), `resolve_db_path()`
# falls through to its legacy behaviour (explicit project_root arg or
# DEFAULT_DB_PATH).  This keeps single-project callers unaffected.
_active_project_root: ContextVar[Path | None] = ContextVar(
    "cos_active_project_root",
    default=None,
)


def set_active_project_root(root: Path | None) -> object:
    """Bind the current request's project root; returns a reset token."""
    return _active_project_root.set(root)


def reset_active_project_root(token: object) -> None:
    """Release a binding made by :func:`set_active_project_root`."""
    _active_project_root.reset(token)  # type: ignore[arg-type]


def get_active_project_root() -> Path | None:
    """Return the currently-bound project root (or None when unset)."""
    return _active_project_root.get()


DB_FILENAME = "coding-os.db"
LEGACY_DB_FILENAME = "thinking_os.db"  # rename target for migrate_legacy_db_filename()
STATE_DIRNAME = ".coding-os"

# A true project root co-locates its `.coding-os/` with at least one of these
# markers. A stray nested `.coding-os/` (lazy-created from a subdir like
# src/cli/) has none of them — so preferring a marked ancestor lets us skip
# strays and anchor on the real root.
_ROOT_MARKERS = (
    ".git",
    ".coding-os.yaml",
    "pyproject.toml",
    "package.json",
    "go.mod",
    "AGENTS.md",
)


def _find_project_root_from_cwd(start: Path | None = None) -> Path | None:
    """Walk up from cwd to find the enclosing coding-os project root.

    .coding-os/ lives ONLY at the project root.  Anywhere we land —
    src/core/web/, tests/, src/cli/, … — we must walk parents and
    anchor on the first .coding-os/ we find.  Without this walk, lazy
    init_db() calls from a subdirectory would CREATE a new stray
    .coding-os/ at cwd, which then surfaces in the Hub as a phantom
    project (the exact bug TASK-117 traced to nested .coding-os/).
    """
    cur = (start or Path.cwd()).resolve()
    try:
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        home = None
    first_with_state: Path | None = None
    for parent in [cur, *cur.parents]:
        # $HOME hard-stop: never inspect or accept $HOME/.coding-os (the global
        # hub state, not a project root). Mirrors the boundary in
        # cos-env.sh::_cos_find_project_root (TASK-498).
        if home is not None and parent == home:
            break
        try:
            if not (parent / STATE_DIRNAME).is_dir():
                continue
        except OSError:
            continue
        if first_with_state is None:
            first_with_state = parent
        # Prefer a `.coding-os/` that co-locates with a project-root marker:
        # this skips a stray nested `.coding-os/` (e.g. src/cli/.coding-os/
        # lazy-created from a subdir) and anchors on the true root. The walk
        # stops at the first MARKED root, so a legitimate checkout is never
        # overridden by an unmarked outer stray (e.g. ~/.coding-os).
        try:
            if any((parent / marker).exists() for marker in _ROOT_MARKERS):
                return parent
        except OSError:
            continue
    if first_with_state is not None:
        return first_with_state
    # No project `.coding-os/` below the $HOME boundary. A real subdir returns
    # cwd so it can lazy-create locally — but $HOME itself is refused: its
    # `.coding-os/` is the global hub state dir, and anchoring there mints a
    # phantom project DB inside it. At bare $HOME there is no project → None.
    if home is not None and cur == home:
        return None
    return cur


DEFAULT_DB_PATH = Path(
    os.environ.get("COS_DB_PATH", "")
    or str((_find_project_root_from_cwd() or Path.cwd()) / STATE_DIRNAME / DB_FILENAME)
)


def resolve_db_path(project_root: Path | str | None = None) -> Path:
    """Single source of truth for the canonical SQLite DB path.

    Resolution priority:
    1. ``<bound_root>/.coding-os/coding-os.db`` when a ProjectScopeMiddleware
       request has bound a per-request project scope. This wins over
       ``$COS_DB_PATH`` because the Hub inherits that env var from the
       directory it was launched in, so a scoped ``/api/p/<slug>/*`` request
       must reach the slug's DB, not the launch project's.
    2. ``$COS_DB_PATH`` env var, when set (the CLI / MCP default override).
    3. ``<project_root>/.coding-os/coding-os.db`` when project_root given.
    4. Walk up from cwd to find the enclosing ``.coding-os/``. RAISES at the
       bare ``$HOME`` boundary (no project below it): ``~/.coding-os/`` is the
       global hub state dir, and every DB-open path funnels through this
       resolver, so raising here is the ONE complete guard against minting a
       phantom ``$HOME/.coding-os/coding-os.db`` — the graph ``SqliteBackend``
       and cognition route ``sqlite3.connect`` directly to this path and would
       otherwise bypass ``init_db``'s guard. Fail-loud at a bare-``$HOME``
       misconfiguration beats a silent phantom; set ``$COS_DB_PATH`` or run
       inside a project. Do NOT weaken this to a cwd fallback.

    Only the Hub's ProjectScopeMiddleware binds ``_active_project_root``, so
    CLI / MCP callers skip step 1 and keep the prior ``$COS_DB_PATH`` behavior.

    Use this helper instead of inlining the same fallback formula in
    ~30 different sites — a future filename change becomes one edit
    here, not a sweep across `core/`, `cli/`, `adapters/`, and hooks.

    The path is returned even if the file does not exist yet — callers
    that need the file present should follow with ``init_db(path)``.
    """
    bound = _active_project_root.get()
    if bound is not None:
        return Path(bound) / STATE_DIRNAME / DB_FILENAME
    explicit = os.environ.get("COS_DB_PATH")
    if explicit:
        return Path(explicit)
    if project_root is not None:
        return Path(project_root) / STATE_DIRNAME / DB_FILENAME
    root = _find_project_root_from_cwd()
    if root is None:
        # Bare $HOME, no project below (see step 4). Every DB-open path resolves
        # through here, so raising is the complete guard — direct-connect
        # callers (graph SqliteBackend, cognition route) bypass init_db.
        raise RuntimeError(
            "no coding-os project found from cwd; set $COS_DB_PATH or run "
            "inside a project — $HOME/.coding-os is the global hub state dir, "
            "not a project DB"
        )
    return root / STATE_DIRNAME / DB_FILENAME


def project_root(start: Path | str | None = None) -> Path:
    """Single source of truth for the project root directory (holds .coding-os/).

    Precedence:
    1. ``$COS_PROJECT_ROOT`` env var, when set (explicit override).
    2. Parent of an absolute ``$COS_STATE_DIR`` — already resolved by
       cos-env.sh, so honoring it means the shell's one resolution is reused
       instead of re-walking.
    3. Upward marker-walk from cwd (``_find_project_root_from_cwd``), which has
       the $HOME hard-stop so the global hub at $HOME/.coding-os is never bound.

    Use this instead of the ``os.environ.get("COS_PROJECT_ROOT") or os.getcwd()``
    idiom that was duplicated across the CLI, board, web, background, and hook
    helpers — that idiom mis-resolves from a subdirectory (TASK-498).
    """
    explicit = os.environ.get("COS_PROJECT_ROOT")
    if explicit:
        return Path(explicit).resolve()
    state = os.environ.get("COS_STATE_DIR")
    if state:
        state_path = Path(state)
        if state_path.is_absolute():
            parent = state_path.resolve().parent
            # $HOME hard-stop: COS_STATE_DIR == $HOME/.coding-os is the global
            # hub (set by `cos hub`), not a project root — its parent is $HOME.
            # Reuse the shell's boundary instead of binding $HOME; fall through
            # to the marker-walk (which has its own $HOME hard-stop).
            try:
                home = Path.home().resolve()
            except (OSError, RuntimeError):
                home = None
            if home is None or parent != home:
                return parent
    start_path = Path(start) if start else None
    root = _find_project_root_from_cwd(start_path)
    return root if root is not None else (start_path or Path.cwd()).resolve()


def migrate_legacy_db_filename(target: Path) -> bool:
    """Rename `<dir>/thinking_os.db` → `<dir>/coding-os.db` once, in place."""
    if target.exists():
        return False
    legacy = target.with_name(LEGACY_DB_FILENAME)
    if not legacy.exists():
        return False
    legacy.rename(target)
    for ext in ("-shm", "-wal"):
        legacy_aux = legacy.with_name(legacy.name + ext)
        if legacy_aux.exists():
            legacy_aux.rename(target.with_name(target.name + ext))
    logger.info("Migrated legacy DB filename: %s -> %s", legacy.name, target.name)
    return True
