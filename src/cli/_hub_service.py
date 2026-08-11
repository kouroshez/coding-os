"""`cos service` — install/uninstall the Hub as a user-scope OS service.

launchd on macOS, systemd --user on Linux; every other platform is refused.
The rendered definition invokes the same `cos hub start --foreground` the
`hub` group runs by hand.
"""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

import click

from cli._hub_paths import (
    DEFAULT_HUB_PORT,
    SERVICE_NAME,
    _log_file,
    _resolve_cos_bin,
)


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
