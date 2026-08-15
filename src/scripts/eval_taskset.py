"""Mine closed tasks for ablation candidates whose acceptance is machine-checkable.

The ablation needs tasks a script can score without a model in the loop, so the
only ones that qualify are those whose acceptance criterion names a command. That
filter is strict on purpose: a task scored by prose is a task scored by whoever
reads the prose.

Mining is not selection. This emits a **candidate list for human review** — an
entry earns its place in the locked set only after someone confirms the prompt is
answerable from the starting commit and the command genuinely fails there. Scoring
a task whose work already exists at the starting state is the eval equivalent of
benchmarking a truncated envelope.

Spec: docs/engineering/ablation-protocol.md

Usage:
    uv run python src/scripts/eval_taskset.py
    uv run python src/scripts/eval_taskset.py --out docs/_meta/eval-candidates.yaml
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = REPO_ROOT / "docs" / "tasks"
GIT_TIMEOUT_SECONDS = 30
PROGRESS_EVERY = 200

# A "Then" clause only scores itself if it names something a shell can run.
_RUNNABLE = re.compile(
    r"\b(uv run [^\n,;]+|make [a-z][a-z0-9-]*|pytest [^\n,;]+|cos [a-z][a-z-]+[^\n,;]*)"
)
_OUTCOME = re.compile(r"^\*\*Outcome \(one sentence\):\*\*\s*(.+)$", re.MULTILINE)
_ACCEPTANCE_BLOCK = re.compile(r"^## Acceptance.*?$(.*?)^## ", re.MULTILINE | re.DOTALL)
_TASK_ID = re.compile(r"^(TASK-\d+)")

# Commands that pass everywhere and would score a task the agent never touched.
_TOO_WEAK = ("make docs-lint", "make help")
# A G/W/T line often *starts* with a command and then keeps talking. Anything
# carrying prose markers is a sentence, not something a shell can run.
_PROSE_MARKERS = ("**", " the ", " and ", "(CLI)")
_MAX_COMMAND_CHARS = 120


@dataclass(frozen=True)
class Candidate:
    task_id: str
    prompt: str
    acceptance_command: str
    closing_commit: str
    starting_commit: str

    def to_yaml_block(self) -> str:
        prompt = self.prompt.replace('"', "'")
        return "\n".join(
            [
                f"- task_id: {self.task_id}",
                f'  prompt: "{prompt}"',
                f'  acceptance_command: "{self.acceptance_command}"',
                f"  starting_commit: {self.starting_commit}",
                f"  closing_commit: {self.closing_commit}",
                "  validated: false  # true only once the command is confirmed to",
                "                    # fail at starting_commit and pass after",
            ]
        )


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def closing_commit(task_id: str) -> str:
    """The last commit whose message names this task — the state after the work."""
    return _git("log", "--format=%H", "-1", f"--grep={task_id}", "--all")


def _known_make_targets() -> frozenset[str]:
    text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8", errors="replace")
    return frozenset(re.findall(r"^([a-z][a-z0-9-]*):", text, re.MULTILINE))


def _known_cos_subcommands() -> frozenset[str]:
    result = subprocess.run(
        ["uv", "run", "cos", "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS * 4,
    )
    return frozenset(re.findall(r"^\s{2,}([a-z][a-z0-9-]*)\s{2,}", result.stdout, re.MULTILINE))


def _is_flag_or_path(token: str) -> bool:
    return token.startswith("-") or "/" in token or token.endswith(".py")


def is_real_command(
    command: str, *, make_targets: frozenset[str], cos_commands: frozenset[str]
) -> bool:
    """Reject a sentence that merely opens with a command word.

    "cos init runs without --agent" matches the shape of a command and is prose.
    Checking the verb against what the repo actually exposes settles it without
    another round of regex guesswork.
    """
    tokens = command.split()
    if len(tokens) < 2:
        return False
    if tokens[0] == "make":
        return len(tokens) == 2 and tokens[1] in make_targets
    if tokens[0] == "cos":
        return tokens[1] in cos_commands and all(t.startswith("-") for t in tokens[2:])
    if tokens[0] == "pytest":
        return all(_is_flag_or_path(t) for t in tokens[1:])
    return tokens[0] == "uv" and tokens[1] == "run"


def acceptance_command(
    body: str, *, make_targets: frozenset[str], cos_commands: frozenset[str]
) -> str:
    match = _ACCEPTANCE_BLOCK.search(body)
    block = match.group(1) if match else ""
    for found in _RUNNABLE.findall(block):
        # A backticked command is followed by prose ("`cos doctor` runs clean") —
        # the backtick is where the command stops.
        command = found.split("`", 1)[0].strip().rstrip(".")
        if any(command.startswith(weak) for weak in _TOO_WEAK):
            continue
        if any(marker in command for marker in _PROSE_MARKERS):
            continue
        if len(command) > _MAX_COMMAND_CHARS:
            continue
        if not is_real_command(command, make_targets=make_targets, cos_commands=cos_commands):
            continue
        return command
    return ""


def mine(
    task_path: Path, body: str, *, make_targets: frozenset[str], cos_commands: frozenset[str]
) -> Candidate | None:
    task_id = _TASK_ID.match(task_path.name)
    outcome = _OUTCOME.search(body)
    command = acceptance_command(body, make_targets=make_targets, cos_commands=cos_commands)
    if not (task_id and outcome and command):
        return None

    closing = closing_commit(task_id.group(1))
    if not closing:
        return None
    parent = _git("rev-parse", f"{closing}^")
    if not parent:
        return None

    return Candidate(
        task_id=task_id.group(1),
        prompt=outcome.group(1).strip(),
        acceptance_command=command,
        closing_commit=closing[:12],
        starting_commit=parent[:12],
    )


def render(candidates: list[Candidate], *, scanned: int) -> str:
    header = [
        "# Ablation candidates — mined, NOT yet validated.",
        "# Spec: docs/engineering/ablation-protocol.md",
        f"# Mined from {scanned} closed tasks; {len(candidates)} carry a runnable acceptance.",
        "# Every entry needs a human to flip `validated` after confirming the command",
        "# fails at starting_commit. An unvalidated set scores work that was already done.",
        "candidates:",
    ]
    body = [
        "\n".join(f"  {line}" for line in candidate.to_yaml_block().splitlines())
        for candidate in candidates
    ]
    return "\n".join(header + body) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="write YAML here (default stdout)")
    args = parser.parse_args(argv)

    task_files = sorted(TASKS_DIR.glob("TASK-*.md"))
    if not task_files:
        print(f"[FAIL] no task files under {TASKS_DIR}", file=sys.stderr)
        return 1

    make_targets = _known_make_targets()
    cos_commands = _known_cos_subcommands()
    if not cos_commands:
        print(
            "[FAIL] could not enumerate cos subcommands — cannot validate mined commands",
            file=sys.stderr,
        )
        return 1
    print(
        f"[OK] {len(make_targets)} make targets, {len(cos_commands)} cos subcommands known",
        file=sys.stderr,
    )

    closed = 0
    candidates: list[Candidate] = []
    for index, path in enumerate(task_files, start=1):
        if index % PROGRESS_EVERY == 0:
            print(f"[{index}/{len(task_files)}] scanned", file=sys.stderr)
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"[FAIL] cannot read {path}: {exc}", file=sys.stderr)
            return 1
        if "status: complete" not in body:
            continue
        closed += 1
        found = mine(path, body, make_targets=make_targets, cos_commands=cos_commands)
        if found:
            candidates.append(found)

    payload = render(candidates, scanned=closed)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"[OK] wrote {args.out}", file=sys.stderr)
    else:
        print(payload)

    rejected = closed - len(candidates)
    print(
        f"[OK] {len(candidates)} candidates, {rejected} rejected (no runnable acceptance "
        f"or no traceable commit), from {closed} closed tasks — all need validation",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
