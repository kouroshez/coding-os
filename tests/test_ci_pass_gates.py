"""Every job CI Pass waits on must also be able to fail it.

A job can sit in `needs:` and be absent from the aggregate check — it then runs,
costs minutes, reports red, and merges anyway. That is not hypothetical: the
nightly slow suite spent months in exactly that state behind a `::warning`, and
a red run under a green CI Pass is precisely the shape of regression that
reaches `main`. A schedule-gated job may resolve `skipped`, which is fine; what
must never be tolerated is `failure`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CI = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
GATE_JOB = "ci-pass"


def _workflow() -> dict:
    return yaml.safe_load(CI.read_text())


def _gate_job(workflow: dict) -> dict:
    jobs = workflow["jobs"]
    for name, job in jobs.items():
        if str(job.get("name", "")).strip().lower() == "ci pass" or name == GATE_JOB:
            return job
    raise AssertionError(f"no CI Pass job in {CI}; jobs: {sorted(jobs)}")


def _gate_script(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job.get("steps", []))


def test_every_needed_job_is_checked_by_the_gate() -> None:
    workflow = _workflow()
    gate = _gate_job(workflow)
    needs = gate.get("needs") or []
    assert needs, "CI Pass declares no needs — it gates nothing"

    script = _gate_script(gate)
    unchecked = [job for job in needs if f"needs.{job}.result" not in script]
    assert not unchecked, (
        "CI Pass waits on these jobs but never inspects their result, so they "
        f"can fail silently: {unchecked}"
    )


def test_gate_never_downgrades_a_failure_to_a_warning() -> None:
    """A gate passes or fails; it does not advise.

    Asserted as "the script emits no ::warning::" rather than by tracing which
    branch guards which job — the nightly result was read through a shell
    variable, so a block-scoped check for `exit 1` found the *other* jobs' exit
    and passed. The absence of a warning annotation is decidable; the control
    flow around an indirected variable is not.
    """
    script = _gate_script(_gate_job(_workflow()))
    warnings = [line.strip() for line in script.splitlines() if "::warning" in line]
    assert not warnings, (
        "CI Pass downgrades a job result to an advisory annotation instead of "
        f"failing on it: {warnings}"
    )


def test_gate_can_fail() -> None:
    script = _gate_script(_gate_job(_workflow()))
    assert "exit 1" in script, "CI Pass has no failing path at all"


def test_macos_smoke_runs_on_every_push() -> None:
    """macOS is the primary platform; a nightly-only signal is a day-late signal."""
    jobs = _workflow()["jobs"]
    smoke = jobs.get("test-macos-smoke")
    assert smoke, "expected a per-push macOS smoke job"
    assert "macos" in str(smoke.get("runs-on", "")).lower()
    condition = str(smoke.get("if", ""))
    assert "schedule" not in condition, (
        f"macOS smoke is schedule-gated ({condition!r}) — it must run on every push"
    )


def test_frontend_job_runs_the_accessibility_suite() -> None:
    """The a11y suite exists and is green; CI has to actually run it."""
    jobs = _workflow()["jobs"]
    frontend = jobs.get("test-frontend")
    assert frontend, "expected a test-frontend job"
    script = "\n".join(str(step.get("run", "")) for step in frontend.get("steps", []))
    assert "test:a11y" in script, "test-frontend never invokes npm run test:a11y"
