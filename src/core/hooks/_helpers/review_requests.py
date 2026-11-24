"""The panel's log of native review requests: planned, approved, claimed, reopened, done.

Append-only JSON lines in $COS_PANEL_DIR/.native-reviews.jsonl, folded on read and
pruned of finished requests when the next round is planned. The plan and the detached
run write it concurrently, so every write holds the panel's lock: a prune that read
the file before another process appended would otherwise drop that line.
Contract: docs/engineering/agent-supervision.md § A review on the session's own
runtime runs as its native subagent.
"""

from __future__ import annotations

import fcntl
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REQUESTS_NAME = ".native-reviews.jsonl"
LOCK_NAME = ".native-reviews.lock"


@contextmanager
def _locked(panel_dir: Path) -> Iterator[None]:
    panel_dir.mkdir(parents=True, exist_ok=True)
    with (panel_dir / LOCK_NAME).open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _write(panel_dir: Path, event: dict[str, Any]) -> None:
    with (panel_dir / REQUESTS_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def append(panel_dir: Path, event: dict[str, Any]) -> None:
    try:
        with _locked(panel_dir):
            _write(panel_dir, event)
    except OSError as exc:
        logger.debug("native review event not written: %s", exc)


def add_request(panel_dir: Path, request: dict[str, Any]) -> bool:
    # One request per review: the plan and the detached run may both get here.
    with _locked(panel_dir):
        if any(
            e.get("event") == "request" and e["id"] == request["id"] for e in _events(panel_dir)
        ):
            return False
        _write(panel_dir, {"event": "request", **request})
    return True


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
    # Approvals queue in order and each start consumes the oldest, so two reviews
    # approved before either subagent started go to one start each.
    queue: list[str] = []
    for event in _events(panel_dir):
        kind, request = event.get("event"), by_id.get(event["id"])
        if kind == "request" and request is None:
            by_id[event["id"]] = {**event, "claim": "", "runs": 0, "done": False}
        elif request is None:
            continue
        elif kind == "approve":
            queue.append(event["id"])
        elif kind == "claim":
            if event["id"] in queue:
                queue.remove(event["id"])
            request["claim"] = str(event.get("agent_id") or "")
        elif kind == "reopen":
            request["claim"], request["runs"] = "", request["runs"] + 1
        elif kind == "done":
            request["done"] = True
    for position, request_id in enumerate(queue):
        by_id[request_id].setdefault("queued", position)
    return list(by_id.values())


def prune(panel_dir: Path) -> list[dict[str, Any]]:
    # Finished requests go, and so do open ones a newer round of the same review replaced.
    with _locked(panel_dir):
        return _prune(panel_dir)


def _prune(panel_dir: Path) -> list[dict[str, Any]]:
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
    # The oldest approval no start has used yet is the one this subagent reviews.
    approved = [r for r in open_requests(panel_dir, agent_type) if "queued" in r]
    return min(approved, key=lambda r: r["queued"]) if approved else None


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
