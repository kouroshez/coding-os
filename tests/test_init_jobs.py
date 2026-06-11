"""TASK-362 — init job tracking: phases, cancel+cleanup, replay, funnel counters.

Uses tiny `python -c` subprocesses instead of a real `cos init` — the unit
under test is the job lifecycle, not the scaffold (covered by test_cli.py).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from web import init_jobs  # noqa: E402


def _wait_terminal(job, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if job.snapshot()["status"] != "running":
            return job.snapshot()
        time.sleep(0.05)
    raise AssertionError(f"job stuck running: {job.snapshot()}")


def _py(script: str) -> list[str]:
    return [sys.executable, "-u", "-c", script]


def _parse_json_payload(lines: list[str]) -> dict:
    import json

    json_lines = [line for line in lines if line.strip().startswith("{")]
    return json.loads(json_lines[-1]) if json_lines else {}


def test_happy_path_phases_payload_and_counter(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    started_before = init_jobs.COUNTERS["started"]
    succeeded_before = init_jobs.COUNTERS["succeeded"]
    script = (
        "print('Initializing coding-os in /x');"
        "print('Installing claude adapter...');"
        "print('Composed 3 .coding-os config(s)');"
        "print('{\"slug\": \"proj\", \"status\": \"ok\"}')"
    )
    job = init_jobs.start_job(_py(script), target, str(tmp_path), _parse_json_payload)
    snap = _wait_terminal(job)
    assert snap["status"] == "succeeded"
    assert snap["phase"] == "done"
    assert snap["result"]["slug"] == "proj"
    assert any("Installing" in line for line in snap["log"])
    assert init_jobs.COUNTERS["started"] == started_before + 1
    assert init_jobs.COUNTERS["succeeded"] == succeeded_before + 1


def test_failure_cleans_partial_scaffold_and_reports_tail(tmp_path: Path) -> None:
    target = tmp_path / "halfbaked"
    script = (
        f"import os; os.makedirs({str(target)!r});"
        "print('Initializing coding-os in /x');"
        "print('ERROR: boom');"
        "raise SystemExit(3)"
    )
    job = init_jobs.start_job(_py(script), target, str(tmp_path), lambda lines: {})
    snap = _wait_terminal(job)
    assert snap["status"] == "failed"
    assert "boom" in snap["error"]
    assert not target.exists()  # rollback removed the partial dir
    assert snap["cleanup"]["removed_dir"] == str(target)


def test_cancel_terminates_and_reports_cleanup(tmp_path: Path) -> None:
    target = tmp_path / "cancelme"
    script = (
        f"import os, time; os.makedirs({str(target)!r});"
        "print('Initializing coding-os in /x', flush=True);"
        "time.sleep(30)"
    )
    cancelled_before = init_jobs.COUNTERS["cancelled"]
    job = init_jobs.start_job(_py(script), target, str(tmp_path), lambda lines: {})
    deadline = time.time() + 10
    while not target.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert init_jobs.cancel_job(job.job_id) is job
    snap = _wait_terminal(job)
    assert snap["status"] == "cancelled"
    assert not target.exists()
    assert snap["cleanup"]["removed_dir"] == str(target)
    assert init_jobs.COUNTERS["cancelled"] == cancelled_before + 1


def test_log_slice_replays_then_follows(tmp_path: Path) -> None:
    job = init_jobs.start_job(
        _py("print('a');print('b');print('c')"), tmp_path / "x", str(tmp_path), lambda lines: {}
    )
    _wait_terminal(job)
    lines, offset = job.log_slice(0)
    assert lines[:3] == ["a", "b", "c"]
    again, _ = job.log_slice(offset)
    assert again == []  # nothing new after the offset


def test_cancel_unknown_job_returns_none() -> None:
    assert init_jobs.cancel_job("job-nope") is None


def test_gc_drops_old_terminal_jobs(tmp_path: Path) -> None:
    job = init_jobs.start_job(_py("print('x')"), tmp_path / "g", str(tmp_path), lambda lines: {})
    _wait_terminal(job)
    job.created_at = time.time() - 7200
    removed = init_jobs.gc_jobs(max_age_secs=3600)
    assert removed >= 1
    assert init_jobs.get_job(job.job_id) is None


def test_render_counters_prometheus_shape() -> None:
    text = init_jobs.render_counters()
    assert "# TYPE cos_init_jobs_total counter" in text
    assert 'cos_init_jobs_total{status="started"}' in text
