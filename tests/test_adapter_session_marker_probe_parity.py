"""Parity guard (TASK-213): every adapter's declared runtime_session_marker
env var MUST be probed by cos-env.sh::_cos_resolve_panel_id.

The shell kernel cannot parse adapter.yaml at source-time, so the panel-id
probe loop is a hand-maintained mirror of the adapters' declared markers. A
declared-but-unprobed marker is silently dead — that adapter's panels fall to
the unstable ppid fallback. This test makes the mirror non-driftable.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
COS_ENV = REPO / "src" / "core" / "hooks" / "cos-env.sh"
ADAPTERS = REPO / "src" / "adapters"


def _probe_env_vars() -> set[str]:
    # Join shell line-continuations so the multi-line `for v in … ; do` reads as one.
    joined = COS_ENV.read_text().replace("\\\n", " ")
    m = re.search(r"for\s+v\s+in\s+(.+?);\s*do", joined)
    assert m, "could not locate the panel-id probe loop in cos-env.sh"
    return {tok for tok in m.group(1).split() if re.fullmatch(r"[A-Z][A-Z0-9_]+", tok)}


def _adapter_markers() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for yml in sorted(ADAPTERS.glob("*/adapter.yaml")):
        data = yaml.safe_load(yml.read_text()) or {}
        marker = data.get("runtime_session_marker") or {}
        out[yml.parent.name] = list(marker.get("env_vars") or [])
    return out


def test_every_adapter_marker_is_probed() -> None:
    probe = _probe_env_vars()
    assert probe, "probe set parsed empty — the regex regressed against cos-env.sh"
    markers = _adapter_markers()
    assert markers, "no adapters discovered under src/adapters/*/adapter.yaml"

    drift = {
        adapter: [v for v in env_vars if v not in probe]
        for adapter, env_vars in markers.items()
    }
    drift = {adapter: missing for adapter, missing in drift.items() if missing}

    assert not drift, (
        "adapter.yaml declares session env vars the cos-env.sh probe does not read "
        f"(declared-but-dead markers): {drift}. Add each to the probe loop in "
        "cos-env.sh::_cos_resolve_panel_id, or remove it from adapter.yaml."
    )
