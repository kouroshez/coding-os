"""cli.hub_commands — `cos hub` + `cos service` CLI.

PURPOSE:      Start/stop/status the singleton FastAPI hub (127.0.0.1:9188) that
              serves every registered project, and manage it as an OS service.
INPUT:        `cos hub {start,stop,status,restart}` / `cos service ...`.
OUTPUT:       lifecycle actions + status on stdout; errors to stderr; precise exit.
DEPENDENCIES: ~/.coding-os/{hub.pid,hub.log}; uvicorn; the web app factory.
NOTES:        Stale-pid detection via os.kill(pid, 0); SIGTERM→SIGKILL escalation.
              The file locations live in `_hub_paths` and the `service` group in
              `_hub_service`; both are re-exported here.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

from cli._hub_paths import (
    DEFAULT_HUB_PORT as DEFAULT_HUB_PORT,
    HUB_HOST as HUB_HOST,
    SERVICE_NAME as SERVICE_NAME,
    _hub_dir as _hub_dir,
    _log_file as _log_file,
    _resolve_cos_bin as _resolve_cos_bin,
)
from cli._hub_service import (
    _launchd_plist_path as _launchd_plist_path,
    _render_launchd_plist as _render_launchd_plist,
    _render_systemd_unit as _render_systemd_unit,
    _systemd_unit_path as _systemd_unit_path,
    service_cli as service_cli,
    service_install as service_install,
    service_uninstall as service_uninstall,
)


def _pid_file() -> Path:
    return _hub_dir() / "hub.pid"


def _reload_flag_file() -> Path:
    return _hub_dir() / "hub.reload"


def _read_pid() -> int | None:
    """Read the hub pid file and validate the process is alive."""
    path = _pid_file()
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)  # signal 0 = probe only
    except ProcessLookupError:
        path.unlink(missing_ok=True)
        return None
    except PermissionError:
        # Process exists but we lack permission — still counts as running.
        return pid
    return pid


def _write_pid(pid: int) -> None:
    _pid_file().write_text(f"{pid}\n", encoding="utf-8")


def _hub_health_ok(port: int) -> bool:
    """Return True if something answers HTTP GET /health on the hub port."""
    import urllib.error
    import urllib.request

    url = f"http://{HUB_HOST}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=0.8) as resp:
            return 200 <= int(resp.status) < 300
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 300
    except Exception:
        return False


def _port_accepts_connections(port: int) -> bool:
    import socket

    try:
        with socket.create_connection((HUB_HOST, port), timeout=0.3):
            return True
    except OSError:
        return False


def _hub_listener_state(port: int) -> str:
    if _hub_health_ok(port):
        return "healthy"
    if _port_accepts_connections(port):
        return "occupied"
    return "down"


def _listener_label(state: str) -> str:
    if state == "healthy":
        return "responds to /health"
    if state == "occupied":
        return "accepts TCP connections but does not answer /health"
    return "not listening"


def _core_newest_mtime() -> tuple[float, Path | None]:
    """Newest mtime among the in-process core *.py the hub loads (skips tests/caches)."""
    from cli._resources import core_dir

    newest = 0.0
    newest_path: Path | None = None
    for dirpath, dirnames, filenames in os.walk(core_dir()):
        dirnames[:] = [
            d for d in dirnames if d not in {"tests", "__pycache__"} and not d.startswith(".")
        ]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            candidate = Path(dirpath) / name
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime > newest:
                newest, newest_path = mtime, candidate
    return newest, newest_path


def _hub_code_is_stale() -> tuple[bool, Path | None]:
    """True when a running hub loaded core *.py older than the newest on disk (SSOT: status/doctor/update)."""
    if _read_pid() is None:
        return False, None
    # A --reload hub auto-restarts its worker on source change, so it is never
    # stale even though hub.pid mtime stays at the original start.
    if _reload_flag_file().exists():
        return False, None
    # hub.pid is rewritten on every start/restart, so its mtime ≈ hub start time.
    try:
        started = _pid_file().stat().st_mtime
    except OSError:
        return False, None
    newest, newest_path = _core_newest_mtime()
    return newest > started, newest_path


@click.group(name="hub", help="Manage the global coding-os Hub daemon.")
def hub_cli() -> None:
    """Parent group."""


@hub_cli.command("start")
@click.option("--port", type=int, default=DEFAULT_HUB_PORT, show_default=True)
@click.option(
    "--foreground",
    is_flag=True,
    default=False,
    help="Block in the current terminal instead of daemonising.",
)
@click.option(
    "--reload",
    "reload_",
    is_flag=True,
    default=False,
    help="Dev only: uvicorn auto-reloads the worker on core_dir() source edits.",
)
def hub_start(port: int, foreground: bool, reload_: bool) -> None:
    """Start the Hub uvicorn process (detached by default).

    NOTES: The pid-file collision check ONLY runs in detached mode.  In
           foreground mode we always attempt to bind — both because the
           parent caller has explicitly asked to block here, and because
           the detached flow re-invokes this command with --foreground
           after it has already written its own pid to hub.pid (a naive
           collision check would then see the fresh pid as "already
           running" and immediately exit).
    """
    if foreground:
        from web.server import run_server  # type: ignore

        click.echo(f"Starting Hub on http://{HUB_HOST}:{port} (foreground)")
        run_server(host=HUB_HOST, port=port, reload=reload_)
        return

    existing = _read_pid()
    if existing is not None:
        if _hub_health_ok(port):
            click.echo(f"Hub already running (pid {existing}). Use `cos hub status`.")
            return
        click.echo(
            f"Stale hub.pid (pid {existing}) — nothing responds on "
            f"http://{HUB_HOST}:{port}/health; stopping and starting fresh.",
            err=True,
        )
        with contextlib.suppress(ProcessLookupError):
            os.kill(existing, signal.SIGTERM)
        for _ in range(30):
            time.sleep(0.1)
            if _read_pid() is None:
                break
        if _read_pid() is not None:
            with contextlib.suppress(ProcessLookupError):
                os.kill(existing, signal.SIGKILL)
            for _ in range(20):
                time.sleep(0.1)
                if _read_pid() is None:
                    break
        _pid_file().unlink(missing_ok=True)

    listener_state = _hub_listener_state(port)
    if listener_state != "down":
        raise click.ClickException(
            f"Hub port {HUB_HOST}:{port} has an unmanaged listener "
            f"({_listener_label(listener_state)}) but no live hub.pid at {_pid_file()}. "
            f"Stop that process or restore the pid file before running `cos hub start`. "
            f"Inspect with `lsof -nP -iTCP:{port} -sTCP:LISTEN`."
        )

    log = _log_file()
    log.touch(exist_ok=True)
    cmd = [_resolve_cos_bin(), "hub", "start", "--foreground", "--port", str(port)]
    if reload_:
        cmd.append("--reload")

    # Graph backend default: SQLite (in-process reindex)
    # lands.  Rationale — Kùzu enforces a single-writer lock on its DB
    # directory: when the hub owns the lock, `cos graph-reindex` running
    # from a separate terminal falls back to SQLite and populates *that*
    # store, leaving Kùzu empty.  Forcing SQLite for the hub keeps both
    # surfaces reading the same data until the reindex endpoint arrives.
    # Users can override by exporting COS_GRAPH_BACKEND=kuzu explicitly.
    env = os.environ.copy()
    env.setdefault("COS_GRAPH_BACKEND", "sqlite")

    # Detach: start_new_session so SIGHUP on terminal close doesn't kill us.
    with open(log, "ab") as logfh:
        proc = subprocess.Popen(
            cmd,
            stdout=logfh,
            stderr=logfh,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )

    # Wait up to ~2s for the child to still be alive before treating the
    # start as successful.  Without this, a child that dies immediately
    # (port in use, import error, etc.) leaves a stale pid file and the
    # caller thinks the hub is up.
    for _ in range(20):
        rc = proc.poll()
        if rc is not None:
            tail = ""
            try:
                tail = log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
            except OSError:
                tail = []
            raise click.ClickException(
                f"Hub child exited with rc={rc} before it could bind.\n"
                f"  Logs: {log}\n  Last lines:\n    " + "\n    ".join(tail)
                if tail
                else f"  Logs: {log}"
            )
        time.sleep(0.1)

    _write_pid(proc.pid)
    # Mark reload mode so the staleness signal stays "fresh" (the worker
    # auto-reloads); a normal start/restart clears it.
    if reload_:
        _reload_flag_file().write_text("1\n", encoding="utf-8")
    else:
        _reload_flag_file().unlink(missing_ok=True)
    click.echo(f"Hub started (pid {proc.pid}) at http://{HUB_HOST}:{port}")
    click.echo(f"  Logs: {log}" + (" (--reload: dev auto-reload on)" if reload_ else ""))


@hub_cli.command("stop")
def hub_stop() -> None:
    """Stop the running Hub daemon."""
    _reload_flag_file().unlink(missing_ok=True)  # reload mode ends with the process
    pid = _read_pid()
    if pid is None:
        click.echo("Hub is not running.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        _pid_file().unlink(missing_ok=True)
        click.echo("Hub process already gone; cleared pid file.")
        return
    # Wait up to 3s for graceful stop.
    for _ in range(30):
        time.sleep(0.1)
        if _read_pid() is None:
            click.echo(f"Hub stopped (pid {pid}).")
            return
    click.echo(
        f"Hub pid {pid} did not exit after SIGTERM; sending SIGKILL.",
        err=True,
    )
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGKILL)
    for _ in range(30):
        time.sleep(0.1)
        if _read_pid() is None:
            click.echo(f"Hub stopped (pid {pid}).")
            return
    _pid_file().unlink(missing_ok=True)
    click.echo(
        f"Hub pid {pid} could not be reaped; cleared {_pid_file()}. "
        f"If a stray listener remains on port 9188, stop it manually.",
        err=True,
    )


@hub_cli.command("restart")
@click.option("--port", type=int, default=DEFAULT_HUB_PORT, show_default=True)
def hub_restart(port: int) -> None:
    """Stop the running Hub (if any) and start it again on the same port.

    Convenience wrapper around `hub stop` + `hub start` — used after
    UI rebuilds or core/ edits that need a process refresh.  Always
    re-detaches; pass `cos hub start --foreground` directly if you
    need a foreground process.
    """
    ctx = click.get_current_context()
    pid = _read_pid()
    if pid is not None:
        ctx.invoke(hub_stop)
    else:
        click.echo("Hub: not running, starting fresh.")
    ctx.invoke(hub_start, port=port, foreground=False)


@hub_cli.command("status")
def hub_status() -> None:
    """Report the Hub's PID, port, meta-repo path, and symlink health.

    Shows the *three* locations a user frequently confuses:
      - Meta repo  (where core/ + adapters/ + templates/ live)
      - Hub state  (~/.coding-os/ — registry.json + hub.pid)
      - Project count + symlink health (broken = meta repo moved)
    """
    pid = _read_pid()
    if pid is None:
        listener_state = _hub_listener_state(DEFAULT_HUB_PORT)
        if listener_state == "down":
            click.echo("Hub: not running")
        else:
            click.echo(
                f"Hub: unmanaged listener on http://{HUB_HOST}:{DEFAULT_HUB_PORT} "
                f"({_listener_label(listener_state)}; no hub.pid)"
            )
            click.echo(f"  Logs: {_log_file()}")
            click.echo("  Start guard: stop the listener or restore hub.pid before `cos hub start`")
    else:
        click.echo(f"Hub: running (pid {pid})")
        click.echo(f"  Logs: {_log_file()}")
        stale, newest = _hub_code_is_stale()
        if stale:
            changed = newest.name if newest else "core code"
            click.echo(
                f"  ⚠ Running stale code — {changed} changed after the hub "
                f"started; run `cos hub restart` to load it"
            )

    meta_repo = Path(__file__).resolve().parent.parent.parent
    click.echo(f"  Meta repo: {meta_repo}")
    click.echo(f"  State dir: {_hub_dir()}")

    try:
        from cli.registry import load_registry

        reg = load_registry()
        alive = sum(1 for p in reg.projects if (Path(p.path) / ".coding-os").is_dir())
        stale = len(reg.projects) - alive
        click.echo(
            f"  Registered projects: {alive} alive"
            + (f" · {stale} stale (run `cos registry gc`)" if stale else "")
        )
    except Exception as exc:
        click.echo(f"  Registry: unavailable ({exc})")

    # Quick symlink-health ping — cheap, doesn't walk every file.
    try:
        from cli.sync_all import _dangling, _each_registered_project, _iter_symlinks

        broken_projects: list[str] = []
        for entry, path in _each_registered_project():
            links = _iter_symlinks(path)
            if any(_dangling(link) for link in links):
                broken_projects.append(entry.slug)
        if broken_projects:
            click.echo(
                f"  ⚠ Symlink health: broken in {broken_projects!r} — "
                f"run `cos sync-doctor --repair`"
            )
        else:
            click.echo("  ✓ Symlink health: all project hooks reachable")
    except Exception as exc:
        click.echo(f"  Symlink check: skipped ({exc})")

    if pid is None:
        sys.exit(1)


@hub_cli.command("logs")
@click.option("-n", "--lines", default=50, show_default=True, type=int)
def hub_logs(lines: int) -> None:
    """Tail the hub.log (stdlib, no dependencies)."""
    log = _log_file()
    if not log.exists():
        click.echo("(no hub log yet)")
        return
    with open(log, encoding="utf-8", errors="replace") as fh:
        content = fh.readlines()
    for line in content[-lines:]:
        click.echo(line.rstrip())
