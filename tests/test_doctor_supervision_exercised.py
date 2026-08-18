"""supervision.routing_exercised — enabled-but-inert is reported (TASK-1012).

model_routing.enabled sat true for days while nothing ever dispatched. The
policy validated, the banner showed a route, and no check compared the toggle
against the evidence — so an enabled feature looked identical to a disabled one.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cli._doctor_shared import DoctorReport
from cli._doctor_supervision import _check_supervision_exercised


def _state(tmp_path: Path, policy: dict, rows: list[tuple[str, str]] | None = None) -> Path:
    state = tmp_path / ".coding-os"
    state.mkdir()
    (state / "hub-settings.json").write_text(json.dumps({"model_routing": policy}))
    if rows is not None:
        with sqlite3.connect(state / "coding-os.db") as conn:
            conn.execute(
                "CREATE TABLE formula_dispatches (id INTEGER PRIMARY KEY, "
                "formula_id TEXT, adapter TEXT)"
            )
            conn.executemany(
                "INSERT INTO formula_dispatches (formula_id, adapter) VALUES (?,?)", rows
            )
    return state


def _run(state: Path) -> object:
    report = DoctorReport(project_dir=str(state.parent), agent="claude", templates=["meta"])
    _check_supervision_exercised(state.parent, state, report)
    return next(c for c in report.checks if c.id == "supervision.routing_exercised")


_ENABLED = {"enabled": True, "mode": "explicit", "roles": {"reviewer": {"adapter": "codex"}}}


class TestExercised:
    def test_warns_when_enabled_but_never_routed(self, tmp_path: Path) -> None:
        check = _run(_state(tmp_path, _ENABLED, rows=[]))
        assert check.severity == "WARN"
        assert "no dispatch has ever recorded an adapter" in check.message

    def test_warns_when_only_unattributed_rows_exist(self, tmp_path: Path) -> None:
        # Legacy/synthetic rows with a NULL adapter are not evidence of routing.
        check = _run(_state(tmp_path, _ENABLED, rows=[("reviewer", None), ("analyst", "")]))
        assert check.severity == "WARN"

    def test_passes_and_tallies_once_routed(self, tmp_path: Path) -> None:
        check = _run(
            _state(tmp_path, _ENABLED, rows=[("reviewer", "codex"), ("architect", "claude")] * 2)
        )
        assert check.severity == "PASS"
        assert "codex=2" in check.message and "claude=2" in check.message

    def test_skips_when_supervision_is_off(self, tmp_path: Path) -> None:
        check = _run(_state(tmp_path, {"enabled": False}, rows=[]))
        assert check.severity == "PASS"
        assert "disabled" in check.message

    def test_skips_when_no_database_yet(self, tmp_path: Path) -> None:
        check = _run(_state(tmp_path, _ENABLED, rows=None))
        assert check.severity == "PASS"
