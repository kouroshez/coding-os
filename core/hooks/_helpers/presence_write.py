"""
Presence file merge + atomic write.

Called from agent-presence.sh on every tool call. Was inline as
`python3 - <<'PY'` but bash 5.3.9 sporadically deadlocks that pattern;
zombie bash children pile up and starve the agent runtime's auxiliary
subprocess spawns. Separate .py file = zero heredoc surface = immune.

USAGE
    python3 presence_write.py <path> <agent> <sid> <pid> <event> <now>

EVENT ∈ {start, prompt, tool, stop, end}. Other values fall through silently.
"""
from __future__ import annotations

import json
import os
import sys


def main(argv: list[str]) -> int:
    if len(argv) != 7:
        return 0  # fail-open: presence is UX, not correctness
    path, agent, sid, pid_s, event, now_s = argv[1:]
    try:
        pid = int(pid_s); now = int(now_s)
    except ValueError:
        return 0

    prev: dict = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                prev = json.load(f)
        except (OSError, json.JSONDecodeError):
            prev = {}

    new = {
        "agent": agent,
        "session_id": sid,
        "pid": pid,
        "started_at": prev.get("started_at"),
        "last_prompt_at": prev.get("last_prompt_at"),
        "last_tool_at": prev.get("last_tool_at"),
        "last_stop_at": prev.get("last_stop_at"),
        "ended_at": prev.get("ended_at"),
    }
    if event == "start":
        new["started_at"] = now
        new["ended_at"] = None
        new["last_stop_at"] = None
    elif event == "prompt":
        new["last_prompt_at"] = now
        new["last_stop_at"] = None
        new["started_at"] = new["started_at"] or now
    elif event == "tool":
        new["last_tool_at"] = now
        new["started_at"] = new["started_at"] or now
    elif event == "stop":
        new["last_stop_at"] = now
    elif event == "end":
        new["ended_at"] = now

    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new, f, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
