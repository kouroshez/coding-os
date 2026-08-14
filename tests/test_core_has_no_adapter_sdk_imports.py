"""P8: the kernel never imports an adapter's SDK.

`src/core/**` reached for `claude_agent_sdk` in three places — the chat runtime,
the dispatch-availability probe, and transcript-directory resolution — so a
Codex-only install reported dispatch unavailable and the kernel encoded one
runtime's on-disk layout. Each now resolves through the adapter registry, which
already carried `sdk_package` and `runtime_entrypoints` for exactly this.

The rule is asserted structurally rather than by behaviour: an import is easy to
re-add and hard to notice, and every guard here was written after finding one.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
CORE = REPO / "src" / "core"
sys.path.insert(0, str(REPO / "src"))


# Distribution names declared by adapters; an import of any of these from core
# is the violation. Read from the manifests so a new adapter is covered for free.
def _adapter_sdk_modules() -> set[str]:
    import yaml

    modules: set[str] = set()
    for manifest in (REPO / "src" / "adapters").glob("*/adapter.yaml"):
        data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        package = str(data.get("sdk_package") or "").strip()
        if package:
            modules.add(package.replace("-", "_"))
    return modules


def _core_modules() -> list[Path]:
    return [
        path
        for path in CORE.rglob("*.py")
        if "/tests/" not in str(path) and not path.name.startswith("test_")
    ]


def test_adapters_declare_sdk_packages() -> None:
    assert _adapter_sdk_modules(), "no adapter declares sdk_package — this guard would be vacuous"


def test_no_core_module_imports_an_adapter_sdk() -> None:
    forbidden = _adapter_sdk_modules()
    offenders: list[str] = []
    for path in _core_modules():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name in forbidden:
                    rel = path.relative_to(REPO)
                    offenders.append(f"{rel}:{node.lineno} imports {name}")
    assert not offenders, "P8 violated — kernel imports an adapter SDK:\n  " + "\n  ".join(
        offenders
    )


@pytest.mark.parametrize(
    "resolver",
    [
        "web.routes._cognition_chat_sdk:_claude_sdk",
        "web.routes._presence_runtime:_transcript_dir",
        "web.routes.roles:_dispatch_available",
    ],
)
def test_each_rewired_seam_still_resolves(resolver: str) -> None:
    """Removing the import must not have removed the capability.

    A structural check alone would pass just as happily on a seam that resolves
    to None for everyone, which is why each is called for real.
    """
    import importlib

    module_name, func_name = resolver.split(":")
    func = getattr(importlib.import_module(module_name), func_name)
    result = func(Path(REPO)) if func_name == "_transcript_dir" else func()
    assert result is not None and result is not False, (
        f"{resolver} resolved to {result!r} — the seam is wired but dead"
    )
