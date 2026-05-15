"""Guard: core/doctor-config.yaml::schema snapshot must match live db.py.

If this test fails, `core/thinking_os/database.py::MIGRATIONS` has been updated
but the committed schema snapshot in `core/doctor-config.yaml` is stale.

Fix by running:

    uv run python scripts/regen_doctor_schema.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCTOR_CONFIG = REPO_ROOT / "src" / "core" / "doctor-config.yaml"


@pytest.mark.slow
def test_expected_tables_match_live_db() -> None:
    sys.path.insert(0, str(REPO_ROOT / "src" / "core" / "thinking_os"))
    from database import MIGRATIONS, init_db  # type: ignore

    live_version = max(m[0] for m in MIGRATIONS)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        live_tables = sorted(
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            if not row[0].startswith("observations_fts")
            and not row[0].startswith("sqlite_")
        )
        conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)

    cfg = yaml.safe_load(DOCTOR_CONFIG.read_text(encoding="utf-8"))
    committed_version = cfg["schema"]["expected_version"]
    committed_tables = list(cfg["schema"]["expected_tables"])

    assert committed_version == live_version, (
        f"schema version mismatch: committed={committed_version} live={live_version} "
        "— run `uv run python scripts/regen_doctor_schema.py`"
    )
    assert committed_tables == live_tables, (
        f"table list mismatch — run `uv run python scripts/regen_doctor_schema.py`\n"
        f"  committed: {committed_tables}\n"
        f"  live:      {live_tables}"
    )
