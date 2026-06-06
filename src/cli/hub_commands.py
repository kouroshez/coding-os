"""cli.hub_commands — `cos hub` + `cos service` CLI.

PURPOSE:      Start/stop/status the singleton FastAPI hub (127.0.0.1:9188) that
              serves every registered project, and manage it as an OS service.
INPUT:        `cos hub {start,stop,status,restart}` / `cos service ...`.
OUTPUT:       lifecycle actions + status on stdout; errors to stderr; precise exit.
DEPENDENCIES: ~/.coding-os/{hub.pid,hub.log}; uvicorn; the web app factory.
NOTES:        Stale-pid detection via os.kill(pid, 0); SIGTERM→SIGKILL escalation.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

import click

DEFAULT_HUB_PORT = 9188
HUB_HOST = "127.0.0.1"

SERVICE_NAME = "com.coding-os.hub"


def _hub_dir() -> Path:
    d = Path.home() / ".coding-os"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pid_file() -> Path:
    return _hub_dir() / "hub.pid"


def _log_file() -> Path:
    return _hub_dir() / "hub.log"


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


def _resolve_cos_bin() -> str:
    """Locate the `cos` entrypoint for the daemon to invoke."""
    import shutil

    which = shutil.which("cos")
    if which:
        return which
    return sys.argv[0]


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
def hub_start(port: int, foreground: bool) -> None:
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
        run_server(host=HUB_HOST, port=port)
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
        try:
            os.kill(existing, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(30):
            time.sleep(0.1)
            if _read_pid() is None:
                break
        if _read_pid() is not None:
            try:
                os.kill(existing, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for _ in range(20):
                time.sleep(0.1)
                if _read_pid() is None:
                    break
        _pid_file().unlink(missing_ok=True)

    log = _log_file()
    log.touch(exist_ok=True)
    cmd = [_resolve_cos_bin(), "hub", "start", "--foreground", "--port", str(port)]

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
    click.echo(f"Hub started (pid {proc.pid}) at http://{HUB_HOST}:{port}")
    click.echo(f"  Logs: {log}")


@hub_cli.command("stop")
def hub_stop() -> None:
    """Stop the running Hub daemon."""
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
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
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
        click.echo("Hub: not running")
    else:
        click.echo(f"Hub: running (pid {pid})")
        click.echo(f"  Logs: {_log_file()}")

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


# ---------------------------------------------------------------------------
# cos service install|uninstall  —  launchd (macOS) / systemd user (Linux)
# ---------------------------------------------------------------------------


@click.group(name="service", help="Install/uninstall the Hub as a user-scope service.")
def service_cli() -> None:
    """Parent group."""


def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_NAME}.plist"


def _systemd_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _render_launchd_plist(port: int) -> str:
    cos_bin = _resolve_cos_bin()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{cos_bin}</string>
        <string>hub</string>
        <string>start</string>
        <string>--foreground</string>
        <string>--port</string>
        <string>{port}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{_log_file()}</string>
    <key>StandardErrorPath</key>
    <string>{_log_file()}</string>
</dict>
</plist>
"""


def _render_systemd_unit(port: int) -> str:
    cos_bin = _resolve_cos_bin()
    return f"""[Unit]
Description=Coding OS Hub
After=network.target

[Service]
Type=simple
ExecStart={cos_bin} hub start --foreground --port {port}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""


@service_cli.command("install")
@click.option("--port", type=int, default=DEFAULT_HUB_PORT, show_default=True)
def service_install(port: int) -> None:
    """Write and load the user-scope service definition for the Hub."""
    system = platform.system()
    if system == "Darwin":
        plist_path = _launchd_plist_path()
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_text(_render_launchd_plist(port), encoding="utf-8")
        # Bootstrap into the user domain (idempotent: unload first if loaded).
        uid = os.getuid()
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{SERVICE_NAME}"],
            check=False,
            capture_output=True,
        )
        result = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            click.echo(
                f"WARN: launchctl bootstrap returned {result.returncode}: {result.stderr.strip()}",
                err=True,
            )
        click.echo(f"Installed launchd service: {plist_path}")
    elif system == "Linux":
        unit_path = _systemd_unit_path()
        unit_path.parent.mkdir(parents=True, exist_ok=True)
        unit_path.write_text(_render_systemd_unit(port), encoding="utf-8")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
        subprocess.run(
            ["systemctl", "--user", "enable", "--now", f"{SERVICE_NAME}.service"],
            check=False,
        )
        click.echo(f"Installed systemd user unit: {unit_path}")
    else:
        raise click.ClickException(f"Unsupported platform: {system}")


@service_cli.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the user-scope service definition."""
    system = platform.system()
    if system == "Darwin":
        uid = os.getuid()
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}/{SERVICE_NAME}"],
            check=False,
            capture_output=True,
        )
        plist_path = _launchd_plist_path()
        if plist_path.exists():
            plist_path.unlink()
            click.echo(f"Removed launchd plist: {plist_path}")
        else:
            click.echo("(no launchd plist present)")
    elif system == "Linux":
        subprocess.run(
            ["systemctl", "--user", "disable", "--now", f"{SERVICE_NAME}.service"],
            check=False,
        )
        unit_path = _systemd_unit_path()
        if unit_path.exists():
            unit_path.unlink()
            click.echo(f"Removed systemd unit: {unit_path}")
        else:
            click.echo("(no systemd unit present)")
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    else:
        raise click.ClickException(f"Unsupported platform: {system}")
