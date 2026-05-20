"""Inspect ClaudeAgentOptions schema — exploratory probe for Q.2 dispatcher hardening.

before editing adapters/claude/sdk_dispatcher.py. Source-of-truth doc:
docs/adapters/claude-sdk.md.
"""

from __future__ import annotations

import dataclasses
import inspect

import claude_agent_sdk as sdk


def dump(cls: type) -> None:
    print(f"\n=== {cls.__name__} ===")
    if dataclasses.is_dataclass(cls):
        for field in dataclasses.fields(cls):
            default = field.default
            if default is dataclasses.MISSING:
                default = "<no-default>"
            print(f"  {field.name}: {field.type}  default={default!r}")
        return
    try:
        sig = inspect.signature(cls)
    except (ValueError, TypeError) as exc:
        print(f"  (no signature available: {exc})")
        return
    for name, param in sig.parameters.items():
        print(f"  {name}: {param.annotation}  default={param.default!r}")


print(f"claude-agent-sdk version: {getattr(sdk, '__version__', '?')}")
dump(sdk.ClaudeAgentOptions)
dump(sdk.HookMatcher)
dump(sdk.AgentDefinition)

print("\n=== query() signature ===")
try:
    sig = inspect.signature(sdk.query)
except (ValueError, TypeError) as exc:
    print(f"  (no signature available: {exc})")
else:
    for name, param in sig.parameters.items():
        print(f"  {name}: {param.annotation}  default={param.default!r}")
