"""Smoke coverage for the third-party token-cost bench entrypoint.

Network-free: --help must exit 0, and a tiny local fixture repo must
produce a well-formed report with every workflow summarized.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1] / "bench" / "third_party.py"


def test_help_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(BENCH), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    assert "--repo" in result.stdout


def test_local_fixture_repo_produces_report(tmp_path: Path) -> None:
    repo = tmp_path / "mini"
    repo.mkdir()
    (repo / "core.py").write_text(
        "def shared_helper(x):\n    return x + 1\n\n"
        "def caller_one(x):\n    return shared_helper(x)\n",
        encoding="utf-8",
    )
    (repo / "app.py").write_text(
        "from core import shared_helper\n\n"
        "def caller_two(x):\n    return shared_helper(x) * 2\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, str(BENCH), "--repo", str(repo), "--queries", "2", "--out", str(out)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["files"] == 2
    for workflow in ("references", "impact", "rename_plan"):
        assert report["summary"][workflow]["probes"] == 2
    assert all(row["graph_tokens"] >= 1 for row in report["probes"])
