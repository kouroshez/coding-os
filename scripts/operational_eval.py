#!/usr/bin/env python3
"""Operational evaluation harness for coding-os.

Runs a full end-to-end simulation of a real user installing coding-os in
sandbox projects (one per template), then captures everything into
`.build/` for manual/automated quality review.

Artifacts written under `<repo>/.build/`:

    sandboxes/{base,django,nextjs}/   # Scaffolded projects after `cos init`
    logs/
        cli/init-<tmpl>.log           # stdout+stderr of cos init
        cli/health-<tmpl>.log         # stdout+stderr of cos health
        mcp/selftest.log              # server.py --test
        verify/pytest.log             # pytest output
        verify/phase-c.log            # verify_phase_c_e2e output
        verify/make-verify.log        # make verify output
    snapshots/snapshot-<ts>.json      # aggregated stats
    reports/operational-eval.md       # human-readable report
    reports/scaffold-<tmpl>.txt       # tree listing per sandbox

All subprocesses run with explicit timeouts (memory:
feedback_script_safety — never let scripts hang silently).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import click

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / ".build"
SANDBOX_DIR = BUILD_DIR / "sandboxes"
LOG_DIR = BUILD_DIR / "logs"
SNAPSHOT_DIR = BUILD_DIR / "snapshots"
REPORT_DIR = BUILD_DIR / "reports"

TEMPLATES: tuple[str, ...] = ("base", "django", "nextjs")
DEFAULT_TIMEOUT = 180
VERIFY_TIMEOUT = 600


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_s: float
    log_path: str
    exit_code: int | None = None
    note: str = ""


@dataclass
class Snapshot:
    timestamp: str
    cos_binary: str | None
    steps: list[StepResult] = field(default_factory=list)
    scaffold_counts: dict[str, int] = field(default_factory=dict)
    db_sizes_kb: dict[str, float] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _ensure_dirs() -> None:
    for d in (BUILD_DIR, SANDBOX_DIR, LOG_DIR / "cli", LOG_DIR / "mcp",
              LOG_DIR / "verify", LOG_DIR / "doctor", SNAPSHOT_DIR, REPORT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _run(
    cmd: list[str],
    log_path: Path,
    *,
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> StepResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    header = f"$ {' '.join(cmd)}\n(cwd={cwd or Path.cwd()})\n\n"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        body = (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or "")
        log_path.write_text(header + body, encoding="utf-8")
        return StepResult(
            name=log_path.stem,
            ok=proc.returncode == 0,
            duration_s=round(time.monotonic() - started, 2),
            log_path=str(log_path.relative_to(REPO_ROOT)),
            exit_code=proc.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(
            header + f"\n!!! TIMEOUT after {exc.timeout}s\n",
            encoding="utf-8",
        )
        return StepResult(
            name=log_path.stem,
            ok=False,
            duration_s=float(timeout),
            log_path=str(log_path.relative_to(REPO_ROOT)),
            note="timeout",
        )
    except FileNotFoundError as exc:
        log_path.write_text(header + f"\n!!! NOT FOUND: {exc}\n", encoding="utf-8")
        return StepResult(
            name=log_path.stem,
            ok=False,
            duration_s=round(time.monotonic() - started, 2),
            log_path=str(log_path.relative_to(REPO_ROOT)),
            note="binary missing",
        )


def _which_cos() -> str | None:
    return shutil.which("cos")


def _cos_cmd(cos: str | None) -> list[str]:
    """Return the command prefix to invoke the coding-os CLI."""
    if cos:
        return [cos]
    return [sys.executable, "-m", "cli.main"]


def _clean_sandbox(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _count_files(path: Path) -> int:
    return sum(1 for _ in path.rglob("*") if _.is_file())


def _tree(path: Path, max_depth: int = 3) -> str:
    lines: list[str] = [str(path)]

    def walk(p: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
        except (PermissionError, FileNotFoundError):
            return
        for i, entry in enumerate(entries):
            last = i == len(entries) - 1
            connector = "└── " if last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            if entry.is_dir() and not entry.is_symlink():
                extension = "    " if last else "│   "
                walk(entry, depth + 1, prefix + extension)

    walk(path, 1, "")
    return "\n".join(lines)


def _db_size_kb(sandbox: Path) -> float:
    db = sandbox / ".coding-os" / "coding-os.db"
    if not db.exists():
        return 0.0
    return round(db.stat().st_size / 1024, 1)


def _step_init_sandbox(
    template: str,
    cos_cmd_prefix: list[str],
    snapshot: Snapshot,
) -> Path:
    """Run `cos init` for a template into .build/sandboxes/<template>."""
    sandbox = SANDBOX_DIR / template
    _clean_sandbox(sandbox)

    cmd = cos_cmd_prefix + ["init", "--agent", "claude",
                            "--project-dir", str(sandbox)]
    if template != "base":
        cmd.extend(["--template", template])

    log = LOG_DIR / "cli" / f"init-{template}.log"
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    result = _run(cmd, log, cwd=REPO_ROOT, env=env)
    snapshot.steps.append(result)

    snapshot.scaffold_counts[template] = _count_files(sandbox)
    snapshot.db_sizes_kb[template] = _db_size_kb(sandbox)

    (REPORT_DIR / f"scaffold-{template}.txt").write_text(
        _tree(sandbox, max_depth=3) + "\n", encoding="utf-8",
    )
    return sandbox


def _step_health(
    template: str,
    sandbox: Path,
    cos_cmd_prefix: list[str],
    snapshot: Snapshot,
) -> None:
    cmd = cos_cmd_prefix + ["health", "--project-dir", str(sandbox)]
    log = LOG_DIR / "cli" / f"health-{template}.log"
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    result = _run(cmd, log, cwd=REPO_ROOT, env=env)
    snapshot.steps.append(result)


def _step_doctor(
    template: str,
    sandbox: Path,
    cos_cmd_prefix: list[str],
    snapshot: Snapshot,
) -> None:
    """Run `cos doctor --format json` against the sandbox."""
    cmd = cos_cmd_prefix + [
        "doctor", "--project-dir", str(sandbox), "--format", "json",
    ]
    log = LOG_DIR / "doctor" / f"{template}.log"
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(REPO_ROOT))
    result = _run(cmd, log, cwd=REPO_ROOT, env=env)
    snapshot.steps.append(result)


def _step_mcp_selftest(snapshot: Snapshot) -> None:
    cmd = [sys.executable, str(REPO_ROOT / "core" / "thinking_os" / "server.py"),
           "--test"]
    log = LOG_DIR / "mcp" / "selftest.log"
    result = _run(cmd, log, cwd=REPO_ROOT, timeout=60)
    snapshot.steps.append(result)


def _step_pytest(snapshot: Snapshot) -> None:
    cmd = ["uv", "run", "pytest", "core/thinking_os/tests/", "-q", "--tb=short"]
    log = LOG_DIR / "verify" / "pytest.log"
    result = _run(cmd, log, cwd=REPO_ROOT, timeout=VERIFY_TIMEOUT)
    snapshot.steps.append(result)


def _step_phase_c(snapshot: Snapshot) -> None:
    script = REPO_ROOT / "scripts" / "verify_phase_c_e2e.py"
    if not script.exists():
        return
    cmd = [sys.executable, str(script)]
    log = LOG_DIR / "verify" / "phase-c.log"
    result = _run(cmd, log, cwd=REPO_ROOT, timeout=VERIFY_TIMEOUT)
    snapshot.steps.append(result)


def _step_make_verify(snapshot: Snapshot) -> None:
    cmd = ["make", "verify"]
    log = LOG_DIR / "verify" / "make-verify.log"
    result = _run(cmd, log, cwd=REPO_ROOT, timeout=VERIFY_TIMEOUT)
    snapshot.steps.append(result)


def _write_snapshot(snapshot: Snapshot) -> Path:
    ts = _now_ts()
    path = SNAPSHOT_DIR / f"snapshot-{ts}.json"
    snapshot.totals = {
        "steps_total": len(snapshot.steps),
        "steps_passed": sum(1 for s in snapshot.steps if s.ok),
        "steps_failed": sum(1 for s in snapshot.steps if not s.ok),
        "scaffold_files_total": sum(snapshot.scaffold_counts.values()),
    }
    payload = asdict(snapshot)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest = SNAPSHOT_DIR / "snapshot-latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _write_report(snapshot: Snapshot, snapshot_path: Path) -> Path:
    lines: list[str] = []
    lines.append("# Coding-OS — Operational Evaluation Report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): `{snapshot.timestamp}`")
    cos_str = snapshot.cos_binary or "NOT INSTALLED (fallback to python -m cli.main)"
    lines.append(f"- `cos` binary: `{cos_str}`")
    lines.append(f"- Snapshot: `{snapshot_path.relative_to(REPO_ROOT)}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    totals = snapshot.totals
    lines.append(
        f"- Steps: **{totals.get('steps_passed', 0)}/"
        f"{totals.get('steps_total', 0)} passed**"
    )
    lines.append(
        f"- Total scaffold files across sandboxes: "
        f"**{totals.get('scaffold_files_total', 0)}**"
    )
    lines.append("")
    lines.append("## Per-Template Scaffold")
    lines.append("")
    lines.append("| Template | Files | DB (KB) | Sandbox |")
    lines.append("| --- | --- | --- | --- |")
    for tmpl in TEMPLATES:
        files = snapshot.scaffold_counts.get(tmpl, 0)
        db = snapshot.db_sizes_kb.get(tmpl, 0.0)
        lines.append(f"| {tmpl} | {files} | {db} | `.build/sandboxes/{tmpl}/` |")
    lines.append("")
    lines.append("## Steps")
    lines.append("")
    lines.append("| Step | Status | Duration (s) | Exit | Log |")
    lines.append("| --- | --- | --- | --- | --- |")
    for step in snapshot.steps:
        status = "PASS" if step.ok else "FAIL"
        note = f" ({step.note})" if step.note else ""
        lines.append(
            f"| {step.name} | {status}{note} | {step.duration_s} | "
            f"{step.exit_code} | `{step.log_path}` |"
        )
    lines.append("")
    lines.append("## How to inspect")
    lines.append("")
    lines.append("```bash")
    lines.append("tree -L 3 .build/sandboxes/base")
    lines.append("cat .build/logs/cli/init-base.log")
    lines.append("cat .build/logs/verify/pytest.log | tail -60")
    lines.append("cat .build/snapshots/snapshot-latest.json | jq .")
    lines.append("```")
    lines.append("")
    lines.append("## Gaps & Follow-ups (fill manually after reviewing)")
    lines.append("")
    lines.append("- [ ] All scaffold files copied as expected?")
    lines.append("- [ ] `.claude/settings.json` resolved templates correctly?")
    lines.append("- [ ] MCP server boots on sandbox DBs?")
    lines.append("- [ ] Hooks fire on simulated edits?")
    lines.append("- [ ] RAG index (Phase B) populated?")
    lines.append("- [ ] Task sync (Phase C) works from docs/tasks/?")
    lines.append("")

    path = REPORT_DIR / "operational-eval.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@click.group()
def cli() -> None:
    """Operational evaluation harness for coding-os."""


@cli.command("all")
@click.option("--skip-verify", is_flag=True,
              help="Skip long verify steps (pytest, make verify, phase-c).")
def run_all(skip_verify: bool) -> None:
    """Run the full evaluation end-to-end."""
    _ensure_dirs()
    cos_binary = _which_cos()
    prefix = _cos_cmd(cos_binary)
    snapshot = Snapshot(timestamp=_now_ts(), cos_binary=cos_binary)

    click.echo(f"[eval] cos binary: {cos_binary or 'FALLBACK (python -m cli.main)'}")
    click.echo(f"[eval] build dir:  {BUILD_DIR}")

    for tmpl in TEMPLATES:
        click.echo(f"[eval] init sandbox: {tmpl}")
        sandbox = _step_init_sandbox(tmpl, prefix, snapshot)
        click.echo(f"[eval] health:       {tmpl}")
        _step_health(tmpl, sandbox, prefix, snapshot)
        click.echo(f"[eval] doctor:       {tmpl}")
        _step_doctor(tmpl, sandbox, prefix, snapshot)

    click.echo("[eval] mcp self-test")
    _step_mcp_selftest(snapshot)

    if not skip_verify:
        click.echo("[eval] pytest")
        _step_pytest(snapshot)
        click.echo("[eval] phase-c e2e")
        _step_phase_c(snapshot)
        click.echo("[eval] make verify")
        _step_make_verify(snapshot)

    snapshot_path = _write_snapshot(snapshot)
    report_path = _write_report(snapshot, snapshot_path)

    passed = snapshot.totals["steps_passed"]
    total = snapshot.totals["steps_total"]
    click.echo(f"\n[eval] DONE — {passed}/{total} steps passed")
    click.echo(f"[eval] report:   {report_path.relative_to(REPO_ROOT)}")
    click.echo(f"[eval] snapshot: {snapshot_path.relative_to(REPO_ROOT)}")
    sys.exit(0 if passed == total else 1)


@cli.command("clean")
def clean() -> None:
    """Remove .build/ entirely."""
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
        click.echo(f"Removed {BUILD_DIR}")
    else:
        click.echo("Nothing to clean.")


@cli.command("sandboxes")
def sandboxes_only() -> None:
    """Rebuild only the sandboxes (skip verify steps)."""
    _ensure_dirs()
    cos_binary = _which_cos()
    prefix = _cos_cmd(cos_binary)
    snapshot = Snapshot(timestamp=_now_ts(), cos_binary=cos_binary)
    for tmpl in TEMPLATES:
        click.echo(f"[eval] init sandbox: {tmpl}")
        sandbox = _step_init_sandbox(tmpl, prefix, snapshot)
        _step_health(tmpl, sandbox, prefix, snapshot)
        _step_doctor(tmpl, sandbox, prefix, snapshot)
    snapshot_path = _write_snapshot(snapshot)
    _write_report(snapshot, snapshot_path)
    click.echo(f"[eval] sandboxes ready under {SANDBOX_DIR}")


if __name__ == "__main__":
    cli()
