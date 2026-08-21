"""Dispatch the roles pinned to a provider other than the running session's.

Same-provider roles are deliberately NOT dispatched. A child rebuilds context from
scratch — measured at ~$0.56 and ~50s per role, 76k cache-creation tokens — so
delegating work the session could do itself is slower AND dearer for identical
capability. A second provider buys an independent blind spot; a sibling of
yourself buys nothing.

Runs detached from the hook: one codex dispatch measured 123s, and a PostToolUse
hook holding the tool call open that long would be worse than no trigger.
Contract: docs/engineering/agent-supervision.md § When dispatch fires by itself.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3]
for _path in (_SRC / "core", _SRC, _SRC / "core" / "thinking_os"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def load_policy(state_dir: Path) -> dict:
    try:
        raw = json.loads((state_dir / "hub-settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    policy = raw.get("model_routing")
    return policy if isinstance(policy, dict) else {}


def known_adapters() -> set[str]:
    try:
        return {p.name for p in (_SRC / "adapters").iterdir() if (p / "adapter.yaml").is_file()}
    except OSError:
        return set()


def cross_provider_roles(policy: dict, session_adapter: str) -> list[dict]:
    """Roles whose pinned adapter differs from the session's — the only ones worth spawning."""
    roles = policy.get("roles")
    if not isinstance(roles, dict):
        return []
    # Fail safe on an unrecognised session adapter. `fable` is a MODEL inside the
    # claude adapter, not an adapter; if a model id ever reaches this argument
    # every role looks cross-provider and one transition spawns the whole chain —
    # ~$6 instead of ~$0.6. Dispatching nothing is the recoverable direction.
    adapters = known_adapters()
    if adapters and session_adapter not in adapters:
        return []
    targets = []
    for role, target in sorted(roles.items()):
        if not isinstance(target, dict):
            continue
        adapter = str(target.get("adapter") or "").strip()
        if not adapter or adapter == session_adapter:
            continue
        targets.append(
            {
                "role": str(role),
                "adapter": adapter,
                "model": str(target.get("model") or ""),
                # Carried verbatim: an adapter without effort_selection rejects a
                # pinned effort outright rather than ignoring it, so the policy —
                # not this helper — is where a codex role keeps effort empty.
                "effort": str(target.get("effort") or ""),
            }
        )
    return targets


def adapter_timeout(adapter: str) -> float | None:
    """Wall-clock budget the adapter declares, or None to use the agent default.

    Role timeouts are calibrated on Claude (44-53s measured). Codex is materially
    slower — a successful review measured 123s against a 120s agent default and
    timed out at the finish line — so the budget is a per-adapter fact, declared
    in the descriptor rather than branched on here.
    """
    try:
        import yaml

        descriptor = _SRC / "adapters" / adapter / "adapter.yaml"
        data = yaml.safe_load(descriptor.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    declared = data.get("dispatch_timeout_s")
    return float(declared) if isinstance(declared, (int, float)) else None


def _seen(marker: Path, key: str) -> bool:
    try:
        return key in marker.read_text(encoding="utf-8").split("\n")
    except OSError:
        return False


def _remember(marker: Path, key: str) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("a", encoding="utf-8") as handle:
            handle.write(key + "\n")
    except OSError:
        pass


def _append(results_file: Path, payload: dict) -> None:
    try:
        results_file.parent.mkdir(parents=True, exist_ok=True)
        with results_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except OSError:
        pass


def _dispatch_one(target: dict, task_id: str, session_id: str, db_path: str) -> dict:
    import asyncio

    from thinking_os import dispatcher as _disp
    from thinking_os.tools._dispatch_persistence import _persist_dispatch_output
    from thinking_os.tools._dispatch_request import _build_dispatch_request

    role = target["role"]
    request = _build_dispatch_request(
        role,
        session_id,
        task_id,
        role,
        "standard",
        adapter_timeout(target["adapter"]),
        target["model"],
        "COMPLICATED",
        db_path,
        adapter=target["adapter"],
        effort=target["effort"],
    )
    result = asyncio.run(_disp.dispatch_request(request, db_path))
    route = {
        "adapter": request.adapter,
        "model": request.model,
        "effort": request.effort,
        "error_category": result.error_category,
        "error": result.error,
    }
    if result.output_json:
        _persist_dispatch_output(
            session_id=session_id,
            task_marker=task_id,
            persona_id=role,
            formula_id=role,
            output_json=result.output_json,
            status=result.status,
            latency_ms=result.latency_ms,
            db_path=db_path,
            raw_transcript=result.raw_transcript,
            resolved_route=route,
        )
    meta = result.output_json.get("_meta") if isinstance(result.output_json, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    return {
        "role": role,
        "adapter": meta.get("adapter") or target["adapter"],
        "model": meta.get("model") or request.model,
        "status": result.status,
        "cost_usd": meta.get("total_cost_usd"),
        "latency_ms": result.latency_ms,
        "error": (result.error or "")[:200] or None,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        return 0
    task_id, session_id, session_adapter = argv[1], argv[2], argv[3]
    state_dir = Path(os.environ.get("COS_STATE_DIR") or (_SRC.parent / ".coding-os"))
    panel_dir = Path(
        os.environ.get("COS_PANEL_DIR") or os.environ.get("COS_AGENT_DIR") or state_dir
    )

    policy = load_policy(state_dir)
    if not policy.get("enabled"):
        return 0
    targets = cross_provider_roles(policy, session_adapter)
    if not targets:
        return 0

    marker = panel_dir / ".auto-dispatched"
    results_file = panel_dir / ".dispatch-results"
    db_path = str(state_dir / "coding-os.db")

    for target in targets:
        key = f"{task_id}:{target['role']}"
        if _seen(marker, key):
            continue
        _remember(marker, key)
        try:
            _append(results_file, _dispatch_one(target, task_id, session_id, db_path))
        except Exception as exc:
            # A background dispatch must never surface as a crash in the parent.
            _append(
                results_file,
                {
                    "role": target["role"],
                    "adapter": target["adapter"],
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                },
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
