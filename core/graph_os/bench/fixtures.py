"""Deterministic fixture generators (I.13).

PURPOSE:  Produce N Python / TS / markdown files with stable content
          so benchmark runs are reproducible (P-I-11 determinism).
INPUT:    target directory + size knobs.
OUTPUT:   list of produced paths.
DEPENDS:  stdlib only.
"""

from __future__ import annotations

from pathlib import Path


def build_python_corpus(root: Path, *, count: int) -> list[Path]:
    """Generate `count` small Python modules that import each other."""
    root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(count):
        target = root / f"mod_{i:04d}.py"
        imports = ""
        if i > 0:
            imports = f"from mod_{(i - 1):04d} import helper\n"
        body = (
            f"{imports}"
            f"def helper(x: int) -> int:\n"
            f"    \"\"\"stable docstring for mod_{i:04d}.\"\"\"\n"
            f"    return x + {i}\n\n"
            f"class Thing{i}:\n"
            f"    def run(self, n: int) -> int:\n"
            f"        return helper(n)\n"
        )
        target.write_text(body, encoding="utf-8")
        paths.append(target)
    return paths


def build_mixed_corpus(root: Path, *, size: int = 100) -> list[Path]:
    """Generate a heterogeneous corpus for contracts + docs coverage."""
    paths: list[Path] = []
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "backend").mkdir(parents=True, exist_ok=True)
    for i in range(size):
        (root / "docs" / f"spec_{i}.md").write_text(
            f"# Spec {i}\n\nSee [other](./spec_{(i + 1) % size}.md).\n",
            encoding="utf-8",
        )
        (root / "backend" / f"route_{i}.py").write_text(
            f"from fastapi import APIRouter\n"
            f"router = APIRouter()\n\n"
            f"@router.get('/items/{i}')\n"
            f"def get_item_{i}(): return {{'i': {i}}}\n",
            encoding="utf-8",
        )
    paths.extend((root / "docs").glob("*.md"))
    paths.extend((root / "backend").glob("*.py"))
    return paths


__all__ = ["build_python_corpus", "build_mixed_corpus"]
