"""cos tail — unified live view of every log/trace/jsonl under .coding-os/.

Reads existing sinks (hooks, traces, telemetry, errors, MCP stderr). Adds no
writers — pure consumer. Snapshot mode for audit; follow mode for live.
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import click

_GLOBAL_SOURCES: list[tuple[str, str]] = [
    ("hooks", ".hooks.log"),
    ("mcp", ".mcp.log"),
    ("graph", ".graph-telemetry.jsonl"),
    ("graph", ".warn-graph-empty.log"),
    ("reindex", ".reindex-errors.log"),
    ("reindex", ".reindex-shell-ops.log"),
    ("regen", ".regen-doc-index-errors.log"),
    ("regen", ".section-index-errors.log"),
    ("prune", ".prune-errors.log"),
    ("overrides", ".overrides.audit.log"),
    ("scheduled", "scheduled/*.json"),
]

# HOME-scoped sources — hub server log lives outside the project state dir
# because one hub serves every project. Path is absolute, computed at discovery.
_HOME_SOURCES: list[tuple[str, str]] = [
    ("hub", ".coding-os/hub.log"),
]

_AGENT_GLOBS: list[tuple[str, str]] = [
    ("turn", ".turn-activity.log"),
    ("trace", "traces/*.jsonl"),
]

_LEVEL_RE = re.compile(r"\b(ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\b", re.I)
_TS_JSON_RE = re.compile(r'"ts"\s*:\s*"?([^",}]+)"?')
# Capture optional Z / ±HH:MM tz suffix so UTC stamps can normalise to
# the operator's local zone — hook logs use ISO-Z (UTC) while MCP /
# Python ``logging`` writes bare local time. Without this, the same
# wall-clock event shows two different times in the unified tail and
# the cross-source sort order breaks.
_TS_BRACKET_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:?\d{2})?")

_COLORS = {
    "hooks": "\033[36m",
    "mcp": "\033[35m",
    "graph": "\033[33m",
    "reindex": "\033[34m",
    "regen": "\033[34m",
    "prune": "\033[90m",
    "overrides": "\033[91m",
    "turn": "\033[32m",
    "trace": "\033[95m",
}
_RESET = "\033[0m"
_DIM = "\033[2m"
_RED = "\033[31m"
_YELLOW = "\033[33m"


@dataclass
class Line:
    ts: str
    source: str
    agent: str
    file: str
    text: str
    level: str = ""


def _discover(state_dir: Path) -> list[tuple[str, str, Path]]:
    found: list[tuple[str, str, Path]] = []
    for source, name in _GLOBAL_SOURCES:
        if any(ch in name for ch in "*?["):
            for p in state_dir.glob(name):
                if p.is_file():
                    found.append((source, "", p))
        else:
            p = state_dir / name
            if p.exists():
                found.append((source, "", p))
    home = Path.home()
    for source, rel in _HOME_SOURCES:
        p = home / rel
        if p.exists() and p.is_file():
            found.append((source, "", p))
    if not state_dir.exists():
        return found
    for child in state_dir.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        agent = child.name
        for source, pattern in _AGENT_GLOBS:
            for p in child.glob(pattern):
                if p.is_file():
                    found.append((source, agent, p))
    return found


def _utc_to_local_str(stamp: str) -> str:
    """Treat ``stamp`` (YYYY-MM-DD HH:MM:SS) as UTC, render in local zone."""
    import datetime as _dt

    parsed = _dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    aware_utc = parsed.replace(tzinfo=_dt.timezone.utc)
    return aware_utc.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _try_parse_iso(iso: str) -> str:
    """Try every supported ISO shape; return raw 19-char prefix on failure."""
    import datetime as _dt

    try:
        if iso.endswith("Z"):
            return _utc_to_local_str(iso[:-1].replace("T", " "))
        if len(iso) >= 25 and iso[19] in ("+", "-"):
            parsed = _dt.datetime.fromisoformat(iso)
            return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso[:19].replace("T", " ")
    return iso[:19].replace("T", " ")


def _extract_ts(text: str) -> str:
    """Return local-zone ISO ts (YYYY-MM-DD HH:MM:SS) for sorting + display.

    Sources unified to the operator's local zone:
      - JSON ``"ts"`` epoch — already UTC; convert via ``fromtimestamp``.
      - JSON ``"ts"`` ISO with ``Z`` / ±HH:MM suffix — parse + convert.
      - Bracket-prefixed log line — hook emitter writes UTC with explicit
        ``Z``; MCP / Python ``logging`` writes bare local time. Detect
        the suffix and convert UTC → local so the same wall-clock event
        appears at the same time across both sources.
      - Bare ISO-prefixed text without tz — assumed already in local time.
    Empty string when no ts found.
    """
    import datetime as _dt

    raw = ""
    if text.startswith("{"):
        m = _TS_JSON_RE.search(text)
        if m:
            raw = m.group(1)
    elif text.startswith("["):
        m = _TS_BRACKET_RE.match(text)
        if m:
            stamp = m.group(1).replace("T", " ")
            tz = m.group(2) or ""
            if tz == "Z":
                try:
                    return _utc_to_local_str(stamp)
                except ValueError:
                    return stamp
            if tz.startswith(("+", "-")):
                try:
                    parsed = _dt.datetime.fromisoformat(m.group(1) + tz)
                    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return stamp
            return stamp
    elif len(text) >= 19 and text[4:5] == "-" and text[10:11] in (" ", "T"):
        return text[:19].replace("T", " ")

    if not raw:
        return ""
    if raw.replace(".", "", 1).isdigit():
        try:
            return _dt.datetime.fromtimestamp(float(raw)).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError):
            return ""
    return _try_parse_iso(raw[:25])


def _extract_level(text: str) -> str:
    m = _LEVEL_RE.search(text)
    return m.group(1).upper() if m else ""


def _format(line: Line, no_color: bool = False) -> str:
    color = "" if no_color else _COLORS.get(line.source, "")
    reset = "" if no_color else _RESET
    dim = "" if no_color else _DIM
    ts = line.ts[-8:] if line.ts else "--------"
    agent = f"[{line.agent}]" if line.agent else ""
    src = f"[{line.source}]"
    lvl_color = ""
    if not no_color:
        if line.level in ("ERROR", "FATAL", "CRITICAL"):
            lvl_color = _RED
        elif line.level in ("WARN", "WARNING"):
            lvl_color = _YELLOW
    return f"{dim}{ts}{reset} {color}{src}{reset}{agent} {lvl_color}{line.text}{reset}"


def _read_last_n(path: Path, n: int) -> list[str]:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 8192
            data = b""
            while size > 0 and data.count(b"\n") <= n:
                read = min(block, size)
                size -= read
                f.seek(size)
                data = f.read(read) + data
            lines = data.splitlines()[-n:]
            return [ln.decode("utf-8", errors="replace") for ln in lines]
    except OSError:
        return []


def _matches(line: Line, sources: set[str], agents: set[str], level: str, grep: str) -> bool:
    if sources and line.source not in sources:
        return False
    if agents:
        if line.agent and line.agent not in agents:
            return False
        if not line.agent and "global" not in agents:
            return False
    if level:
        order = ["DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL"]
        try:
            min_idx = order.index(level.upper())
        except ValueError:
            min_idx = 0
        cur = line.level.upper() or "INFO"
        try:
            cur_idx = order.index(cur)
        except ValueError:
            cur_idx = 1
        if cur_idx < min_idx:
            return False
    return not (grep and grep not in line.text)


def _spawn_tail(
    path: Path,
    source: str,
    agent: str,
    q: queue.Queue[Line],
    stop: threading.Event,
    procs: list[subprocess.Popen],
) -> None:
    proc = subprocess.Popen(
        ["tail", "-F", "-n", "0", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    procs.append(proc)

    def reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            if stop.is_set():
                break
            text = raw.rstrip("\n")
            q.put(
                Line(
                    ts=_extract_ts(text),
                    source=source,
                    agent=agent,
                    file=str(path),
                    text=text,
                    level=_extract_level(text),
                )
            )

    threading.Thread(target=reader, daemon=True).start()


def run_tail(
    state_dir: Path,
    follow: bool,
    tail_count: int,
    sources: set[str],
    agents: set[str],
    level: str,
    grep: str,
    no_color: bool,
) -> int:
    targets = _discover(state_dir)
    if not targets:
        click.echo(f"No log files found under {state_dir}", err=True)
        return 1

    if not follow:
        all_lines: list[Line] = []
        for source, agent, path in targets:
            for raw in _read_last_n(path, tail_count):
                ln = Line(
                    ts=_extract_ts(raw),
                    source=source,
                    agent=agent,
                    file=str(path),
                    text=raw,
                    level=_extract_level(raw),
                )
                if _matches(ln, sources, agents, level, grep):
                    all_lines.append(ln)
        all_lines.sort(key=lambda ln: ln.ts)
        for ln in all_lines[-tail_count:]:
            click.echo(_format(ln, no_color))
        return 0

    q: queue.Queue[Line] = queue.Queue()
    stop = threading.Event()
    procs: list[subprocess.Popen] = []
    click.echo(
        f"{_DIM}cos tail — {len(targets)} sources, Ctrl-C to stop{_RESET}",
        err=True,
    )
    for source, agent, path in targets:
        _spawn_tail(path, source, agent, q, stop, procs)
    try:
        while True:
            try:
                ln = q.get(timeout=0.5)
            except queue.Empty:
                continue
            if _matches(ln, sources, agents, level, grep):
                click.echo(_format(ln, no_color))
    except KeyboardInterrupt:
        stop.set()
        for p in procs:
            try:
                p.terminate()
            except OSError as exc:
                click.echo(f"warn: could not terminate tail PID {p.pid}: {exc}", err=True)
        click.echo(f"\n{_DIM}stopped{_RESET}", err=True)
    return 0


@click.command("tail")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option("-f", "--follow", is_flag=True, default=False, help="Follow live (tail -F)")
@click.option("-n", "tail_count", default=50, help="Last N lines per source (snapshot mode)")
@click.option(
    "--source", "sources_csv", default="", help="Filter sources (csv): hooks,mcp,graph,trace,..."
)
@click.option("--agent", "agents_csv", default="", help="Filter agents (csv): claude,codex,global")
@click.option("--level", default="", help="Min level: DEBUG|INFO|WARN|ERROR")
@click.option("--grep", default="", help="Substring filter")
@click.option("--no-color", is_flag=True, default=False, help="Disable ANSI color")
@click.option(
    "--list-sources", is_flag=True, default=False, help="List discovered sources and exit"
)
def tail_cmd(
    project_dir: str,
    follow: bool,
    tail_count: int,
    sources_csv: str,
    agents_csv: str,
    level: str,
    grep: str,
    no_color: bool,
    list_sources: bool,
) -> None:
    """Unified live view of all logs/traces/telemetry under .coding-os/.

    Examples:

        cos tail                        # snapshot, last 50 lines, all sources
        cos tail -f                     # live follow
        cos tail -f --agent claude      # only claude per-agent files
        cos tail --source hooks,mcp     # only those sources
        cos tail --level ERROR -n 200   # errors only, more history
        cos tail --grep "TASK-002"      # substring filter
        cos tail --list-sources         # which files would I read?
    """
    project = Path(project_dir).resolve()
    state = project / os.environ.get("COS_STATE_DIR_NAME", ".coding-os")

    if list_sources:
        targets = _discover(state)
        for source, agent, path in targets:
            agent_label = agent or "(global)"
            click.echo(f"  [{source:9}] {agent_label:8} {path}")
        click.echo(f"\n{len(targets)} sources discovered")
        return

    sources = {s.strip() for s in sources_csv.split(",") if s.strip()}
    agents = {a.strip() for a in agents_csv.split(",") if a.strip()}

    sys.exit(
        run_tail(
            state_dir=state,
            follow=follow,
            tail_count=tail_count,
            sources=sources,
            agents=agents,
            level=level,
            grep=grep,
            no_color=no_color,
        )
    )
