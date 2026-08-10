"""graph_os — Python uid grammar and path-to-module-name resolution.

Leaf module: imports the shared path normaliser only, never a sibling walker.
Every uid emitted by the Python extractor is minted here so the grammar has one
definition site.
"""

from __future__ import annotations

from .md_links import _normalize_path

EXTRACTOR_ID = "code_python@v1"


# separate ID for the tree-sitter-primary import path so
# provenance_for() can distinguish ast-emitted edges from
# tree-sitter-emitted ones.
EXTRACTOR_ID_TS_IMPORTS = "code_python_ts@v1"


def file_uid(path: str) -> str:
    return f"code:file:{_normalize_path(path)}"


def module_uid(module_name: str) -> str:
    return f"code:module:{module_name}"


def class_uid(path: str, qualname: str) -> str:
    return f"code:class:{_normalize_path(path)}::{qualname}"


def function_uid(path: str, qualname: str) -> str:
    return f"code:function:{_normalize_path(path)}::{qualname}"


def method_uid(path: str, qualname: str) -> str:
    return f"code:method:{_normalize_path(path)}::{qualname}"


def _module_name_for_path(path: str) -> str:
    """Derive a dotted module name from a file path.

    Resolution order:
      1. Active ToolchainContext (TASK-082): when pyproject.toml /
         setup.cfg declare a non-standard package root (e.g.
         ``[tool.poetry.packages] include="myapp" from="packages"``),
         honour it so `packages/myapp/auth.py` → `myapp.auth`.
      2. Hard-coded ``src/`` / ``core/`` strip — keeps coding-os and
         most src-layout projects working without a config file.
      3. Fall through: full POSIX path with `.py` and `__init__` removed.
    """
    parts = [p for p in _normalize_path(path).split("/") if p]
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][: -len(".py")]
    if parts and parts[-1] == "__init__":
        parts.pop()

    # 1. Toolchain-driven package root.
    rebased = _toolchain_python_module_parts(parts)
    if rebased is not None:
        return ".".join(rebased) or "__root__"

    # 2. Default repo-root shims.
    if parts and parts[0] in {"src", "core"}:
        parts = parts[1:]
    return ".".join(parts) or "__root__"


def _toolchain_python_module_parts(parts: list[str]) -> list[str] | None:
    """Try to rebase a file's path-parts under a known Python package
    root from the active ToolchainContext.  Returns the rebased parts
    (e.g. ``["myapp", "auth"]``) or None when no package root matches.
    """
    try:
        from ..toolchain import get_active
    except ImportError:
        return None
    ctx = get_active()
    if ctx is None:
        return None
    if not ctx.python_packages:
        return None
    flat = "/".join(parts)
    # Match longest root first so nested packages win over shallow ones.
    for pkg_name, pkg_root in sorted(ctx.python_packages.items(), key=lambda kv: -len(kv[1])):
        rel_root = pkg_root.strip("/").replace("\\", "/")
        if not rel_root:
            continue
        prefix = f"{rel_root}/"
        if flat.startswith(prefix):
            tail = flat[len(prefix) :]
            tail_parts = [p for p in tail.split("/") if p]
            return [pkg_name, *tail_parts]
        if flat == rel_root:
            return [pkg_name]
    return None


def _absolute_module_for(source_module: str | None, *, path: str) -> str:
    if not source_module:
        return ""
    if not source_module.startswith("."):
        return source_module
    file_module = _module_name_for_path(path)
    file_parts = file_module.split(".") if file_module != "__root__" else []
    leading = len(source_module) - len(source_module.lstrip("."))
    tail = source_module.lstrip(".")
    base = file_parts[:-leading] if leading <= len(file_parts) else []
    if tail:
        base = base + tail.split(".")
    return ".".join(base)
