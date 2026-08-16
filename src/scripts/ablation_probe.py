"""Preflight the ablation cost probe: can one priced SWE-bench run execute here?

The pilot registered in docs/engineering/ablation-protocol.md is 300 runs and
nobody should fund it on a guessed price. Pricing it needs ONE run, not ten: the
trajectory of a single `raw` arm carries real input / cache / output token counts
and real wall-clock, and grading is deliberately skipped because the grader
answers completion rate, not cost. This reports which prerequisites that one run
is missing, so "can we run it" is answered by a command's output, not an opinion.

Never installs, never downloads the dataset, never calls a paid API, and never
prints a secret value — only the NAME of a key it can see.

Spec: docs/engineering/ablation-protocol.md

Usage:
    uv run python src/scripts/ablation_probe.py --preflight
    uv run python src/scripts/ablation_probe.py --preflight --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field

PILOT_RUNS = 300
COMMAND_TIMEOUT_SECONDS = 20
NETWORK_TIMEOUT_SECONDS = 15
CONTROL_AGENT = "mini-swe-agent"
DATASET = "princeton-nlp/SWE-bench_Verified"
DATASET_SIZE_ENDPOINT = f"https://datasets-server.huggingface.co/size?dataset={DATASET}"
# A SWE-bench eval image unpacks to ~1 GB and the agent runs a test suite inside
# it. Two gibibytes is a floor, not a measured requirement — the first real run
# replaces it with an observation.
MINIMUM_CONTAINER_MEMORY_BYTES = 2 * 1024**3
RERUN = "uv run python src/scripts/ablation_probe.py --preflight"
_KEY_PATTERN = re.compile(r"^[A-Z0-9_]*(API_KEY|AUTH_TOKEN|ANTHROPIC|OPENAI)[A-Z0-9_]*$")
_ANALYTICS_KEY_MARKERS = ("POSTHOG",)


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    fix: str = ""

    @property
    def marker(self) -> str:
        return "[OK]" if self.passed else "[FAIL]"


@dataclass
class Preflight:
    checks: list[Check] = field(default_factory=list)

    @property
    def blockers(self) -> list[Check]:
        return [check for check in self.checks if not check.passed]

    def to_dict(self) -> dict:
        return {
            "runs_required_to_price_the_pilot": 1,
            "pilot_runs": PILOT_RUNS,
            "ready": not self.blockers,
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail, "fix": c.fix}
                for c in self.checks
            ],
        }


def _run(command: list[str]) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=COMMAND_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return result.returncode, (result.stdout or result.stderr).strip()


def _gibibytes(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def check_container_runtime() -> Check:
    if shutil.which("docker") is None:
        return Check(
            "container runtime",
            False,
            "docker not on PATH",
            "install Docker Desktop or colima, then start the daemon",
        )
    code, output = _run(["docker", "info", "--format", "{{.ServerVersion}} {{.MemTotal}}"])
    if code != 0:
        first_line = output.splitlines()[0][:120] if output else "no output"
        return Check(
            "container runtime",
            False,
            f"docker present but the daemon did not answer: {first_line}",
            "start Docker Desktop (or `colima start`) and re-run",
        )
    version, _, memory = output.partition(" ")
    try:
        total = int(memory)
    except ValueError:
        return Check(
            "container runtime",
            False,
            f"daemon {version} answered but reported no usable MemTotal ({memory!r})",
            "upgrade or restart the runtime — memory headroom cannot be judged blind",
        )
    if total < MINIMUM_CONTAINER_MEMORY_BYTES:
        return Check(
            "container runtime",
            False,
            f"daemon {version} has {_gibibytes(total)} total, below the "
            f"{_gibibytes(MINIMUM_CONTAINER_MEMORY_BYTES)} floor",
            "raise the VM memory limit; also `docker stats` — other stacks may hold most of it",
        )
    return Check("container runtime", True, f"daemon {version}, {_gibibytes(total)} total")


def check_dataset_reachable() -> Check:
    try:
        with urllib.request.urlopen(
            DATASET_SIZE_ENDPOINT, timeout=NETWORK_TIMEOUT_SECONDS
        ) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Check(
            "dataset",
            False,
            f"{DATASET} not reachable: {exc}",
            "the instance list is remote and anonymous — check network or HF status",
        )
    rows = payload.get("size", {}).get("dataset", {}).get("num_rows")
    if not rows:
        return Check(
            "dataset",
            False,
            f"{DATASET} answered without a row count — the response shape changed",
            "re-check the datasets-server response before trusting the split",
        )
    return Check("dataset", True, f"{DATASET} reachable, {rows} instances")


def check_control_agent() -> Check:
    code, output = _run([sys.executable, "-c", "import minisweagent; print(minisweagent.__file__)"])
    if code == 0:
        return Check("control agent", True, f"{CONTROL_AGENT} importable at {output}")
    return Check(
        "control agent",
        False,
        f"{CONTROL_AGENT} not importable in this interpreter",
        f"uvx {CONTROL_AGENT}  # the raw arm IS this agent, unmodified",
    )


def check_model_credential() -> Check:
    names = sorted(
        name
        for name in os.environ
        if _KEY_PATTERN.match(name)
        and os.environ[name]
        and not any(marker in name for marker in _ANALYTICS_KEY_MARKERS)
    )
    if names:
        return Check("model credential", True, f"present: {', '.join(names)}")
    return Check(
        "model credential",
        False,
        "no provider key in the environment — the agent routes through litellm, "
        "which cannot borrow this session's OAuth",
        "export the key both arms will use — they MUST share one model",
    )


CHECKS = (
    check_container_runtime,
    check_dataset_reachable,
    check_control_agent,
    check_model_credential,
)


def preflight() -> Preflight:
    report = Preflight()
    for index, check in enumerate(CHECKS, start=1):
        print(f"[{index}/{len(CHECKS)}] {check.__name__}", file=sys.stderr)
        report.checks.append(check())
    return report


def render(report: Preflight) -> str:
    lines = ["Ablation cost probe — 1 run prices the 300-run pilot", ""]
    for check in report.checks:
        lines.append(f"{check.marker:<7}{check.name}: {check.detail}")
        if not check.passed and check.fix:
            lines.append(f"       fix: {check.fix}")
    lines.append("")
    passed = len(report.checks) - len(report.blockers)
    if report.blockers:
        names = ", ".join(check.name for check in report.blockers)
        lines.append(
            f"[FAIL] {passed} present, {len(report.blockers)} missing of "
            f"{len(report.checks)} — blocked on: {names} — rerun: {RERUN}"
        )
        lines.append("[SKIP] probe not started — a partial run prices nothing")
    else:
        lines.append(
            f"[OK] {passed} present, 0 missing of {len(report.checks)} — the probe can run"
        )
        lines.append("     read tokens and wall-clock from the trajectory; do not grade")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--preflight", action="store_true", help="report which prerequisites are missing"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)

    if not args.preflight:
        parser.print_help()
        return 0

    report = preflight()
    print(json.dumps(report.to_dict(), indent=2) if args.json else render(report))
    return 1 if report.blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
