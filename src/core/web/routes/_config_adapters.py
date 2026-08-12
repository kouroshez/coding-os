"""Per-capability adapter probing for the Hub Config + chat pickers.

One reason to change: how an adapter's runtime readiness is determined.

`runtime: in_process | roadmap` is a manifest *authoring* label, not a runtime
fact. Deriving availability from it made the Hub state the opposite of reality:
codex resolved a working CLI dispatcher and a working chat SDK while the picker
still read "coming soon", because a string in a YAML file said so. Readiness is
therefore probed per capability, and an unavailable one carries the reason and
the command that fixes it rather than an indefinite promise.
"""

from __future__ import annotations

import importlib.util
import logging

from thinking_os.adapter_registry import (
    AdapterRecord,
    entrypoint_path,
    load_entrypoint_module,
)

logger = logging.getLogger(__name__)

TRANSCRIPT_CAPABILITY = "transcript"
DISPATCH_CAPABILITY = "dispatch"
# The Hub generates a chat turn by driving an agent SDK inside its own process.
# `runtime: in_process` is a manifest's declaration that it can be driven that
# way; anything else can still be dispatched or read, just not streamed live.
IN_PROCESS_RUNTIME = "in_process"
_CHAT_SDK_MODULE = "claude_agent_sdk"


def _entrypoint(record: AdapterRecord, capability: str):
    if capability not in record.capabilities or entrypoint_path(record, capability) is None:
        return None
    return load_entrypoint_module(record, capability)


def _call(module, name: str, default):
    func = getattr(module, name, None)
    if not callable(func):
        return default
    try:
        return func()
    except Exception as exc:
        logger.debug("%s.%s failed: %s", getattr(module, "__name__", "?"), name, exc)
        return default


def probe_chat(record: AdapterRecord) -> dict:
    """Whether the Hub can stream a live chat turn from this adapter."""
    if str(record.manifest.get("runtime") or "") != IN_PROCESS_RUNTIME:
        return {
            "available": False,
            "declared": False,
            "missing": "an in-process chat runtime",
            "remedy": "",
        }
    if importlib.util.find_spec(_CHAT_SDK_MODULE) is None:
        return {
            "available": False,
            "declared": True,
            "missing": f"the {_CHAT_SDK_MODULE.replace('_', '-')} package",
            "remedy": "uv sync --extra claude-sdk",
        }
    return {"available": True, "declared": True, "missing": "", "remedy": ""}


def probe_transcript(record: AdapterRecord) -> dict:
    """Whether this adapter's past sessions can be listed and read in the Hub."""
    module = _entrypoint(record, TRANSCRIPT_CAPABILITY)
    if module is None:
        return {
            "available": False,
            "declared": False,
            "missing": "a transcript provider",
            "remedy": "",
        }
    if _call(module, "available", False):
        return {"available": True, "declared": True, "missing": "", "remedy": ""}
    requirement = _call(module, "requirement", {}) or {}
    return {
        "available": False,
        "declared": True,
        "missing": str(requirement.get("missing") or "an unmet runtime dependency"),
        "remedy": str(requirement.get("remedy") or ""),
    }


def probe_dispatch(record: AdapterRecord) -> dict:
    """Whether this adapter can execute a dispatched role, and why not if it cannot."""
    module = _entrypoint(record, DISPATCH_CAPABILITY)
    if module is None:
        return {
            "available": False,
            "declared": False,
            "missing": "a dispatcher",
            "remedy": "",
        }
    factory = getattr(module, "build_dispatcher", None)
    dispatcher = None
    if callable(factory):
        try:
            dispatcher = factory()
        except Exception as exc:
            logger.debug("%s dispatch readiness failed: %s", record.id, exc)
    if dispatcher is not None and dispatcher.available():
        return {"available": True, "declared": True, "missing": "", "remedy": ""}
    requirement = _call(module, "requirement", {}) or {}
    return {
        "available": False,
        "declared": True,
        "missing": str(requirement.get("missing") or "an unmet runtime dependency"),
        "remedy": str(requirement.get("remedy") or ""),
    }


def resolve_models(record: AdapterRecord) -> list[dict]:
    """Models this adapter offers — discovered from its runtime, else its manifest.

    Discovery wins because a manifest list is authored once and drifts; the
    adapter reading its own config reports what the next turn will actually use.
    """
    module = _entrypoint(record, TRANSCRIPT_CAPABILITY)
    discovered = _call(module, "discovered_models", []) if module is not None else []
    rows: list[dict] = []
    source = discovered if isinstance(discovered, list) and discovered else record.models
    for model in source:
        if not isinstance(model, dict) or not model.get("id"):
            continue
        rows.append(
            {
                "id": str(model["id"]),
                "label": str(model.get("label") or model["id"]),
                "default": bool(model.get("default")),
            }
        )
    return rows
