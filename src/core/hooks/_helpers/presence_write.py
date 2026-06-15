"""
Presence file merge + atomic write.

Called from agent-presence.sh on every tool call. Was inline as
`python3 - <<'PY'` but bash 5.3.9 sporadically deadlocks that pattern;
zombie bash children pile up and starve the agent runtime's auxiliary
subprocess spawns. Separate .py file = zero heredoc surface = immune.

USAGE
    python3 presence_write.py <path> <agent> <sid> <pid> <event> <now> [model] [sdk_uuid] [transcript]

EVENT ∈ {start, prompt, tool, stop, end}. Other values fall through silently.
MODEL (optional 7th arg) — Claude Code / Codex runtime model id
(e.g. "claude-opus-4-7"). When provided, stored as sessions/<sid>.json::model so
the Hub UI can attribute live agents to the actual runtime model rather
than the stale shared $COS_AGENT_DIR/.model file.
SDK_UUID (optional 8th arg) — the host runtime's own session id (the SDK
transcript uuid, from the hook payload's `.session_id`). Stored as
sessions/<sid>.json::sdk_uuid so a task's coding-os agent_session can resolve
to its chat transcript (the id bridge — TASK-184).
TRANSCRIPT (optional 9th arg) — the runtime's live transcript path (Claude Stop
payload `.transcript_path`). On the `stop` event the last assistant `usage`
block is tailed and summed into sessions/<sid>.json::used_tokens so the Hub's
live-agent context-window percent is real, not N/A (TASK-255). Privacy-safe:
only the aggregate token count is stored, never transcript content. Window math
lives in web/routes/presence.py (the reader); keep the summed-key list in sync.
"""

from __future__ import annotations

import json
import os
import sys


def _used_tokens_from_transcript(transcript_path: str) -> int | None:
    """Tail the live transcript for the latest assistant usage, sum input
    tokens. Cheap (last 256 KB only), fail-open. Sibling of
    web/routes/presence.py::_latest_transcript_usage — keep the key list aligned.
    """
    if not transcript_path or not os.path.exists(transcript_path):
        return None
    try:
        with open(transcript_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            window = min(fh.tell(), 256 * 1024)
            fh.seek(-window, os.SEEK_END)
            tail = fh.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        if '"usage"' not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = obj.get("message") if isinstance(obj, dict) else None
        usage = msg.get("usage") if isinstance(msg, dict) else None
        if not isinstance(usage, dict):
            usage = obj.get("usage") if isinstance(obj, dict) else None
        if isinstance(usage, dict):
            used = sum(
                int(usage.get(k) or 0)
                for k in (
                    "input_tokens",
                    "cache_read_input_tokens",
                    "cache_creation_input_tokens",
                )
            )
            return used if used > 0 else None
    return None


def main(argv: list[str]) -> int:
    if len(argv) not in (7, 8, 9, 10):
        return 0  # fail-open: presence is UX, not correctness
    path, agent, sid, pid_s, event, now_s = argv[1:7]
    model = argv[7].strip() if len(argv) >= 8 else ""
    sdk_uuid = argv[8].strip() if len(argv) >= 9 else ""
    transcript = argv[9].strip() if len(argv) == 10 else ""
    try:
        pid = int(pid_s)
        now = int(now_s)
    except ValueError:
        return 0

    prev: dict = {}
    parse_failed = False
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, json.JSONDecodeError):
            # File exists but is corrupt — keep going with empty `prev`,
            # but emit one breadcrumb to cos hooks-log so ops can spot a
            # disk that's silently shredding presence files.
            prev = {}
            parse_failed = True

    new = {
        "agent": agent,
        "session_id": sid,
        "pid": pid,
        "started_at": prev.get("started_at"),
        "last_prompt_at": prev.get("last_prompt_at"),
        "last_tool_at": prev.get("last_tool_at"),
        "last_stop_at": prev.get("last_stop_at"),
        "ended_at": prev.get("ended_at"),
        "model": (model or prev.get("model") or None),
        # Bridges the coding-os session id (this file's name) to the host SDK
        # transcript uuid so a task can link to the chat that made it.
        "sdk_uuid": (sdk_uuid or prev.get("sdk_uuid") or None),
        # Aggregate context-window tokens stamped on stop (TASK-255).
        "used_tokens": prev.get("used_tokens"),
        "context_updated_at": prev.get("context_updated_at"),
    }
    if event == "start":
        # Authoritative session boundary — overwrite even if a prompt
        # event raced ahead and stamped started_at first (observed when
        # UserPromptSubmit fires before SessionStart on Claude Code 2.x
        # cold boot).  Without the overwrite, started_at can land AFTER
        # last_prompt_at and the board's "alive >5min" check trips on a
        # fresh session.
        new["started_at"] = now
        new["ended_at"] = None
        new["last_stop_at"] = None
    elif event == "prompt":
        new["last_prompt_at"] = now
        new["last_stop_at"] = None
        # Only seed started_at when we genuinely don't have one yet.
        if not isinstance(new["started_at"], int):
            new["started_at"] = now
    elif event == "tool":
        new["last_tool_at"] = now
        if not isinstance(new["started_at"], int):
            new["started_at"] = now
    elif event == "stop":
        new["last_stop_at"] = now
        used = _used_tokens_from_transcript(transcript)
        if used is not None:
            new["used_tokens"] = used
            new["context_updated_at"] = now
    elif event == "end":
        new["ended_at"] = now

    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new, f, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        return 0
    if parse_failed:
        # One-line breadcrumb so `cos hooks-log` surfaces silent corruption.
        # stderr only — agent-presence.sh discards stderr in the happy
        # path, so this never reaches the user, only the ops log.
        sys.stderr.write(f"presence_write: replaced corrupt {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
