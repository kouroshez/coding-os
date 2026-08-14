"""The create-a-project endpoints: validate, scaffold, and follow the job.

`_run_cos_init` sits with its only caller because it is the seam a test replaces
to exercise the route without a real scaffold.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from fastapi import Body

from ._hub_init import (
    _build_cos_init_cmd,
    _parse_init_payload,
    _resolve_agents,
    _validate_init_inputs,
)
from ._hub_shared import _err, _resolve_slug_from_registry, router

logger = logging.getLogger("coding_os.web.hub")


def _run_cos_init(
    name: str,
    parent_dir: str,
    stacks: list[str],
    agents: list[str],
    preset: str = "",
    description: str = "",
    extra_skills: list[str] | None = None,
    disabled_modules: list[str] | None = None,
    timeout: int = 300,
):
    """Run `cos init` in a subprocess → (ok, payload, error).

    Default timeout has headroom over the in-init graph-build cap
    (COS_INIT_GRAPH_TIMEOUT, default 180s) so a slow graph build degrades to an
    empty graph inside init rather than the create subprocess being killed.

    Module-level so a test can monkeypatch it without a real scaffold.
    Description/extra-skills ride the CLI flags (--summary/--skills) so the
    wizard and a hand-typed `cos init` produce byte-identical projects."""
    cmd = _build_cos_init_cmd(
        name,
        parent_dir,
        stacks,
        agents,
        preset=preset,
        description=description,
        extra_skills=extra_skills,
        disabled_modules=disabled_modules,
    )
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=parent_dir)
    except subprocess.TimeoutExpired:
        return False, None, f"init timed out after {timeout}s"
    except OSError as exc:
        return False, None, f"could not launch cos init: {exc}"
    if proc.returncode != 0:
        return False, None, (proc.stderr or proc.stdout or "init failed").strip()[-400:]
    return True, _parse_init_payload((proc.stdout or "").splitlines()), ""


@router.post("/registry/validate-init")
def hub_registry_validate_init(
    name: str = Body("", embed=True),
    parent_dir: str = Body(..., embed=True),
    stacks: list[str] = Body(default_factory=list, embed=True),
    preset: str = Body("", embed=True),
    agent: str = Body("", embed=True),
    agents: list[str] = Body(default_factory=list, embed=True),
    extra_skills: list[str] = Body(default_factory=list, embed=True),
    disabled_modules: list[str] = Body(default_factory=list, embed=True),
):
    """Dry-run validation + merged-config preview for the onboarding wizard (TASK-358)."""
    resolved_agents = _resolve_agents(agent, agents)
    error, info = _validate_init_inputs(
        name,
        parent_dir,
        stacks,
        preset,
        resolved_agents,
        extra_skills=extra_skills,
        disabled_modules=disabled_modules,
    )
    if error is not None:
        return error
    swimlanes: list[str] = []
    conflicts: list[str] = []
    try:
        from cli.config_composer import preview_coding_os_configs  # type: ignore
        from cli.list_stacks import TEMPLATES_DIR  # type: ignore

        merged, conflicts = preview_coding_os_configs(
            info["templates"], templates_dir=TEMPLATES_DIR
        )
        scrumban = merged.get("scrumban-config.yaml") or {}
        swimlanes = [
            lane.get("id") for lane in scrumban.get("swimlanes") or [] if isinstance(lane, dict)
        ]
    except Exception as exc:
        logger.debug("dry-config preview failed: %s", exc)
    return {
        "data": {
            "valid": True,
            "name": info["name"],
            "auto_named": info["auto_named"],
            "target": str(info["target"]),
            "templates": info["templates"],
            "agents": info["agents"],
            "disabled_modules": info["disabled_modules"],
            "swimlanes": swimlanes,
            "conflicts": conflicts,
        },
        "meta": {"layer": "hub", "source": "hub.registry_validate_init"},
    }


@router.post("/registry/init")
def hub_registry_init(
    name: str = Body("", embed=True),
    parent_dir: str = Body(..., embed=True),
    stack: str = Body("", embed=True),
    stacks: list[str] = Body(default_factory=list, embed=True),
    preset: str = Body("", embed=True),
    agent: str = Body("", embed=True),
    agents: list[str] = Body(default_factory=list, embed=True),
    description: str = Body("", embed=True),
    extra_skills: list[str] = Body(default_factory=list, embed=True),
    disabled_modules: list[str] = Body(default_factory=list, embed=True),
    background: bool = Body(False, embed=True),
):
    """Scaffold a NEW project via `cos init` and register it (security-gated, TASK-249/358/362)."""
    all_stacks = [s for s in ((stacks or []) + ([stack] if stack else [])) if s]
    resolved_agents = _resolve_agents(agent, agents)
    error, info = _validate_init_inputs(
        name,
        parent_dir,
        all_stacks,
        preset,
        resolved_agents,
        extra_skills=extra_skills,
        disabled_modules=disabled_modules,
    )
    if error is not None:
        return error
    target: Path = info["target"]
    if background:
        # Job-based create: returns a job_id immediately; phases +
        # log stream over GET /api/hub/init-jobs/{id}/events.
        from web import init_jobs  # type: ignore

        cmd = _build_cos_init_cmd(
            info["name"],
            str(info["parent"]),
            all_stacks,
            resolved_agents,
            preset=preset,
            description=description or "",
            extra_skills=extra_skills or [],
            disabled_modules=info["disabled_modules"],
        )
        job = init_jobs.start_job(cmd, target, str(info["parent"]), _parse_init_payload)
        return {
            "data": {
                "job_id": job.job_id,
                "name": info["name"],
                "auto_named": info["auto_named"],
                "target": str(target),
            },
            "meta": {"layer": "hub", "source": "hub.registry_init_job"},
        }
    ok, payload, err = _run_cos_init(
        info["name"],
        str(info["parent"]),
        all_stacks,
        resolved_agents,
        preset=preset,
        description=description or "",
        extra_skills=extra_skills or [],
        disabled_modules=info["disabled_modules"],
    )
    if not ok:
        # A failed init must leave nothing — remove the partial scaffold.
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        return _err("internal", f"init failed: {err}", status=500)
    slug = (payload or {}).get("slug") or _resolve_slug_from_registry(target)
    return {
        "data": {
            "slug": slug,
            "path": str(target),
            "stack": (all_stacks[0] if all_stacks else None),
            "stacks": all_stacks,
            "agents": resolved_agents,
            "disabled_modules": info["disabled_modules"],
            "preset": preset or None,
            "auto_named": info["auto_named"],
        },
        "meta": {"layer": "hub", "source": "hub.registry_init"},
    }


@router.get("/init-jobs/{job_id}")
def hub_init_job_snapshot(job_id: str):
    """Current phase + status + log tail for a tracked init job (TASK-362)."""
    from web import init_jobs  # type: ignore

    job = init_jobs.get_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)
    return {"data": job.snapshot(), "meta": {"layer": "hub", "source": "hub.init_job"}}


@router.post("/init-jobs/{job_id}/cancel")
def hub_init_job_cancel(job_id: str):
    """Cancel a running init job; the partial scaffold is cleaned up (TASK-362)."""
    from web import init_jobs  # type: ignore

    job = init_jobs.cancel_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)
    return {
        "data": {"job_id": job.job_id, "status": job.snapshot()["status"]},
        "meta": {"layer": "hub", "source": "hub.init_job_cancel"},
    }


@router.get("/init-jobs/{job_id}/events")
async def hub_init_job_events(job_id: str):
    """SSE: buffered log replay then live phase/log events until terminal.

    Reconnect-safe — a browser refresh re-attaches with the same job_id and
    replays the buffered log before following (TASK-362)."""
    import asyncio

    from fastapi.responses import StreamingResponse

    from web import init_jobs  # type: ignore

    job = init_jobs.get_job(job_id)
    if job is None:
        return _err("not_found", f"no init job {job_id!r}", status=404)

    def _frame(event: str, payload: dict) -> bytes:
        return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()

    async def _gen():
        offset = 0
        last_phase = None
        while True:
            snap = job.snapshot(log_tail=0)
            lines, offset = await asyncio.to_thread(job.log_slice, offset)
            for line in lines:
                yield _frame("log", {"line": line})
            if snap["phase"] != last_phase:
                last_phase = snap["phase"]
                yield _frame("phase", {"phase": last_phase, "phases": snap["phases"]})
            if snap["status"] != "running":
                yield _frame(
                    snap["status"],
                    {
                        "status": snap["status"],
                        "error": snap["error"],
                        "result": snap["result"],
                        "cleanup": snap["cleanup"],
                    },
                )
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
