"""How a dotted Python module name maps onto a repo file path.

Leaf module: the link passes ask it whether a file is the module a stub names.
"""

from __future__ import annotations


def _names_module(real_file: str, module: str, declared: frozenset[str]) -> bool:
    # A declared dependency's name means a repo file only at that very path:
    # `import redis` is the library, never `proj/redis.py`.
    suffix = module.replace(".", "/")
    exact = (
        f"{suffix}.py",
        f"{suffix}/__init__.py",
        f"src/{suffix}.py",
        f"src/{suffix}/__init__.py",
    )
    if real_file in exact:
        return True
    if module.split(".")[0].lower() in declared:
        return False
    return real_file.endswith(f"/{suffix}.py") or real_file.endswith(f"/{suffix}/__init__.py")


def _dotted_path(file_path: str) -> str:
    stem = file_path[: -len(".py")] if file_path.endswith(".py") else file_path
    stem = stem.removesuffix("/__init__")
    return "." + stem.replace("/", ".")
