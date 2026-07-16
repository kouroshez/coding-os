"""TASK-815 — a scaffold doc naming a module-owned slash command must carry the
matching module tag (file `| module:X` or an `<!-- if-module:X -->` block), so
tag coverage tracks the subsystem registry automatically instead of by hand."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "src" / "scripts" / "dev" / "audit_scaffold_module_tags.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("audit_scaffold_module_tags", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_scaffold_docs_tag_module_owned_commands() -> None:
    violations = _load_audit().collect_violations()
    assert not violations, "untagged module-command references:\n" + "\n".join(violations)
