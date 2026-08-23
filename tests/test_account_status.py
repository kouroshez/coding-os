"""Provider account state — the normalization contract and both live probes.

The point of these is the *refusals*. A quota panel that shows 0% when it knows
nothing is worse than one that shows nothing at all: the operator reads "plenty
left" off a number that was never measured. Every case below pins a way the
pipeline is allowed to say "I don't know".
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapters.claude import account_probe as claude_probe
from adapters.codex import account_probe as codex_probe
from thinking_os.account_status import (
    STALE_AFTER_SECONDS,
    age_of,
    normalize_report,
    unavailable,
    window_label,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


class TestWindowLabel:
    @pytest.mark.parametrize(
        ("minutes", "expected"),
        [(300, "5h"), (10080, "weekly"), (1440, "daily"), (20160, "2-weekly"), (45, "45m")],
    )
    def test_derives_from_duration(self, minutes: int, expected: str) -> None:
        # Derived, never mapped from the provider's own primary/secondary slot
        # names: codex puts the weekly window in `primary` when there is no
        # five-hour one, so a positional reading mislabels it.
        assert window_label(minutes) == expected

    def test_unknown_duration_is_not_invented(self) -> None:
        assert window_label(None) == "window"
        assert window_label(0) == "window"


class TestNormalize:
    def _payload(self, **over):
        base = {
            "status": "ok",
            "auth_mode": "subscription",
            "plan": "max",
            "observed_at": NOW.isoformat(),
            "windows": [{"percent": 40, "window_minutes": 300}],
        }
        base.update(over)
        return base

    def test_keeps_a_reported_window(self) -> None:
        report = normalize_report("claude", self._payload(), NOW)
        assert report["status"] == "ok"
        assert report["windows"][0] == {
            "label": "5h",
            "percent": 40.0,
            "resets_at": None,
            "severity": "normal",
            "window_minutes": 300,
            "scope": None,
        }

    def test_a_window_without_a_percent_is_dropped_not_zeroed(self) -> None:
        report = normalize_report("claude", self._payload(windows=[{"window_minutes": 300}]), NOW)
        assert report["status"] == "unavailable"
        assert report["windows"] == []

    def test_no_windows_means_unavailable_even_when_the_probe_said_ok(self) -> None:
        assert normalize_report("claude", self._payload(windows=[]), NOW)["status"] == "unavailable"

    def test_a_non_mapping_probe_result_cannot_crash_the_route(self) -> None:
        assert normalize_report("x", "boom", NOW)["status"] == "unavailable"
        assert normalize_report("x", None, NOW)["status"] == "unavailable"

    def test_an_unknown_severity_falls_back_rather_than_reaching_the_ui(self) -> None:
        payload = self._payload(windows=[{"percent": 1, "severity": "APOCALYPSE"}])
        assert normalize_report("claude", payload, NOW)["windows"][0]["severity"] == "normal"

    def test_windows_sort_shortest_first(self) -> None:
        payload = self._payload(
            windows=[
                {"percent": 1, "window_minutes": 10080},
                {"percent": 2, "window_minutes": 300},
            ]
        )
        labels = [w["label"] for w in normalize_report("c", payload, NOW)["windows"]]
        assert labels == ["5h", "weekly"]

    def test_a_fresh_reading_is_not_stale(self) -> None:
        recent = (NOW - timedelta(seconds=STALE_AFTER_SECONDS - 1)).isoformat()
        assert normalize_report("c", self._payload(observed_at=recent), NOW)["stale"] is False

    def test_an_old_reading_is_marked_stale(self) -> None:
        old = (NOW - timedelta(seconds=STALE_AFTER_SECONDS + 1)).isoformat()
        report = normalize_report("c", self._payload(observed_at=old), NOW)
        assert report["stale"] is True
        assert report["age_seconds"] == STALE_AFTER_SECONDS + 1

    def test_an_unparseable_timestamp_reports_unknown_age_not_zero(self) -> None:
        report = normalize_report("c", self._payload(observed_at="last tuesday"), NOW)
        assert report["age_seconds"] is None
        # Unknown age must not read as fresh — that is the failure this guards.
        assert report["stale"] is False and report["observed_at"] == "last tuesday"

    def test_unavailable_carries_its_reason(self) -> None:
        report = unavailable("codex", "no rollouts", "~/.codex")
        assert report["status"] == "unavailable"
        assert report["reason"] == "no rollouts"
        assert report["windows"] == []


class TestAgeOf:
    def test_a_naive_timestamp_is_read_as_utc(self) -> None:
        assert age_of("2026-08-21T11:00:00", NOW) == 3600

    def test_a_future_timestamp_clamps_to_zero(self) -> None:
        assert age_of("2026-08-21T13:00:00+00:00", NOW) == 0


class TestClaudeProbe:
    def _write(self, tmp_path: Path, payload: dict, monkeypatch) -> None:
        (tmp_path / ".claude.json").write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def test_reads_every_limit_row_including_the_scoped_one(self, tmp_path, monkeypatch) -> None:
        # The binding limit on this account was a per-model weekly cap at 78%
        # while the two headline windows read 0% and 49%. A panel that shows
        # only five_hour/seven_day hides the one about to bite.
        self._write(
            tmp_path,
            {
                "oauthAccount": {
                    "billingType": "stripe_subscription",
                    "organizationType": "claude_max",
                    "organizationRateLimitTier": "default_claude_max_20x",
                    "emailAddress": "someone@example.com",
                },
                "cachedUsageUtilization": {
                    "fetchedAtMs": 1787251725613,
                    "utilization": {
                        "limits": [
                            {"kind": "session", "group": "session", "percent": 0},
                            {"kind": "weekly_all", "group": "weekly", "percent": 49},
                            {
                                "kind": "weekly_scoped",
                                "group": "weekly",
                                "percent": 78,
                                "severity": "warning",
                                "scope": {"model": {"display_name": "Fable"}},
                            },
                        ]
                    },
                },
            },
            monkeypatch,
        )
        report = normalize_report("claude", claude_probe.probe_account(), NOW)
        assert [(w["label"], w["percent"]) for w in report["windows"]] == [
            ("5h", 0.0),
            ("weekly", 49.0),
            ("weekly · Fable", 78.0),
        ]
        assert report["plan"] == "claude_max (default_claude_max_20x)"
        assert report["auth_mode"] == "subscription"

    def test_no_identifying_field_leaves_the_probe(self, tmp_path, monkeypatch) -> None:
        # The same file holds the account email, org name and several uuids.
        # None of them are part of the contract, and a quota panel is not a
        # reason to start moving them around.
        self._write(
            tmp_path,
            {
                "oauthAccount": {
                    "billingType": "stripe_subscription",
                    "organizationType": "claude_max",
                    "emailAddress": "someone@example.com",
                    "accountUuid": "236e7d36-314b-4a01-9a28-2c78ac0c2cbf",
                    "organizationName": "someone@example.com's Organization",
                },
                "cachedUsageUtilization": {
                    "fetchedAtMs": 1787251725613,
                    "utilization": {
                        "limits": [{"kind": "session", "group": "session", "percent": 1}]
                    },
                },
            },
            monkeypatch,
        )
        blob = json.dumps(normalize_report("claude", claude_probe.probe_account(), NOW))
        for secret in ("someone@example.com", "236e7d36", "Organization"):
            assert secret not in blob

    def test_falls_back_to_the_named_windows_when_limits_is_absent(
        self, tmp_path, monkeypatch
    ) -> None:
        self._write(
            tmp_path,
            {
                "cachedUsageUtilization": {
                    "fetchedAtMs": 1787251725613,
                    "utilization": {
                        "five_hour": {"utilization": 12, "resets_at": "2026-08-21T14:00:00+00:00"},
                        "seven_day": {"utilization": 34},
                    },
                }
            },
            monkeypatch,
        )
        report = normalize_report("claude", claude_probe.probe_account(), NOW)
        assert [(w["label"], w["percent"]) for w in report["windows"]] == [
            ("5h", 12.0),
            ("weekly", 34.0),
        ]

    def test_an_api_key_in_the_environment_outranks_the_plan(self, tmp_path, monkeypatch) -> None:
        # The SDK bills the key, so the subscription the account also holds is
        # not what this dispatch spends.
        self._write(
            tmp_path,
            {
                "oauthAccount": {"billingType": "stripe_subscription"},
                "cachedUsageUtilization": {
                    "fetchedAtMs": 1787251725613,
                    "utilization": {
                        "limits": [{"kind": "session", "group": "session", "percent": 3}]
                    },
                },
            },
            monkeypatch,
        )
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        assert claude_probe.probe_account()["auth_mode"] == "api_key"

    def test_a_missing_config_reports_why(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "nope"))
        result = claude_probe.probe_account()
        assert result["status"] == "unavailable"
        assert "unreadable" in result["reason"]

    def test_a_config_without_a_usage_cache_says_how_to_populate_it(
        self, tmp_path, monkeypatch
    ) -> None:
        self._write(tmp_path, {"numStartups": 3}, monkeypatch)
        assert "/usage" in claude_probe.probe_account()["reason"]


class TestCodexProbe:
    def _rollout(self, home: Path, day: str, name: str, lines: list[str]) -> Path:
        directory = home / "sessions" / day[:4] / day[5:7] / day[8:10]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"rollout-{name}.jsonl"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def _limits_line(self, percent: float, minutes: int, plan: str = "plus") -> str:
        return json.dumps(
            {
                "timestamp": "2026-08-21T11:00:00.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "rate_limits": {
                        "primary": {
                            "used_percent": percent,
                            "window_minutes": minutes,
                            "resets_at": 1787339213,
                        },
                        "secondary": None,
                        "plan_type": plan,
                    },
                },
            }
        )

    def test_reads_the_newest_rollouts_rate_limits(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        (tmp_path / "auth.json").write_text(
            json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "secret"}}), encoding="utf-8"
        )
        self._rollout(tmp_path, "2026-08-21", "a", [self._limits_line(2.0, 10080)])
        report = normalize_report("codex", codex_probe.probe_account(), NOW)
        assert report["status"] == "ok"
        assert report["plan"] == "plus"
        assert report["auth_mode"] == "subscription"
        assert [(w["label"], w["percent"]) for w in report["windows"]] == [("weekly", 2.0)]

    def test_the_auth_token_never_leaves_the_probe(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        (tmp_path / "auth.json").write_text(
            json.dumps({"auth_mode": "chatgpt", "tokens": {"access": "sk-super-secret"}}),
            encoding="utf-8",
        )
        self._rollout(tmp_path, "2026-08-21", "a", [self._limits_line(2.0, 10080)])
        assert "sk-super-secret" not in json.dumps(codex_probe.probe_account())

    def test_the_last_block_in_the_file_wins(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        self._rollout(
            tmp_path,
            "2026-08-21",
            "a",
            [self._limits_line(2.0, 10080), "{not json", self._limits_line(9.0, 10080)],
        )
        report = normalize_report("codex", codex_probe.probe_account(), NOW)
        assert report["windows"][0]["percent"] == 9.0

    def test_a_resumed_older_session_is_still_found(self, tmp_path, monkeypatch) -> None:
        # A resumed session appends under its original date, so ranking day
        # directories alone would miss the freshest reading in the tree.
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        old = self._rollout(tmp_path, "2026-08-16", "old", [self._limits_line(7.0, 10080)])
        self._rollout(tmp_path, "2026-08-21", "new", ["{}"])
        import os

        os.utime(old, (2_000_000_000, 2_000_000_000))
        report = normalize_report("codex", codex_probe.probe_account(), NOW)
        assert report["windows"][0]["percent"] == 7.0

    def test_no_sessions_reports_why(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        result = codex_probe.probe_account()
        assert result["status"] == "unavailable"
        assert "no session rollouts" in result["reason"]

    def test_rollouts_without_limits_report_why(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        self._rollout(tmp_path, "2026-08-21", "a", ['{"type":"event_msg"}'])
        result = codex_probe.probe_account()
        assert result["status"] == "unavailable"
        assert "no rate_limits" in result["reason"]

    def test_an_api_key_in_the_environment_outranks_the_login(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_HOME", str(tmp_path))
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        (tmp_path / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt"}), encoding="utf-8")
        self._rollout(tmp_path, "2026-08-21", "a", [self._limits_line(2.0, 10080)])
        assert codex_probe.probe_account()["auth_mode"] == "api_key"
