"""/api/cognition/cost carries the adapter dimension (TASK-1012).

A blended total cannot answer "what did Claude cost vs Codex", which is the only
reason to route work across providers. The route grouped by formula and day
only, so the split was unrecoverable from the API.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core.web.routes import cognition_dispatch_views as views

_SCHEMA = """
CREATE TABLE formula_dispatches (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
  formula_id TEXT NOT NULL, ts TEXT NOT NULL, status TEXT NOT NULL,
  cost_usd REAL, latency_ms INTEGER, adapter TEXT, model TEXT
);
"""

_ROWS = [
    ("s1", "reviewer", "2026-08-18T10:00:00", "ok", 0.50, 1000, "claude", "claude-opus-4-8"),
    ("s2", "reviewer", "2026-08-18T11:00:00", "ok", 0.25, 800, "codex", "gpt-5"),
    ("s3", "architect", "2026-08-18T12:00:00", "ok", 1.00, 1200, "claude", "claude-opus-4-8"),
    ("s4", "analyst", "2026-08-18T13:00:00", "ok", 0.10, 500, None, None),
]


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "coding-os.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        conn.executemany(
            "INSERT INTO formula_dispatches "
            "(session_id, formula_id, ts, status, cost_usd, latency_ms, adapter, model) "
            "VALUES (?,?,?,?,?,?,?,?)",
            _ROWS,
        )
    monkeypatch.setattr(views, "_db_path", lambda: path)
    return path


def _payload(**kwargs) -> dict:
    result = views.dispatcher_cost_summary(formula_id=None, limit=50, _rl=None, _m=None, **kwargs)
    return json.loads(result.body)["data"] if hasattr(result, "body") else result["data"]


class TestAdapterRollup:
    def test_splits_spend_by_adapter(self, db: Path) -> None:
        by_adapter = {r["adapter"]: r for r in _payload()["by_adapter"]}
        assert by_adapter["claude"]["total_cost_usd"] == pytest.approx(1.50)
        assert by_adapter["codex"]["total_cost_usd"] == pytest.approx(0.25)

    def test_null_adapter_reports_as_unattributed(self, db: Path) -> None:
        # Folding pre-attribution history into a real adapter would make the
        # split untrustworthy, which defeats the point of having it.
        by_adapter = {r["adapter"]: r for r in _payload()["by_adapter"]}
        assert by_adapter["unattributed"]["total_cost_usd"] == pytest.approx(0.10)
        assert "claude" in by_adapter and "codex" in by_adapter

    def test_total_covers_every_adapter(self, db: Path) -> None:
        assert _payload()["total_usd"] == pytest.approx(1.85)

    def test_rows_name_adapter_and_model(self, db: Path) -> None:
        rows = _payload()["rows"]
        assert all("adapter" in r and "model" in r for r in rows)
        reviewer = sorted(
            (r for r in rows if r["formula_id"] == "reviewer"), key=lambda r: r["adapter"]
        )
        # One (day, formula) now spans two adapters — previously one blended row.
        assert [r["adapter"] for r in reviewer] == ["claude", "codex"]

    def test_empty_database_still_returns_the_key(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(views, "_db_path", lambda: None)
        assert _payload()["by_adapter"] == []
