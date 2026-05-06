"""Coding OS — `cos verify --since-edit`."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import click


# ---------------------------------------------------------------------------
# Matrix — keep in sync with AGENTS.md "Verification Matrix" + core/rules/
# test-discipline.md. Glob → command. First match wins for a given file.
# ---------------------------------------------------------------------------

MATRIX_RULES: list[tuple[str, str]] = [
    # (glob-prefix, command)
    ("core/thinking_os/db.py",
        "uv run --extra rag pytest core/thinking_os/tests/test_db.py -q"),
    ("core/thinking_os/",
        "uv run --extra rag pytest core/thinking_os/tests/ -q"),
    ("core/graph_os/",
        "uv run --extra graph_os pytest core/graph_os/tests/ -q"),
    ("core/board_os/",
        "uv run --extra rag --with aiohttp --with pytest-asyncio pytest core/board_os/tests/ -q"),
    ("core/hooks/",
        "make verify-hooks"),
    ("core/scripts/",
        "make verify-hooks"),
    ("adapters/",
        "uv run pytest tests/test_adapters.py tests/test_adapter_parity.py -q"),
    ("cli/",
        "uv run pytest tests/test_cli.py -q"),
    ("templates/",
        "uv run pytest tests/test_template_scaffold.py -q"),
    ("docs/",
        "make docs-lint"),
]


# ---------------------------------------------------------------------------
# IO contracts
# ---------------------------------------------------------------------------

@dataclass
class SuiteResult:
    command: str
    files: list[str] = field(default_factory=list)
    exit_code: int = 0
    duration_s: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


@dataclass
class RefIssue:
    file: str
    old_name: str
    new_name: str
    callers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _git_diff_names(since: str, staged_only: bool) -> list[str]:
    """List changed files vs `since`. Includes staged + unstaged + untracked."""
    repo_root = _repo_root()
    if repo_root is None:
        return []

    files: set[str] = set()

    if staged_only:
        cmd = ["git", "diff", "--name-only", "--cached"]
    else:
        cmd = ["git", "diff", "--name-only", since]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=10,
    )
    if result.returncode == 0:
        files.update(line.strip() for line in result.stdout.splitlines() if line.strip())

    if not staged_only:
        # Include untracked + unstaged-modified
        ls = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "--modified"],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=10,
        )
        if ls.returncode == 0:
            files.update(line.strip() for line in ls.stdout.splitlines() if line.strip())

    return sorted(files)


def _repo_root() -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip())


def _map_files_to_suites(files: list[str]) -> dict[str, list[str]]:
    """Group changed files under the matrix command they trigger.

    Returns: {command: [files]}. Files that don't match any rule are
    grouped under the special key '__unmatched__' for visibility.
    """
    buckets: dict[str, list[str]] = {}
    for f in files:
        matched = False
        for prefix, cmd in MATRIX_RULES:
            if f.startswith(prefix):
                buckets.setdefault(cmd, []).append(f)
                matched = True
                break
        if not matched:
            buckets.setdefault("__unmatched__", []).append(f)
    return buckets


def _run_suite(command: str, files: list[str], cwd: Path) -> SuiteResult:
    started = time.time()
    proc = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=300,
    )
    return SuiteResult(
        command=command,
        files=files,
        exit_code=proc.returncode,
        duration_s=round(time.time() - started, 2),
        stdout_tail=proc.stdout[-1500:] if proc.stdout else "",
        stderr_tail=proc.stderr[-1500:] if proc.stderr else "",
    )


# ---------------------------------------------------------------------------
# Symbol-ref scan — partial-rename detector.
# ---------------------------------------------------------------------------

_RENAME_DIFF_RE = re.compile(
    r"^-(?P<minus>.*\b(?P<old>[A-Za-z_][A-Za-z0-9_]{2,})\b.*)\n"
    r"\+(?P<plus>.*\b(?P<new>[A-Za-z_][A-Za-z0-9_]{2,})\b.*)$",
    re.MULTILINE,
)


def _scan_renames(since: str, repo_root: Path) -> list[RefIssue]:
    """Cheap heuristic: scan diff hunks for `-foo` paired with `+bar`
    where lines are otherwise similar. Then grep the rest of the repo
    for unreplaced `foo` references.

    Imperfect on purpose: false positives are surfaced as warnings so
    the agent reviews; false negatives are caught by the test matrix.
    """
    diff = subprocess.run(
        ["git", "diff", "-U0", since],
        capture_output=True,
        text=True,
        cwd=repo_root,
        timeout=15,
    )
    if diff.returncode != 0:
        return []

    issues: list[RefIssue] = []
    seen: set[tuple[str, str]] = set()
    for match in _RENAME_DIFF_RE.finditer(diff.stdout):
        old, new = match.group("old"), match.group("new")
        if old == new or len(old) < 4 or len(new) < 4:
            continue
        if (old, new) in seen:
            continue
        seen.add((old, new))
        # Sanity: line must be lexically similar (not unrelated lines that
        # happen to be adjacent in the diff).
        m, p = match.group("minus"), match.group("plus")
        if abs(len(m) - len(p)) > max(8, len(m) // 4):
            continue
        # grep for unreplaced `old`
        grep = subprocess.run(
            ["git", "grep", "-l", "-n", "--word-regexp", "--", old],
            capture_output=True,
            text=True,
            cwd=repo_root,
            timeout=10,
        )
        if grep.returncode != 0:
            continue
        callers = [
            line.strip() for line in grep.stdout.splitlines()
            if line.strip() and not line.strip().endswith(".pyc")
        ]
        if not callers:
            continue
        issues.append(RefIssue(
            file=callers[0],
            old_name=old,
            new_name=new,
            callers=callers,
        ))
    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command("verify")
@click.option(
    "--since",
    default="HEAD",
    show_default=True,
    help="Diff base — HEAD, branch name, or commit SHA.",
)
@click.option(
    "--staged",
    is_flag=True,
    default=False,
    help="Only consider staged changes (git diff --cached).",
)
@click.option(
    "--refs",
    is_flag=True,
    default=False,
    help="Run symbol-rename consistency scan (catches partial renames).",
)
@click.option(
    "--no-tests",
    is_flag=True,
    default=False,
    help="Skip matrix test runs; only do --refs scan.",
)
@click.option(
    "--parallel/--serial",
    default=True,
    show_default=True,
    help="Run matrix suites in parallel (default) or one at a time.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def verify_since_edit_cmd(
    since: str,
    staged: bool,
    refs: bool,
    no_tests: bool,
    parallel: bool,
    output_format: str,
) -> None:
    """Fast scope-aware verification: matrix tests + symbol-ref scan.

    Replaces broad `pytest tests/ -q` (~6 min) with the matrix commands
    that match the files you actually changed (~20–90s typical).
    """
    repo_root = _repo_root()
    if repo_root is None:
        click.echo("verify: not a git repo (or git unavailable).", err=True)
        sys.exit(2)

    files = _git_diff_names(since, staged)
    if not files:
        click.echo("verify: no changed files vs " + since)
        sys.exit(0)

    buckets = _map_files_to_suites(files)
    suites = [(cmd, fs) for cmd, fs in buckets.items() if cmd != "__unmatched__"]
    unmatched = buckets.get("__unmatched__", [])

    # ------------------------------------------------------------------
    # Symbol-ref scan
    # ------------------------------------------------------------------
    ref_issues: list[RefIssue] = []
    if refs:
        ref_issues = _scan_renames(since, repo_root)

    # ------------------------------------------------------------------
    # Matrix runs
    # ------------------------------------------------------------------
    results: list[SuiteResult] = []
    if not no_tests and suites:
        if parallel and len(suites) > 1:
            with ThreadPoolExecutor(max_workers=min(4, len(suites))) as pool:
                futures = {
                    pool.submit(_run_suite, cmd, fs, repo_root): cmd
                    for cmd, fs in suites
                }
                for fut in as_completed(futures):
                    results.append(fut.result())
        else:
            for cmd, fs in suites:
                results.append(_run_suite(cmd, fs, repo_root))

    failed = [r for r in results if not r.passed]
    overall = 0 if not failed and not ref_issues else 1

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    if output_format == "json":
        payload = {
            "since": since,
            "files": files,
            "suites": [
                {
                    "command": r.command,
                    "files": r.files,
                    "exit_code": r.exit_code,
                    "duration_s": r.duration_s,
                    "passed": r.passed,
                    "stdout_tail": r.stdout_tail,
                    "stderr_tail": r.stderr_tail,
                }
                for r in results
            ],
            "ref_issues": [
                {
                    "old_name": issue.old_name,
                    "new_name": issue.new_name,
                    "callers": issue.callers,
                }
                for issue in ref_issues
            ],
            "unmatched_files": unmatched,
            "overall_exit": overall,
        }
        click.echo(json.dumps(payload, indent=2))
        sys.exit(overall)

    # Text output
    click.echo(f"verify --since {since}: {len(files)} changed file(s)")
    for cmd, fs in suites:
        click.echo(f"  • {cmd}  ({len(fs)} file{'s' if len(fs) != 1 else ''})")
    if unmatched:
        click.echo(f"  • [unmatched] {len(unmatched)} file(s) — no matrix rule")
        for f in unmatched[:5]:
            click.echo(f"      - {f}")

    if results:
        click.echo("")
        click.echo("Results:")
        for r in results:
            status = "✓" if r.passed else "✗"
            click.echo(f"  {status} {r.command}  ({r.duration_s:.1f}s)")
            if not r.passed:
                tail = r.stderr_tail or r.stdout_tail
                for line in tail.splitlines()[-15:]:
                    click.echo(f"      {line}")

    if ref_issues:
        click.echo("")
        click.echo(f"Symbol-rename warnings ({len(ref_issues)}):")
        for issue in ref_issues:
            click.echo(f"  ⚠ {issue.old_name} → {issue.new_name}")
            for caller in issue.callers[:5]:
                click.echo(f"      still referenced in: {caller}")

    if overall == 0:
        click.echo("")
        click.echo("verify: ✓ all passed")
    else:
        click.echo("")
        click.echo(f"verify: ✗ {len(failed)} suite(s) failed, {len(ref_issues)} ref warning(s)")
    sys.exit(overall)
