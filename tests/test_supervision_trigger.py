"""TASK-1001 — the routing policy actually applies, and the banner always shows.

Covers the two dead-trigger defects together, because they were one symptom to
the operator: model_routing sat `enabled: true` for days while nothing resolved
it per prompt, and the banner had no field that would have revealed that.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "src" / "core" / "hooks"
SESSION_CONTEXT = HOOKS / "session-context.sh"
RESOLVE_ROUTE = HOOKS / "resolve-supervise-route.sh"


_UNSEEDED = "unseeded-panel"


def _panel(tmp_path: Path, session_id: str = "ses-smoke") -> Path:
    # cos_panel_upgrade_from_payload() derives the panel dir from the payload's
    # session_id, so the fixture must place markers where the hook will look —
    # pinning COS_PANEL_DIR instead would test a path production never takes.
    panel = tmp_path / "panels" / (session_id or _UNSEEDED)
    panel.mkdir(parents=True, exist_ok=True)
    if session_id:
        (panel / "session-id").write_text(session_id, encoding="utf-8")
    return panel


def _write_settings(tmp_path: Path, routing: dict) -> None:
    state = tmp_path / ".coding-os"
    state.mkdir(parents=True, exist_ok=True)
    (state / "hub-settings.json").write_text(
        json.dumps({"model_routing": routing}), encoding="utf-8"
    )


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "COS_AGENT_DIR": str(tmp_path),
        "COS_PANEL_ID": "smoke",
        "COS_STATE_DIR": str(tmp_path),
        **extra,
    }


def _pulse(tmp_path: Path, mode: str, *, session_id: str = "ses-smoke") -> str:
    panel = _panel(tmp_path, session_id)
    (panel / ".task-mode").write_text(mode, encoding="utf-8")
    (tmp_path / ".task-mode").write_text(mode, encoding="utf-8")
    assert panel.is_dir()
    proc = subprocess.run(
        ["bash", str(SESSION_CONTEXT)],
        input=json.dumps({"session_id": session_id or _UNSEEDED, "prompt": "x"}).encode(),
        capture_output=True,
        timeout=30,
        env=_env(tmp_path),
    )
    return proc.stdout.decode(errors="ignore")


def _banner(output: str) -> str:
    for line in output.replace("\\n", "\n").splitlines():
        if "USER_BANNER" in line:
            return line
    return ""


class TestBannerAlwaysPresent:
    """A banner the operator sees only sometimes cannot be trusted at all."""

    def test_every_user_facing_mode_emits_a_banner(self, tmp_path: Path) -> None:
        for mode in ("formal", "query", "adhoc", "chore", "gov-required", "propose-formal"):
            target = tmp_path / mode
            target.mkdir()
            assert "USER_BANNER" in _pulse(target, mode), f"{mode} emitted no banner"

    def test_hook_internal_system_mode_is_the_only_suppression(self, tmp_path: Path) -> None:
        # Not an exception to the rule: classify-task-mode.sh never writes
        # `system` for a user prompt, so there is no reply to prefix.
        assert "USER_BANNER" not in _pulse(tmp_path, "system")

    def test_payload_without_session_id_still_emits(self, tmp_path: Path) -> None:
        # Turn 1 with no session_id in the payload and no runtime session var:
        # the panel id falls back to a PPID hash, so `ses=` still has a value and
        # the old `SES_TAIL`-empty suppression never actually fired. The banner is
        # nonetheless asserted unconditionally here — `${SES_TAIL:-new}` makes the
        # always-emit guarantee independent of that fallback continuing to work.
        (tmp_path / ".task-mode").write_text("formal", encoding="utf-8")
        env = {
            key: value
            for key, value in _env(tmp_path).items()
            if key not in {"CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CODEX_SESSION_ID"}
        }
        env.pop("COS_PANEL_ID", None)
        proc = subprocess.run(
            ["bash", str(SESSION_CONTEXT)],
            input=json.dumps({"prompt": "first ever turn"}).encode(),
            capture_output=True,
            timeout=30,
            env=env,
        )
        banner = _banner(proc.stdout.decode(errors="ignore"))
        assert banner, "no banner on an unseeded panel"
        assert "ses=" in banner and "mode=formal" in banner


class TestBannerRoutingField:
    def test_sup_field_names_the_resolved_route(self, tmp_path: Path) -> None:
        panel = _panel(tmp_path)
        (panel / ".supervise-route").write_text(
            json.dumps({"adapter": "codex", "model": "gpt-x", "effort": "high"}),
            encoding="utf-8",
        )
        assert "sup=codex/gpt-x/high" in _banner(_pulse(tmp_path, "formal"))

    def test_sup_rides_casual_modes_too(self, tmp_path: Path) -> None:
        # Which model answers is a cost fact the operator is owed on a one-liner.
        panel = _panel(tmp_path)
        (panel / ".supervise-route").write_text(json.dumps({"adapter": "claude"}), encoding="utf-8")
        assert "sup=claude" in _banner(_pulse(tmp_path, "query"))

    def test_suggest_mode_marks_the_route_as_a_proposal(self, tmp_path: Path) -> None:
        panel = _panel(tmp_path)
        (panel / ".supervise-route").write_text(
            json.dumps({"adapter": "claude", "mode": "suggest"}), encoding="utf-8"
        )
        assert "sup=claude?" in _banner(_pulse(tmp_path, "formal"))

    def test_no_route_file_costs_zero_characters(self, tmp_path: Path) -> None:
        assert "sup=" not in _banner(_pulse(tmp_path, "formal"))


class TestBannerPanelScope:
    def test_agent_level_roles_never_leak_into_a_fresh_panel(self, tmp_path: Path) -> None:
        # The observed defect: a six-day-old chain from another tab rendered as
        # this panel's active role. A neighbour's chain is a false statement the
        # operator cannot detect; '-' is a true one.
        (tmp_path / ".roles").write_text(json.dumps(["debugger", "reviewer"]), encoding="utf-8")
        (tmp_path / ".role").write_text("debugger", encoding="utf-8")
        banner = _banner(_pulse(tmp_path, "formal"))
        assert "roles=-" in banner
        assert "debugger" not in banner

    def test_panel_local_roles_are_shown(self, tmp_path: Path) -> None:
        panel = _panel(tmp_path)
        (panel / ".roles").write_text(json.dumps(["analyst", "implementer"]), encoding="utf-8")
        (panel / ".role").write_text("implementer", encoding="utf-8")
        assert "roles=implementer 2/2" in _banner(_pulse(tmp_path, "formal"))


def _resolve(tmp_path: Path, panel: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(RESOLVE_ROUTE)],
        input=b"{}",
        capture_output=True,
        timeout=30,
        env=_env(
            tmp_path,
            COS_STATE_DIR=str(tmp_path / ".coding-os"),
            COS_PANEL_DIR=str(panel),
            COS_PROJECT_ROOT=str(tmp_path),
        ),
    )


class TestRouteResolution:
    @staticmethod
    def _primed_panel(tmp_path: Path, role: str) -> Path:
        panel = _panel(tmp_path)
        (panel / ".thinking_os-gate").write_text("ses-smoke COMPLICATED 3", encoding="utf-8")
        (panel / ".role").write_text(role, encoding="utf-8")
        (panel / ".roles").write_text(json.dumps([role]), encoding="utf-8")
        return panel

    def test_disabled_policy_writes_nothing(self, tmp_path: Path) -> None:
        _write_settings(tmp_path, {"enabled": False})
        panel = self._primed_panel(tmp_path, "reviewer")
        _resolve(tmp_path, panel)
        assert not (panel / ".supervise-route").exists()

    def test_pinned_role_resolves_to_its_policy_adapter(self, tmp_path: Path) -> None:
        _write_settings(
            tmp_path,
            {"enabled": True, "mode": "explicit", "roles": {"reviewer": {"adapter": "codex"}}},
        )
        panel = self._primed_panel(tmp_path, "reviewer")
        _resolve(tmp_path, panel)
        route = json.loads((panel / ".supervise-route").read_text())
        assert route["adapter"] == "codex"
        assert route["pinned"] == "1"
        assert route["role"] == "reviewer"

    def test_unpinned_role_falls_back_to_the_running_adapter(self, tmp_path: Path) -> None:
        # Mirrors dispatcher.dispatch_request: `request.adapter or _detect_agent()`.
        _write_settings(tmp_path, {"enabled": True, "mode": "explicit"})
        panel = self._primed_panel(tmp_path, "analyst")
        _resolve(tmp_path, panel)
        route = json.loads((panel / ".supervise-route").read_text())
        assert route["adapter"]
        assert route["pinned"] == ""

    def test_adaptive_below_threshold_reports_unrouted(self, tmp_path: Path) -> None:
        _write_settings(
            tmp_path,
            {"enabled": True, "mode": "adaptive", "complexity_threshold": "COMPLEX"},
        )
        panel = self._primed_panel(tmp_path, "reviewer")
        (panel / ".thinking_os-gate").write_text("ses-smoke CLEAR 1", encoding="utf-8")
        result = _resolve(tmp_path, panel)
        assert not (panel / ".supervise-route").exists()
        assert "below threshold" in result.stdout.decode(errors="ignore")

    def test_emits_the_adapter_in_agent_context(self, tmp_path: Path) -> None:
        _write_settings(
            tmp_path,
            {"enabled": True, "mode": "explicit", "roles": {"reviewer": {"adapter": "codex"}}},
        )
        panel = self._primed_panel(tmp_path, "reviewer")
        payload = json.loads(_resolve(tmp_path, panel).stdout.decode())
        context = payload["hookSpecificOutput"]["additionalContext"]
        assert "codex" in context
        assert "cos_dispatch_formula_run" in context

    def test_debounce_marker_tracks_the_active_role(self, tmp_path: Path) -> None:
        # A chain advance must re-resolve: the next role may be pinned elsewhere.
        _write_settings(
            tmp_path,
            {
                "enabled": True,
                "mode": "explicit",
                "roles": {"reviewer": {"adapter": "codex"}, "architect": {"adapter": "claude"}},
            },
        )
        panel = self._primed_panel(tmp_path, "reviewer")
        _resolve(tmp_path, panel)
        assert json.loads((panel / ".supervise-route").read_text())["adapter"] == "codex"

        (panel / ".role").write_text("architect", encoding="utf-8")
        _resolve(tmp_path, panel)
        assert json.loads((panel / ".supervise-route").read_text())["adapter"] == "claude"
