"""Hub chat reaches a runtime through a port, not an SDK module's own surface.

Removing the literal `claude_agent_sdk` from the kernel moved the coupling
rather than ending it: core still called `sdk.list_sessions` /
`get_session_info` / `get_session_messages` / `query`, so a second in-process
runtime had to expose those four attribute names with those signatures by
coincidence. An adapter now declares the `chat` capability and implements
CHAT_PORT; core calls nothing else.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
ROUTES = REPO / "src" / "core" / "web" / "routes"
sys.path.insert(0, str(REPO / "src"))

from web.routes._cognition_chat_sdk import (
    CHAT_CAPABILITY,
    CHAT_PORT,
    _chat_runtime,
)


def test_core_calls_only_the_port() -> None:
    """Any `sdk.<name>` outside CHAT_PORT is a provider surface back in the kernel."""
    allowed = set(CHAT_PORT) | {"available", "requirement"}
    offenders: list[str] = []
    for path in ROUTES.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            if isinstance(value, ast.Name) and value.id == "sdk" and node.attr not in allowed:
                offenders.append(f"{path.name}:{node.lineno}: sdk.{node.attr}")
    assert not offenders, "core calls a runtime surface outside the port:\n  " + "\n  ".join(
        offenders
    )


def test_an_adapter_declares_and_implements_the_chat_port() -> None:
    implementers = []
    for manifest_path in (REPO / "src" / "adapters").glob("*/adapter.yaml"):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        entrypoints = manifest.get("runtime_entrypoints") or {}
        if CHAT_CAPABILITY not in (entrypoints.get("capabilities") or []):
            continue
        module_name = entrypoints.get(CHAT_CAPABILITY)
        assert module_name, f"{manifest_path.parent.name} declares chat with no entrypoint"
        assert (manifest_path.parent / module_name).is_file(), (
            f"{manifest_path.parent.name} points chat at a missing {module_name}"
        )
        implementers.append(manifest_path.parent.name)
    assert implementers, "no adapter implements the chat port — the guard would be vacuous"


def test_resolved_runtime_exposes_every_port_function() -> None:
    runtime = _chat_runtime()
    if runtime is None:
        pytest.skip("no chat runtime installed in this environment")
    missing = [name for name in CHAT_PORT if not callable(getattr(runtime, name, None))]
    assert not missing, f"resolved runtime is missing port functions: {missing}"
    assert inspect.isasyncgenfunction(runtime.stream_turn), (
        "stream_turn must be an async generator — the routes `async for` over it"
    )


def test_incomplete_implementation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A module that declares chat but misses a function must not be handed to the routes.

    Returning a partial module would surface as an AttributeError mid-stream, in
    a route, at the moment a user pressed send.
    """
    import types

    import web.routes._cognition_chat_sdk as chat_sdk
    from thinking_os.adapter_registry import AdapterRecord

    partial = types.ModuleType("partial_runtime")
    partial.list_sessions = lambda **_: []  # every other port function absent

    record = AdapterRecord(
        id="partial",
        path=REPO,
        manifest={"runtime_entrypoints": {"chat": "x.py", "capabilities": ["chat"]}},
    )
    monkeypatch.setattr(
        "thinking_os.adapter_registry.load_adapter_records", lambda: {"partial": record}
    )
    monkeypatch.setattr(
        "thinking_os.adapter_registry.load_entrypoint_module", lambda *_a, **_k: partial
    )
    assert chat_sdk._chat_runtime() is None
