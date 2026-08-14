"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

import click

from ._doctor_shared import (  # noqa: F401
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
    IGNORED_PREFIXES,
    MANIFEST_PATH_DEFAULT,
    MCP_SERVER_PATH,
    PLACEHOLDER_RE,
    RUNTIME_PATHS,
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    STATE_DIR_DEFAULT,
    CheckResult,
    DoctorReport,
    _derive_expected_schema_version,
    _load_doctor_config,
    _load_runtime_paths,
    _scan_project_files,
    _tick,
)

logger = logging.getLogger(__name__)


def _probe_agent_sdk() -> None:
    import importlib.metadata
    import os
    import shutil
    import subprocess
    from pathlib import Path

    import yaml

    target_id = os.environ.get("COS_AGENT", "")
    adapters_root = Path(__file__).resolve().parent.parent.parent / "src" / "adapters"
    if not target_id:
        for adapter_dir in sorted(adapters_root.iterdir()):
            if adapter_dir.is_dir() and (adapter_dir / "adapter.yaml").exists():
                target_id = adapter_dir.name
                break

    meta_path = adapters_root / target_id / "adapter.yaml"
    adapter = yaml.safe_load(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    cli_binary = adapter.get("cli_binary") or target_id
    sdk_package = adapter.get("sdk_package") or ""
    sdk_optional_extra = adapter.get("sdk_optional_extra") or ""
    label = adapter.get("label") or target_id

    click.echo(f"{label} SDK compatibility report")
    click.echo("=" * 60)

    if sdk_package:
        try:
            sdk_version = importlib.metadata.version(sdk_package)
            click.echo(f"  [OK]   {sdk_package} = {sdk_version}")
        except importlib.metadata.PackageNotFoundError:
            if sdk_optional_extra:
                click.echo(
                    f"  [WARN] {sdk_package} not installed "
                    f"(uv sync --extra {sdk_optional_extra}; CLI fallback remains available)"
                )
            else:
                click.echo(f"  [FAIL] {sdk_package} not installed (uv sync --extra rag)")
    else:
        click.echo("  [SKIP] no sdk_package declared in adapter.yaml")

    cli_path = shutil.which(cli_binary)
    if cli_path:
        try:
            result = subprocess.run(
                [cli_path, "--version"], capture_output=True, text=True, timeout=5
            )
            cli_version = result.stdout.strip() or result.stderr.strip()
            click.echo(f"  [OK]   {cli_binary} CLI = {cli_version} ({cli_path})")
        except (subprocess.TimeoutExpired, OSError) as exc:
            click.echo(f"  [WARN] {cli_binary} CLI unreachable: {exc}")
    else:
        click.echo(f"  [WARN] {cli_binary} CLI not on PATH")

    auth_env_vars = [str(name) for name in adapter.get("auth_env_vars", []) if name]
    configured_auth = [name for name in auth_env_vars if os.environ.get(name)]
    if configured_auth:
        click.echo(f"  [OK]   {configured_auth[0]} set")
    elif auth_env_vars:
        click.echo(
            f"  [WARN] none of {', '.join(auth_env_vars)} set "
            "(CLI-managed login may still be valid)"
        )
    else:
        click.echo("  [SKIP] no auth_env_vars declared in adapter.yaml")

    for marker in adapter.get("runtime_env_markers", []):
        value = os.environ.get(str(marker))
        if value:
            click.echo(f"  [OK]   {marker} = {value!r}")

    mcp_paths: list[Path] = []
    for entry in adapter.get("mcp_launch", {}).get("config_paths", []):
        if not isinstance(entry, dict) or not entry.get("path"):
            continue
        base = Path.home() if entry.get("scope") == "home" else Path.cwd()
        mcp_paths.append(base / str(entry["path"]))
    present_mcp_paths = [path for path in mcp_paths if path.exists()]
    if present_mcp_paths:
        click.echo(f"  [OK]   MCP config present ({present_mcp_paths[0].resolve()})")
    elif mcp_paths:
        expected = ", ".join(str(path) for path in mcp_paths)
        click.echo(f"  [WARN] MCP config missing ({expected})")
    else:
        click.echo("  [SKIP] no MCP config paths declared in adapter.yaml")


def _probe_otel() -> None:
    """Print OTEL configuration table for cos doctor --otel (T8.3)."""
    import os
    import socket

    _VARS = [
        "OTEL_TRACES_EXPORTER",
        "OTEL_METRICS_EXPORTER",
        "OTEL_LOGS_EXPORTER",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_EXPORTER_OTLP_HEADERS",
        "OTEL_RESOURCE_ATTRIBUTES",
        "OTEL_SERVICE_NAME",
        "CLAUDE_CODE_ENABLE_TELEMETRY",
    ]
    configured = {v: os.environ.get(v) for v in _VARS}
    click.echo("OTEL probe")
    click.echo("=" * 60)
    for var, val in configured.items():
        if val:
            click.echo(f"  [OK]  {var} = {val!r}")
        else:
            click.echo(f"  [--]  {var} = not set")

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
    if endpoint:
        click.echo("")
        click.echo(f"Probing endpoint: {endpoint}")
        try:
            from urllib.parse import urlparse as _up

            parsed = _up(endpoint)
            host = parsed.hostname or "localhost"
            port = parsed.port or (443 if parsed.scheme == "https" else 4317)
            with socket.create_connection((host, port), timeout=3):
                click.echo(f"  [OK]  TCP {host}:{port} reachable")
        except OSError as exc:
            click.echo(f"  [ERR] TCP unreachable: {exc}")
    else:
        click.echo("\nNo OTEL_EXPORTER_OTLP_ENDPOINT set — local stdout exporter assumed.")


_BOOTSTRAP_MIN_PYTHON = (3, 10)
_BOOTSTRAP_MIN_BASH_MAJOR = 4


def _capture_tool_version(executable: str) -> str | None:
    """First line of `<tool> --version`, or None when the tool is absent."""
    import shutil

    if shutil.which(executable) is None:
        return None
    try:
        proc = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (proc.stdout or proc.stderr or "").strip()
    return text.splitlines()[0] if text else ""


def _check_bootstrap_python(report: DoctorReport) -> None:
    found = sys.version_info[:2]
    label = f"python {found[0]}.{found[1]}"
    if found >= _BOOTSTRAP_MIN_PYTHON:
        report.checks.append(CheckResult("bootstrap.python_version", SEV_PASS, label))
    else:
        report.checks.append(
            CheckResult(
                "bootstrap.python_version",
                SEV_FAIL,
                f"{label} < {_BOOTSTRAP_MIN_PYTHON[0]}.{_BOOTSTRAP_MIN_PYTHON[1]} — "
                "install a newer Python and reinstall cos with it",
            )
        )


def _check_bootstrap_bash(report: DoctorReport) -> None:
    from . import doctor as _kernel

    banner = _kernel._capture_tool_version("bash")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.bash_version",
                SEV_FAIL,
                "bash not found on PATH — hook scripts require bash >= 4",
            )
        )
        return
    match = re.search(r"version (\d+)\.(\d+)", banner)
    major = int(match.group(1)) if match else 0
    if major >= _BOOTSTRAP_MIN_BASH_MAJOR:
        report.checks.append(CheckResult("bootstrap.bash_version", SEV_PASS, banner))
    else:
        report.checks.append(
            CheckResult(
                "bootstrap.bash_version",
                SEV_FAIL,
                f"{banner} — hooks need bash >= 4 (macOS ships 3.2: brew install bash)",
            )
        )


def _check_bootstrap_git(report: DoctorReport) -> None:
    from . import doctor as _kernel

    banner = _kernel._capture_tool_version("git")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.git_present",
                SEV_FAIL,
                "git not found — `cos init` runs git init "
                "(macOS: xcode-select --install · debian: apt install git)",
            )
        )
    else:
        report.checks.append(CheckResult("bootstrap.git_present", SEV_PASS, banner))


def _check_bootstrap_uv(report: DoctorReport) -> None:
    from . import doctor as _kernel

    banner = _kernel._capture_tool_version("uv")
    if banner is None:
        report.checks.append(
            CheckResult(
                "bootstrap.uv_present",
                SEV_WARN,
                "uv not found — updates and extras install through it "
                "(curl -LsSf https://astral.sh/uv/install.sh | sh)",
            )
        )
    else:
        report.checks.append(CheckResult("bootstrap.uv_present", SEV_PASS, banner))


def _check_bootstrap_sed(report: DoctorReport) -> None:
    from . import doctor as _kernel

    banner = _kernel._capture_tool_version("sed")
    if banner is None:
        report.checks.append(CheckResult("bootstrap.sed_flavor", SEV_WARN, "sed not found on PATH"))
        return
    flavor = "gnu" if "GNU" in banner else "bsd"
    report.checks.append(
        CheckResult("bootstrap.sed_flavor", SEV_PASS, f"{flavor} sed detected", {"flavor": flavor})
    )


def _check_bootstrap_hook_parsers(report: DoctorReport) -> None:
    from . import doctor as _kernel

    # The hook layer reads its stdin envelope and extracts fields from it; both
    # halves degrade (perl→python3→cat, jq→python3) but with NO parser at all a
    # gate cannot evaluate and fails closed on every tool call — an unusable
    # install, not a silent one. observability-eye § 5 I8.
    present = [t for t in ("jq", "perl", "python3") if _kernel._capture_tool_version(t)]
    if "python3" in present:
        extras = [t for t in ("jq", "perl") if t in present]
        detail = f"python3 + {', '.join(extras)}" if extras else "python3 only (fallback path)"
        report.checks.append(
            CheckResult(
                "bootstrap.hook_parsers", SEV_PASS, f"hook gates can parse: {detail}"
            )
        )
        return
    report.checks.append(
        CheckResult(
            "bootstrap.hook_parsers",
            SEV_FAIL,
            "no python3 on PATH — enforcement hooks cannot read their input and "
            "fail closed on every tool call. Install python3 (jq optional, faster).",
        )
    )


def run_bootstrap_doctor() -> DoctorReport:
    """Preflight prerequisite checks — no initialized project required.

    Encodes README § Prerequisites; check docs live in
    docs/playbooks/doctor-checks.md § bootstrap (TASK-347).
    """
    report = DoctorReport(project_dir="-", agent=None, templates=[])
    _check_bootstrap_python(report)
    _check_bootstrap_bash(report)
    _check_bootstrap_git(report)
    _check_bootstrap_uv(report)
    _check_bootstrap_sed(report)
    _check_bootstrap_hook_parsers(report)
    return report
