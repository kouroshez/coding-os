"""graph_os — language toolchain config parser (TASK-082).

PURPOSE:      Make cross-file import resolution use real path-aliases
              from `tsconfig.compilerOptions.paths`, the Go module
              prefix from `go.mod`, crate names from `Cargo.toml`, and
              package roots from `pyproject.toml` / `setup.cfg`.  So
              `from @shared/auth import login` in TS, or
              `import "myapp/internal/auth"` in Go, emit concrete
              edges to repo-local nodes instead of `unresolved:...`.
INPUT:        Repository root path.  Files looked up:
                tsconfig.json (+ extends chain)
                go.mod
                Cargo.toml (+ workspace)
                pyproject.toml ([tool.poetry.packages] /
                                [tool.setuptools.packages] /
                                [project] name)
                setup.cfg fallback
OUTPUT:       ToolchainContext — a frozen dataclass cached per
              (repo_root, mtime_sum).  Read-only after construction.
DEPENDENCIES: stdlib only on Python 3.11+ (`tomllib`).  No Node, no
              Go, no Cargo invoked — pure parsing.
NOTES:        Tolerant: malformed config logs WARN and yields the
              empty mapping for that toolchain.  Never raises during
              normal flow.

              Extractors integrate via the module-level *active*
              context — `set_active(ctx)` is called once per indexing
              dispatch in `reindex_dispatch._reindex_graph`, and
              `get_active()` returns the in-flight context (or None
              when not running under a dispatch).  Extractors fall
              back to the old behavior when None.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Python 3.11+ ships tomllib stdlib; older runtimes fall back to the
# vendored tomli package.  Keeping the import behind a conditional means
# the Cargo.toml / pyproject.toml parsing degrades gracefully when no
# TOML reader is available — those particular toolchain hints just
# come back empty.
try:
    import tomllib  # type: ignore[unused-ignore]
except ModuleNotFoundError:  # Python <= 3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]


def _toml_error() -> type[Exception]:
    """Return the TOML decode-error class for whichever backend is
    available, or ValueError as a stand-in when no TOML reader is
    installed (so `except (OSError, _toml_error())` always works)."""
    if tomllib is None:
        return ValueError
    return getattr(tomllib, "TOMLDecodeError", ValueError)


logger = logging.getLogger("graph_os.toolchain")


# ---------------------------------------------------------------------------
# ToolchainContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolchainContext:
    """Resolved toolchain hints for one repo.

    All paths are stored repo-relative POSIX strings so they line up
    with the rest of graph_os's path canonicalisation.  Empty mappings
    are normal — most repos only have one toolchain.
    """

    repo_root: str
    # tsconfig.compilerOptions.paths.  Pattern → list of replacement
    # globs.  ``*`` is the wildcard that's substituted when matching.
    ts_paths: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # tsconfig.compilerOptions.baseUrl resolved relative to repo_root,
    # POSIX form.  Empty string when absent.
    ts_base_url: str = ""
    # go.mod `module github.com/...` value.  Empty when no go.mod.
    go_module: str = ""
    # Cargo crate name → repo-relative root.  Always includes the root
    # crate; workspace members add their own entries.
    rust_crates: dict[str, str] = field(default_factory=dict)
    # Python package name → repo-relative root.  E.g.
    #   {"myapp": "src/myapp"} for src-layout poetry projects.
    python_packages: dict[str, str] = field(default_factory=dict)


_EMPTY = ToolchainContext(repo_root="")


# ---------------------------------------------------------------------------
# Loader (cached)
# ---------------------------------------------------------------------------


_CACHE: dict[tuple[str, int], ToolchainContext] = {}
_CACHE_LOCK = threading.Lock()


def load_toolchain(repo_root: str | Path) -> ToolchainContext:
    """Return the ToolchainContext for ``repo_root``, cached by mtime sum.

    INPUT:    repo_root — anything Path-like, resolved to its absolute
              POSIX form for cache stability.
    OUTPUT:   ToolchainContext.  Returns ``_EMPTY`` (no toolchain hints)
              when no recognised config file is present.
    NOTES:    Cache key is (resolved_root, sum(mtime)) so editing any
              config file cheaply invalidates.  The cache is bounded
              implicitly by the number of distinct repos a single
              process touches.
    """
    root = Path(repo_root).expanduser().resolve()
    if not root.is_dir():
        return ToolchainContext(repo_root=str(root))

    config_files = [
        root / "tsconfig.json",
        root / "go.mod",
        root / "Cargo.toml",
        root / "pyproject.toml",
        root / "setup.cfg",
    ]
    mtime_sum = 0
    for path in config_files:
        try:
            mtime_sum += int(path.stat().st_mtime_ns)
        except FileNotFoundError:
            continue
        except OSError as exc:
            logger.debug("stat failed for %s: %s", path, exc)

    cache_key = (str(root), mtime_sum)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached is not None:
            return cached

    ctx = ToolchainContext(
        repo_root=str(root),
        ts_paths=_load_ts_paths(root),
        ts_base_url=_load_ts_base_url(root),
        go_module=_load_go_module(root),
        rust_crates=_load_rust_crates(root),
        python_packages=_load_python_packages(root),
    )

    with _CACHE_LOCK:
        _CACHE[cache_key] = ctx
    return ctx


def reset_cache() -> None:
    """Clear the toolchain cache.  Used by tests + cos sync-doctor."""
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Active-context API (consumed by extractors)
# ---------------------------------------------------------------------------


_ACTIVE = threading.local()


def set_active(ctx: ToolchainContext | None) -> None:
    """Stash the toolchain for the current dispatch.  Extractors then
    consult ``get_active()`` to access it without changing their public
    `extract(path, content)` signature."""
    _ACTIVE.value = ctx


def get_active() -> ToolchainContext | None:
    return getattr(_ACTIVE, "value", None)


# ---------------------------------------------------------------------------
# tsconfig.json — paths + baseUrl
# ---------------------------------------------------------------------------


def _strip_jsonc(raw: str) -> str:
    """Best-effort JSONC -> JSON: strip // line comments, /* ... */ blocks,
    and trailing commas before } or ].  tsconfig is JSONC in the wild."""
    no_block = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    no_line = re.sub(r"//[^\n]*", "", no_block)
    no_trailing = re.sub(r",(\s*[}\]])", r"\1", no_line)
    return no_trailing


def _read_tsconfig(root: Path) -> dict[str, Any]:
    path = root / "tsconfig.json"
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("tsconfig read failed: %s", exc)
        return {}
    try:
        data = json.loads(_strip_jsonc(raw))
    except json.JSONDecodeError as exc:
        logger.warning("tsconfig parse failed: %s", exc)
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _load_ts_paths(root: Path) -> dict[str, tuple[str, ...]]:
    data = _read_tsconfig(root)
    co = data.get("compilerOptions") or {}
    paths = co.get("paths") or {}
    if not isinstance(paths, dict):
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for pattern, replacements in paths.items():
        if not isinstance(replacements, list):
            continue
        cleaned = tuple(r for r in replacements if isinstance(r, str) and r)
        if cleaned:
            out[str(pattern)] = cleaned
    return out


def _load_ts_base_url(root: Path) -> str:
    data = _read_tsconfig(root)
    co = data.get("compilerOptions") or {}
    base = co.get("baseUrl")
    if not isinstance(base, str) or not base:
        return ""
    rel = (root / base).resolve()
    try:
        as_posix = rel.relative_to(root).as_posix()
    except ValueError:
        # baseUrl outside repo — keep as absolute POSIX.
        return rel.as_posix()
    # `.` (repo root) is most useful as the empty string so callers can
    # concatenate without a stray `./` prefix.
    return "" if as_posix == "." else as_posix


# ---------------------------------------------------------------------------
# go.mod — module github.com/...
# ---------------------------------------------------------------------------


_GO_MODULE_RE = re.compile(r"^module\s+\"?([^\"\s]+)\"?\s*$", re.MULTILINE)


def _load_go_module(root: Path) -> str:
    path = root / "go.mod"
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("go.mod read failed: %s", exc)
        return ""
    m = _GO_MODULE_RE.search(raw)
    return m.group(1).strip() if m else ""


# ---------------------------------------------------------------------------
# Cargo.toml — root + workspace members
# ---------------------------------------------------------------------------


def _load_rust_crates(root: Path) -> dict[str, str]:
    path = root / "Cargo.toml"
    if not path.is_file() or tomllib is None:
        return {}
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except (OSError, _toml_error()) as exc:
        logger.warning("Cargo.toml parse failed: %s", exc)
        return {}

    crates: dict[str, str] = {}

    pkg = data.get("package") or {}
    if isinstance(pkg, dict):
        name = pkg.get("name")
        if isinstance(name, str) and name:
            crates[name] = "."

    workspace = data.get("workspace") or {}
    members = workspace.get("members") if isinstance(workspace, dict) else None
    if isinstance(members, list):
        for entry in members:
            if not isinstance(entry, str) or not entry:
                continue
            member_root = (root / entry).resolve()
            cargo_member = member_root / "Cargo.toml"
            if not cargo_member.is_file():
                # Globbed entries are uncommon for graph_os repos; skip
                # silently rather than spamming WARN.
                continue
            try:
                with cargo_member.open("rb") as fh:
                    sub = tomllib.load(fh)
            except (OSError, _toml_error()):
                continue
            sub_pkg = sub.get("package") or {}
            sub_name = sub_pkg.get("name") if isinstance(sub_pkg, dict) else None
            if isinstance(sub_name, str) and sub_name:
                try:
                    rel = member_root.relative_to(root).as_posix()
                except ValueError:
                    continue
                crates[sub_name] = rel
    return crates


# ---------------------------------------------------------------------------
# pyproject.toml + setup.cfg — package roots
# ---------------------------------------------------------------------------


def _load_python_packages(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    pyproject = root / "pyproject.toml"
    data: dict[str, Any] = {}
    if pyproject.is_file() and tomllib is not None:
        try:
            with pyproject.open("rb") as fh:
                data = tomllib.load(fh)
        except (OSError, _toml_error()) as exc:
            logger.warning("pyproject.toml parse failed: %s", exc)
            data = {}

    # PEP 621 [project] name — points at root by convention; only
    # useful when the package directory matches the project name.
    project = data.get("project") or {}
    if isinstance(project, dict):
        proj_name = project.get("name")
        if isinstance(proj_name, str) and proj_name:
            # Try src-layout first, then flat-layout.
            for candidate in (f"src/{proj_name}", proj_name):
                if (root / candidate).is_dir():
                    out[proj_name] = candidate
                    break

    # [tool.poetry.packages] = [{include = "myapp", from = "src"}]
    tool = data.get("tool") or {}
    poetry = tool.get("poetry") or {}
    if isinstance(poetry, dict):
        packages = poetry.get("packages") or []
        if isinstance(packages, list):
            for entry in packages:
                if not isinstance(entry, dict):
                    continue
                include = entry.get("include")
                from_ = entry.get("from", "")
                if not isinstance(include, str) or not include:
                    continue
                rel = f"{from_.rstrip('/')}/{include}" if from_ else include
                if (root / rel).is_dir():
                    out[include] = rel.replace("\\", "/")

    # [tool.setuptools.packages.find] / [tool.setuptools] package_dir
    setuptools = tool.get("setuptools") or {}
    if isinstance(setuptools, dict):
        package_dir = setuptools.get("package-dir") or {}
        if isinstance(package_dir, dict):
            for name, rel in package_dir.items():
                if name and isinstance(rel, str) and (root / rel).is_dir():
                    out[name] = rel.replace("\\", "/")

    return out


__all__ = [
    "ToolchainContext",
    "get_active",
    "load_toolchain",
    "reset_cache",
    "set_active",
]
