#!/usr/bin/env python3
"""Regenerate core/doctor-config.yaml::schema from the live database.py state.

Run this after editing core/thinking_os/database.py::MIGRATIONS so doctor's
EXPECTED_TABLES + expected_version stay in sync with the migration chain.

The test `tests/test_expected_tables_fresh.py` guards this in CI.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCTOR_CONFIG = REPO_ROOT / "core" / "doctor-config.yaml"


def _introspect() -> tuple[int, list[str]]:
    """Run init_db on an empty DB and return (version, sorted_table_list)."""
    sys.path.insert(0, str(REPO_ROOT / "core" / "thinking_os"))
    from database import MIGRATIONS, init_db  # type: ignore

    version = max(m[0] for m in MIGRATIONS)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    try:
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        tables = sorted(
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not row[0].startswith("observations_fts") and not row[0].startswith("sqlite_")
        )
        conn.close()
    finally:
        Path(db_path).unlink(missing_ok=True)

    return version, tables


def main() -> int:
    version, tables = _introspect()
    data = yaml.safe_load(DOCTOR_CONFIG.read_text(encoding="utf-8"))
    schema = data.setdefault("schema", {})
    schema["expected_version"] = version
    schema["expected_tables"] = tables
    DOCTOR_CONFIG.write_text(
        yaml.dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[doctor-schema] version={version} tables={len(tables)} → {DOCTOR_CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
