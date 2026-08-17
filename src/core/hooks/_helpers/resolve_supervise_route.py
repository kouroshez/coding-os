"""Resolve where the active role would dispatch and stamp it for the banner.

Called by resolve-supervise-route.sh (UserPromptSubmit). A policy that nothing
reads per-prompt is indistinguishable from a policy that is switched off, which
is exactly how model_routing sat enabled-but-invisible: nudge-model-routing.sh
announced it, and nothing resolved it.

This helper answers one question — "if the active role dispatched right now,
where would it go?" — using the SAME precedence the dispatcher uses, then writes
`.supervise-route` (panel-scoped) so the transparency banner can name the
adapter/model and the agent can pass them to cos_dispatch_formula_run.

It is read-only with respect to providers: no child process, no token, no probe.
Execution stays an explicit act, because a real sub-session per prompt is a token
incident, not a feature.

USAGE
    python3 resolve_supervise_route.py <gate_class> <panel_dir>
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("resolve_supervise_route")

_THIS = Path(__file__).resolve()
_THINKING_OS = _THIS.parents[2] / "thinking_os"
if _THINKING_OS.is_dir() and str(_THINKING_OS) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS))


def _active_role(panel_dir: Path) -> str:
    # Panel-scoped with no agent-level fallback, deliberately: a neighbouring
    # tab's chain rendered as this panel's role is a false statement the operator
    # cannot detect, where an empty role is a true one.
    try:
        role = (panel_dir / ".role").read_text(encoding="utf-8").strip()
    except OSError:
        role = ""
    if role:
        return role.split()[-1] if " " in role else role
    try:
        chain = json.loads((panel_dir / ".roles").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(chain[0]) if isinstance(chain, list) and chain else ""


def _default_adapter() -> str:
    try:
        from dispatcher import _detect_agent

        return _detect_agent()
    except Exception as exc:
        logger.debug("adapter detection unavailable: %s", exc)
        return (os.environ.get("COS_AGENT") or "").strip().lower()


def _write_route(panel_dir: Path, route: dict[str, str]) -> None:
    try:
        panel_dir.mkdir(parents=True, exist_ok=True)
        target = panel_dir / ".supervise-route"
        target.write_text(json.dumps(route, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.debug(".supervise-route write failed: %s", exc)


def _clear_route(panel_dir: Path) -> None:
    try:
        (panel_dir / ".supervise-route").unlink()
    except OSError:
        pass


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    gate_class = (argv[1] or "").upper()
    panel_dir = Path(argv[2])

    try:
        from _supervision_policy import load_policy, policy_applies, role_policy
    except ImportError as exc:
        # Non-zero on purpose: the caller logs a breadcrumb. A bare `python3`
        # lacks the project's deps, and swallowing that is how the sibling
        # compose trigger sat dead for days while its debounce marker made it
        # look like it had run.
        logger.debug("supervision policy unavailable: %s", exc)
        print(f"import failed: {exc}", file=sys.stderr)
        return 3

    try:
        policy = load_policy()
    except Exception as exc:
        logger.debug("load_policy failed: %s", exc)
        return 0

    if not policy.get("enabled"):
        _clear_route(panel_dir)
        return 0

    mode = str(policy.get("mode") or "explicit")
    # Under `adaptive` a request below the threshold is genuinely unsupervised;
    # reporting a route there would claim a policy that will not apply.
    if not policy_applies(policy, gate_class):
        _clear_route(panel_dir)
        print(f"[supervise] mode={mode} — gate {gate_class or 'unset'} is below threshold, unrouted")
        return 0

    role = _active_role(panel_dir)
    try:
        resolved = role_policy(role, complexity=gate_class)
    except Exception as exc:
        logger.debug("role_policy failed: %s", exc)
        return 0

    # Mirror dispatcher.dispatch_request: an unpinned role lands on the current
    # runtime, so reporting "-" there would hide the answer rather than admit it.
    adapter = resolved.get("adapter") or _default_adapter()
    if not adapter:
        _clear_route(panel_dir)
        return 0

    route = {
        "adapter": adapter,
        "model": resolved.get("model") or "",
        "effort": resolved.get("effort") or "",
        "role": role,
        "mode": mode,
        "gate": gate_class,
        "pinned": "1" if resolved.get("adapter") else "",
    }
    _write_route(panel_dir, route)

    target = adapter
    if route["model"]:
        target += f"/{route['model']}"
    if route["effort"]:
        target += f"/{route['effort']}"
    origin = "policy" if route["pinned"] else "session default"
    if mode == "suggest":
        print(
            f"[supervise] mode=suggest — role={role or '-'} would route to {target} "
            f"({origin}); report it, do NOT dispatch on it."
        )
    else:
        print(
            f"[supervise] mode={mode} — role={role or '-'} routes to {target} ({origin}). "
            f"Pass adapter='{adapter}'"
            + (f" model='{route['model']}'" if route["model"] else "")
            + " to cos_dispatch_formula_run when you dispatch."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
