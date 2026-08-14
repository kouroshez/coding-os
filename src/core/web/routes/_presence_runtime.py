"""Read one agent's live runtime state off disk.

Where the markers live and how their session prefixes are stripped is a
filesystem contract with write-state.sh, and it moves whenever the hook layer
does — a different clock from the routes that shape the HUD payload. A leaf: the
sibling route modules it needs are imported inside the functions that use them.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("coding_os.web.presence")

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _state_dir() -> Path:
    from web._project_context import current_project_root, is_explicit_project_scope  # type: ignore

    if is_explicit_project_scope():
        return current_project_root() / ".coding-os"
    env = os.environ.get("COS_STATE_DIR") or os.environ.get("COS_AGENT_DIR")
    if env:
        return Path(env).resolve()
    return current_project_root() / ".coding-os"


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def _strip_session_prefix(value: str | None, session_id: str | None) -> str | None:
    """write-state.sh prefixes each value with the writer's session/panel id — strip it."""
    if not value:
        return value
    if session_id and value.startswith(session_id):
        return value[len(session_id) :].strip() or None
    # The prefix token is whatever write-state.sh had: a ses-… session id, a
    # ppid-… panel id, or a raw UUID panel id (the fallback when the panel
    # session-id file is unseeded — common on Claude, whose per-tool-call hook
    # subprocesses each resolve a fresh ppid panel). Strip whichever leads.
    import re as _re

    m = _re.match(
        r"^(?:ses-\S+|ppid-\S+|[0-9a-fA-F]{8}-[0-9a-fA-F-]{27})\s+(.*)$",
        value,
    )
    if m:
        return m.group(1).strip() or None
    return value


def _read_json(p: Path) -> dict[str, Any] | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _transcript_dir(project_root: Path) -> Path | None:
    """Ask the adapter where its transcripts live — never import its SDK here.

    This read `from claude_agent_sdk import project_key_for_directory`, an
    adapter SDK import inside the kernel (P8) that also hardcoded one runtime's
    on-disk layout. The `presence` entrypoint owns both facts now.
    """
    from thinking_os.adapter_registry import (
        load_adapter_records,
        load_entrypoint_module,
    )

    for record in load_adapter_records().values():
        if "presence" not in record.capabilities:
            continue
        module = load_entrypoint_module(record, "presence")
        resolver = getattr(module, "transcript_dir", None)
        if not callable(resolver):
            continue
        try:
            return Path(resolver(project_root))
        except Exception as exc:
            logger.debug("%s presence provider failed: %s", record.id, exc)
    return None


def _latest_claude_chat_uuid(project_root: Path) -> str | None:
    """Newest transcript file for this project (proxy for an active chat)."""
    base = _transcript_dir(project_root)
    if base is None:
        return None
    if not base.is_dir():
        return None
    newest: Path | None = None
    newest_mtime = 0.0
    for jsonl in base.glob("*.jsonl"):
        try:
            mt = jsonl.stat().st_mtime
        except OSError:
            continue
        if mt > newest_mtime:
            newest = jsonl
            newest_mtime = mt
    if newest is None:
        return None
    return newest.stem


def _newest_marker(agent_dir: Path, basename: str) -> str | None:
    """Newest copy of a per-panel marker across agent_dir + every panels/*/.

    Post-TASK-035 the cognitive-state markers (.task-current,
    .thinking_os-gate, .active-skill) live under panels/<id>/. The panel id is
    NOT stable across Claude's per-tool-call hook subprocesses, so one
    session's markers scatter across many ppid-* panels and the agent-level
    copy is a stale fossil. The HUD wants the live value, so the newest mtime
    wins (empty newest → None, i.e. "no current value").
    """
    candidates = [agent_dir / basename]
    panels = agent_dir / "panels"
    if panels.is_dir():
        try:
            candidates.extend(p / basename for p in panels.iterdir() if p.is_dir())
        except OSError as exc:
            logger.debug("panel scan failed for %s: %s", agent_dir, exc)
    best_text: str | None = None
    best_mtime = -1.0
    for path in candidates:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > best_mtime:
            best_mtime = mtime
            best_text = _read_text(path)
    return best_text


def _agent_runtime(agent_dir: Path, agent: str) -> dict[str, Any] | None:
    """Best-effort runtime snapshot for one agent."""
    if not agent_dir.is_dir():
        return None
    # Prefer the live panel-scoped session-id marker; the flat agent-level
    # session-id is a startup fossil nothing writes anymore (P7).
    sid = _newest_marker(agent_dir, "session-id") or _read_text(agent_dir / "session-id")
    task = _strip_session_prefix(_newest_marker(agent_dir, ".task-current"), sid)
    skill_active = _strip_session_prefix(_newest_marker(agent_dir, ".active-skill"), sid)
    gate = _strip_session_prefix(_newest_marker(agent_dir, ".thinking_os-gate"), sid)
    session_payload = None
    if sid:
        session_payload = _read_json(agent_dir / "sessions" / f"{sid}.json")
    # Model is per-session — the shared $COS_AGENT_DIR/.model file is a
    # stale fallback (gets overwritten by whichever runtime started last
    # and never cleaned up).  Prefer sessions/<sid>.json::model so two
    # concurrent agents on the same project can disagree on model without
    # one trampling the other's display.
    model: str | None = None
    if isinstance(session_payload, dict):
        candidate = session_payload.get("model")
        if isinstance(candidate, str) and candidate.strip():
            model = candidate.strip()
    if not model:
        model = _strip_session_prefix(_read_text(agent_dir / ".model"), sid)
    return {
        "agent": agent,
        "session_id": sid,
        "task": task,
        "skill_active": skill_active,
        "model": model,
        "gate": gate,
        "session": session_payload,
    }


def _last_hook_event(state: Path) -> dict[str, Any] | None:
    log = state / ".hooks.log"
    if not log.exists():
        return None
    try:
        with log.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            window = min(size, 8192)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    from .hooks import _parse_hook_line  # type: ignore

    for line in reversed(tail.splitlines()):
        evt = _parse_hook_line(line)
        if evt is not None:
            return evt
    return None


def _canonical_agents() -> list[str]:
    """Return the canonical adapter ids (scanned from src/adapters, fails soft)."""
    from board_os.hub_adapter_manifest import list_agent_ids  # type: ignore

    return list_agent_ids()


def _project_slug(project_root: Path) -> str | None:
    """Owning-project registry slug for a resolved root (fail-soft, TASK-435).

    Home-level presence surfaces render at the unscoped '/' route and cannot
    read a slug from the URL, so each agent carries its project's slug to build
    an explicit /p/<slug>/cognition/... link instead of an unscoped one."""
    try:
        from cli.registry import load_registry  # type: ignore

        reg = load_registry()
    except Exception as exc:
        logger.debug("load_registry unavailable for slug stamp: %s", exc)
        reg = None
    if reg is not None:
        for entry in reg.projects:
            try:
                if Path(entry.path).resolve() == project_root:
                    return entry.slug
            except OSError:
                continue
    try:
        from cli.registry import _derive_slug  # type: ignore

        return _derive_slug(project_root)
    except Exception as exc:
        logger.debug("_derive_slug unavailable: %s", exc)
        return None
