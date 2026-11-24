"""The panel's log of native review requests: planned, approved, claimed, reopened, done.

Append-only JSON lines in $COS_PANEL_DIR/.native-reviews.jsonl, folded on read and
pruned of finished requests when the next round is planned.
Contract: docs/engineering/agent-supervision.md § A review on the session's own
runtime runs as its native subagent.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REQUESTS_NAME = ".native-reviews.jsonl"


def _events(panel_dir: Path) -> list[dict[str, Any]]:
    try:
        raw = (panel_dir / REQUESTS_NAME).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in raw:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("id"):
            events.append(event)
    return events


def _requests(panel_dir: Path) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for order, event in enumerate(_events(panel_dir)):
        kind, request = event.get("event"), by_id.get(event["id"])
        if kind == "request":
            by_id[event["id"]] = {**event, "claim": "", "runs": 0, "done": False, "approved": -1}
        elif request is None:
            continue
        elif kind == "approve":
            request["approved"] = order
        elif kind == "claim":
            request["claim"] = str(event.get("agent_id") or "")
        elif kind == "reopen":
            request["claim"], request["runs"] = "", request["runs"] + 1
        elif kind == "done":
            request["done"] = True
    return list(by_id.values())


def prune(panel_dir: Path) -> list[dict[str, Any]]:
    # Finished requests go, and so do open ones a newer round of the same review replaced.
    requests = _requests(panel_dir)
    latest: dict[tuple[str, str], int] = {}
    for r in requests:
        key = (str(r.get("task_id")), str(r.get("role")))
        latest[key] = max(latest.get(key, 0), int(r.get("round") or 0))
    open_ids = {
        r["id"]
        for r in requests
        if not r["done"]
        and int(r.get("round") or 0) == latest[(str(r.get("task_id")), str(r.get("role")))]
    }
    kept = [json.dumps(e, ensure_ascii=False) for e in _events(panel_dir) if e["id"] in open_ids]
    path = panel_dir / REQUESTS_NAME
    if not path.exists():
        return []
    try:
        scratch = path.with_suffix(".tmp")
        scratch.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")
        scratch.replace(path)
    except OSError as exc:
        logger.debug("native review requests not pruned: %s", exc)
        return []
    return [r for r in requests if r["id"] not in open_ids]


def open_requests(panel_dir: Path, agent_type: str) -> list[dict[str, Any]]:
    return [r for r in _requests(panel_dir) if r["agent"] == agent_type and not r["done"]]


def to_start(panel_dir: Path, agent_type: str) -> dict[str, Any] | None:
    # The request the guard approved last is the one the starting subagent reviews.
    approved = [r for r in open_requests(panel_dir, agent_type) if r["approved"] >= 0]
    return max(approved, key=lambda r: r["approved"]) if approved else None


def claims(panel_dir: Path) -> set[str]:
    return {r["claim"] for r in _requests(panel_dir) if r["claim"] and not r["done"]}


def claimed_by(panel_dir: Path, agent_type: str, agent_id: str) -> dict[str, Any] | None:
    # Only the subagent whose start claimed the request may record it.
    if not agent_id:
        return None
    return next(
        (
            r
            for r in _requests(panel_dir)
            if r["agent"] == agent_type and not r["done"] and r["claim"] == agent_id
        ),
        None,
    )
