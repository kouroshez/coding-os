"""CLI subcommands for scheduled job management: cos cron *."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import click

CODING_OS_ROOT = Path(__file__).resolve().parent.parent.parent
_PLIST_SRC = (
    CODING_OS_ROOT
    / "src"
    / "core"
    / "scheduled"
    / "launchd"
    / "com.codingos.nightly.plist.template"
)
_PLIST_DEST = Path.home() / "Library" / "LaunchAgents" / "com.codingos.nightly.plist"
_GLOBAL_SUMMARY = Path.home() / ".coding-os" / "scheduled" / "last_summary.json"
_NIGHTLY_SCRIPT = CODING_OS_ROOT / "src" / "core" / "scheduled" / "nightly.py"

_SYSTEMD_SRC = CODING_OS_ROOT / "src" / "core" / "scheduled" / "systemd"
_SERVICE_SRC = _SYSTEMD_SRC / "coding-os-nightly.service.template"
_TIMER_SRC = _SYSTEMD_SRC / "coding-os-nightly.timer.template"
_SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
_SERVICE_DEST = _SYSTEMD_USER_DIR / "coding-os-nightly.service"
_TIMER_DEST = _SYSTEMD_USER_DIR / "coding-os-nightly.timer"
_TIMER_UNIT = "coding-os-nightly.timer"


def _uv_path() -> str:
    uv = shutil.which("uv")
    if not uv:
        raise click.ClickException("uv not found in PATH. Install: https://docs.astral.sh/uv/")
    return uv


def _cos_nightly_path() -> str:
    """Prefer installed cos-nightly entry point; fall back to uv run."""
    installed = shutil.which("cos-nightly")
    if installed:
        return installed
    return ""


def _render_plist(hour: int) -> str:
    if not _PLIST_SRC.exists():
        raise click.ClickException(f"plist template not found: {_PLIST_SRC}")

    nightly_bin = _cos_nightly_path()
    if nightly_bin:
        # installed entry point — direct exec, no uv needed
        program_args = f"""  <array>
    <string>{nightly_bin}</string>
  </array>"""
    else:
        # dev / editable install — use uv run
        uv = _uv_path()
        program_args = f"""  <array>
    <string>{uv}</string>
    <string>run</string>
    <string>--project</string>
    <string>{CODING_OS_ROOT}</string>
    <string>python</string>
    <string>{_NIGHTLY_SCRIPT}</string>
  </array>"""

    template = _PLIST_SRC.read_text()
    # Replace ProgramArguments block (template has uv-run style — override entirely)
    import re

    template = re.sub(
        r"<key>ProgramArguments</key>\s*<array>.*?</array>",
        f"<key>ProgramArguments</key>\n{program_args}",
        template,
        flags=re.DOTALL,
    )
    return (
        template.replace("{{HOME}}", str(Path.home()))
        .replace("{{PATH}}", os.environ.get("PATH", ""))
        .replace("{{CRON_HOUR}}", str(hour))
        # {{CODING_OS_ROOT}} and {{UV_PATH}} no longer in body after substitution above
        .replace("{{CODING_OS_ROOT}}", str(CODING_OS_ROOT))
        .replace("{{UV_PATH}}", _uv_path())
    )


def _exec_args() -> list[str]:
    """Nightly invocation — prefer the installed cos-nightly binary, else uv run."""
    nightly_bin = _cos_nightly_path()
    if nightly_bin:
        return [nightly_bin]
    return [_uv_path(), "run", "--project", str(CODING_OS_ROOT), "python", str(_NIGHTLY_SCRIPT)]


def _render_systemd(hour: int) -> tuple[str, str]:
    if not _SERVICE_SRC.exists() or not _TIMER_SRC.exists():
        raise click.ClickException(f"systemd templates not found under {_SYSTEMD_SRC}")
    exec_start = " ".join(_exec_args())
    service = (
        _SERVICE_SRC.read_text()
        .replace("{{EXEC_START}}", exec_start)
        .replace("{{PATH}}", os.environ.get("PATH", ""))
        .replace("{{HOME}}", str(Path.home()))
    )
    timer = _TIMER_SRC.read_text().replace("{{CRON_HOUR}}", f"{hour:02d}")
    return service, timer


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def _install_launchd(hour: int) -> str:
    rendered = _render_plist(hour)
    _PLIST_DEST.parent.mkdir(parents=True, exist_ok=True)
    _PLIST_DEST.write_text(rendered)
    result = subprocess.run(
        ["launchctl", "load", "-w", str(_PLIST_DEST)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise click.ClickException(f"launchctl load failed: {result.stderr.strip()}")
    return "cos-nightly binary" if _cos_nightly_path() else "uv run (dev mode)"


def _install_systemd(hour: int) -> None:
    if not shutil.which("systemctl"):
        raise click.ClickException("systemctl not found — install systemd or schedule via crontab.")
    service, timer = _render_systemd(hour)
    _SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    _SERVICE_DEST.write_text(service)
    _TIMER_DEST.write_text(timer)
    _systemctl("daemon-reload")
    r = _systemctl("enable", "--now", _TIMER_UNIT)
    if r.returncode != 0:
        raise click.ClickException(f"systemctl enable failed: {r.stderr.strip()}")


def _uninstall_systemd() -> bool:
    if shutil.which("systemctl"):
        _systemctl("disable", "--now", _TIMER_UNIT)
    removed = False
    for dest in (_TIMER_DEST, _SERVICE_DEST):
        if dest.exists():
            dest.unlink()
            removed = True
    if shutil.which("systemctl"):
        _systemctl("daemon-reload")
    return removed


@click.group("cron")
def cron_cmd() -> None:
    """Manage the nightly scheduled maintenance job (CRON A)."""


@cron_cmd.command("install")
@click.option(
    "--hour", default=3, show_default=True, metavar="0-23", help="Hour of day to run (local time)."
)
def cron_install(hour: int) -> None:
    """Install + load the nightly job (macOS launchd / Linux systemd user timer)."""
    if not 0 <= hour <= 23:
        raise click.ClickException("--hour must be 0-23")

    log_dir = Path.home() / ".coding-os" / "scheduled"
    log_dir.mkdir(parents=True, exist_ok=True)

    system = platform.system()
    if system == "Darwin":
        mode = _install_launchd(hour)
        click.echo(f"✓ cron installed (launchd, {mode}) — runs daily at {hour:02d}:00")
        click.echo(f"  plist: {_PLIST_DEST}")
    elif system == "Linux":
        _install_systemd(hour)
        mode = "cos-nightly binary" if _cos_nightly_path() else "uv run (dev mode)"
        click.echo(f"✓ cron installed (systemd --user timer, {mode}) — runs daily at {hour:02d}:00")
        click.echo(f"  unit:  {_TIMER_DEST}")
    else:
        raise click.ClickException(
            f"unsupported OS {system!r}; schedule `cos cron run` via crontab instead."
        )
    click.echo(f"  logs:  {log_dir}")


@cron_cmd.command("uninstall")
def cron_uninstall() -> None:
    """Unload + remove the nightly job (launchd on macOS / systemd timer on Linux)."""
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["launchctl", "unload", "-w", str(_PLIST_DEST)], capture_output=True)
        if _PLIST_DEST.exists():
            _PLIST_DEST.unlink()
            click.echo("✓ cron uninstalled")
        else:
            click.echo("nothing to uninstall (plist not found)")
    elif system == "Linux":
        if _uninstall_systemd():
            click.echo("✓ cron uninstalled")
        else:
            click.echo("nothing to uninstall (timer not found)")
    else:
        click.echo(f"nothing to uninstall on {system}")


@cron_cmd.command("run")
@click.option("--dry-run", is_flag=True, help="Simulate without writing.")
@click.option("--project", "slug", default=None, metavar="SLUG", help="Run only this project slug.")
@click.option("--verbose", "-v", is_flag=True)
@click.option("--reset-failures", is_flag=True, help="Clear failure counter first.")
def cron_run(dry_run: bool, slug: str | None, verbose: bool, reset_failures: bool) -> None:
    """Run nightly maintenance now."""
    # Import nightly directly — no subprocess, no PYTHONPATH injection.
    # Both installed (uv tool install) and dev (editable) paths work because
    # pyproject.toml maps "scheduled" → "src/core/scheduled" so nightly is importable.
    try:
        from scheduled import nightly  # type: ignore[import]
    except ImportError as exc:
        raise click.ClickException(f"scheduled package not importable: {exc}") from exc

    argv: list[str] = []
    if dry_run:
        argv.append("--dry-run")
    if slug:
        argv += ["--project", slug]
    if verbose:
        argv.append("--verbose")
    if reset_failures:
        argv.append("--reset-failures")

    click.echo("[cron] running nightly maintenance…", err=True)
    rc = nightly.main(argv)
    sys.exit(rc if rc else 0)


@cron_cmd.command("status")
def cron_status() -> None:
    """Show last nightly run summary."""
    system = platform.system()
    if system == "Linux":
        installed = _TIMER_DEST.exists()
        loaded = bool(installed and shutil.which("systemctl")) and (
            _systemctl("is-enabled", _TIMER_UNIT).returncode == 0
        )
    else:
        installed = _PLIST_DEST.exists()
        loaded = False
        if installed and system == "Darwin":
            r = subprocess.run(
                ["launchctl", "list", "com.codingos.nightly"], capture_output=True
            )
            loaded = r.returncode == 0

    click.echo(f"installed : {installed}")
    click.echo(f"loaded    : {loaded}")

    if _GLOBAL_SUMMARY.exists():
        try:
            data = json.loads(_GLOBAL_SUMMARY.read_text())
            click.echo(f"last run  : {data.get('run_at', 'unknown')}")
            for proj in data.get("projects", []):
                slug = proj.get("slug", "?")
                err = proj.get("last_error")
                failures = proj.get("consecutive_failures", 0)
                click.echo(f"  [{slug}] failures={failures} error={err or 'none'}")
                for task, info in (proj.get("tasks") or {}).items():
                    status = info.get("status", "?")
                    reason = info.get("reason", "")
                    suffix = f" ({reason})" if reason else ""
                    click.echo(f"    {task}: {status}{suffix}")
        except (json.JSONDecodeError, OSError) as exc:
            click.echo(f"could not read summary: {exc}")
    else:
        click.echo("no run recorded yet — run: cos cron run")
