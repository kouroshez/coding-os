"""resolve_chain — the composed role chain the live-agent cards show."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes._role_chain import resolve_chain


def _agent_dir(tmp_path: Path) -> Path:
    agent_dir = tmp_path / "claude"
    (agent_dir / "traces").mkdir(parents=True)
    return agent_dir


def test_reads_the_markers_when_no_trace_exists(tmp_path):
    agent_dir = _agent_dir(tmp_path)
    (agent_dir / ".roles").write_text(json.dumps(["F1", "F2", "F5"]), encoding="utf-8")
    (agent_dir / ".role").write_text("F2", encoding="utf-8")

    assert resolve_chain(tmp_path, "claude") == (["F1", "F2", "F5"], "F2")


def test_trace_wins_over_a_stale_marker(tmp_path):
    # Under concurrent panels the .roles marker can be stale; the newest
    # agent-level compose_done trace is the consistent source.
    agent_dir = _agent_dir(tmp_path)
    (agent_dir / ".roles").write_text(json.dumps(["analyst"]), encoding="utf-8")
    (agent_dir / ".role").write_text("reviewer", encoding="utf-8")
    (agent_dir / "traces" / "ses-x.jsonl").write_text(
        json.dumps({"kind": "compose_done", "data": {"chain": ["refactorer", "reviewer"]}}) + "\n",
        encoding="utf-8",
    )

    assert resolve_chain(tmp_path, "claude") == (["refactorer", "reviewer"], "reviewer")


def test_newest_panel_marker_wins(tmp_path):
    agent_dir = _agent_dir(tmp_path)
    (agent_dir / ".role").write_text("analyst", encoding="utf-8")
    panel = agent_dir / "panels" / "p1"
    panel.mkdir(parents=True)
    (panel / ".role").write_text("implementer", encoding="utf-8")

    assert resolve_chain(tmp_path, "claude")[1] == "implementer"


def test_comma_separated_marker_is_accepted(tmp_path):
    agent_dir = _agent_dir(tmp_path)
    (agent_dir / ".roles").write_text("analyst, architect", encoding="utf-8")

    assert resolve_chain(tmp_path, "claude")[0] == ["analyst", "architect"]


def test_a_traversing_agent_reads_nothing(tmp_path):
    assert resolve_chain(tmp_path, "../etc") == ([], None)
