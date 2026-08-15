"""Measure the always-on context cost of a coding-os install, per project profile.

There is no single "coding-os costs N tokens" number, and publishing one would be
wrong in both directions: a WordPress consumer installs one stack rule, a polyglot
consumer installs several, and this meta-repo carries two generated registries no
consumer ever sees. So the profiler scaffolds real presets with the real `cos init`
and measures what the scaffold actually put in front of the model.

Always-on means loaded on every turn regardless of what the agent does: the root
instruction file plus the rules directory. Skills, commands and MCP tool schemas are
excluded on purpose — they are lazy-loaded, and counting them is the mistake that
turns a 13k-token layer into a fictional 200k one.

Spec: docs/engineering/context-budget.md

Usage:
    uv run python src/scripts/context_budget.py                 # representative span
    uv run python src/scripts/context_budget.py --json          # machine-readable
    uv run python src/scripts/context_budget.py --preset mern --preset tall
    uv run python src/scripts/context_budget.py --all-presets   # every preset (slow)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRESETS_DIR = REPO_ROOT / "src" / "templates" / "_presets"
CORE_RULES_DIR = REPO_ROOT / "src" / "core" / "rules"

INIT_TIMEOUT_SECONDS = 300
SECONDS_PER_SCAFFOLD_ESTIMATE = 20
CHARS_PER_TOKEN = 4
REFERENCE_CONTEXT_WINDOW_TOKENS = 200_000

# Representative span, smallest real profile to largest. The point of the default
# set is the spread, not an average.
DEFAULT_PRESETS = ("wordpress-cms", "jamstack", "mern", "ai-saas", "hexagonal-product")


class ScaffoldError(RuntimeError):
    """A `cos init` probe did not produce a measurable project."""


def estimate_tokens(character_count: int) -> int:
    return round(character_count / CHARS_PER_TOKEN)


@dataclass(frozen=True)
class Component:
    files: int
    characters: int

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.characters)


@dataclass(frozen=True)
class ProfileBudget:
    profile: str
    stacks: list[str]
    root_instructions: Component
    core_rules: Component
    stack_rules: Component
    skills_on_disk: int
    scaffold_files: int

    @property
    def total_characters(self) -> int:
        return (
            self.root_instructions.characters
            + self.core_rules.characters
            + self.stack_rules.characters
        )

    @property
    def total_tokens(self) -> int:
        return estimate_tokens(self.total_characters)

    @property
    def window_share_percent(self) -> float:
        return self.total_tokens / REFERENCE_CONTEXT_WINDOW_TOKENS * 100

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("root_instructions", "core_rules", "stack_rules"):
            payload[key]["tokens"] = getattr(self, key).tokens
        payload["total_characters"] = self.total_characters
        payload["total_tokens"] = self.total_tokens
        payload["window_share_percent"] = round(self.window_share_percent, 2)
        return payload


def available_presets() -> list[str]:
    return sorted(path.stem for path in PRESETS_DIR.glob("*.yaml"))


def preset_stacks(preset: str) -> list[str]:
    for line in (PRESETS_DIR / f"{preset}.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("stacks:"):
            declared = line.split(":", 1)[1].strip().strip("[]")
            return [item.strip() for item in declared.split(",") if item.strip()]
    return []


def scaffold(preset: str, parent: Path) -> Path:
    """Run the real `cos init` so the measurement reflects what a user gets."""
    project = parent / f"probe-{preset}"
    command = [
        "uv", "run", "--directory", str(REPO_ROOT), "cos", "init", "--yes",
        "--preset", preset, "--agent", "claude",
        "--project-dir", str(parent), "--name", project.name,
        "--no-register", "--no-index",
    ]  # fmt: skip
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=INIT_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise ScaffoldError(f"cos init timed out after {INIT_TIMEOUT_SECONDS}s") from exc
    if result.returncode != 0:
        raise ScaffoldError((result.stderr or result.stdout)[-400:].strip())
    if not project.is_dir():
        raise ScaffoldError(f"cos init reported success but {project} does not exist")
    return project


def _component(paths: list[Path]) -> Component:
    characters = 0
    for path in paths:
        try:
            characters += len(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            # A silent zero would report an unmeasurable tree as under budget.
            raise ScaffoldError(f"cannot read {path}: {exc}") from exc
    return Component(files=len(paths), characters=characters)


def measure(project: Path, *, profile: str, stacks: list[str]) -> ProfileBudget:
    """Split the always-on layer into the parts a reader can act on."""
    root_instructions = [path for path in (project / "CLAUDE.md",) if path.exists()]
    if not root_instructions:
        raise ScaffoldError(f"no CLAUDE.md in {project} — nothing always-on to measure")

    rules = sorted((project / ".claude" / "rules").glob("*.md"))
    core_rule_names = {path.name for path in CORE_RULES_DIR.glob("*.md")}
    skills_dir = project / ".claude" / "skills"

    return ProfileBudget(
        profile=profile,
        stacks=stacks,
        root_instructions=_component(root_instructions),
        core_rules=_component([path for path in rules if path.name in core_rule_names]),
        stack_rules=_component([path for path in rules if path.name not in core_rule_names]),
        skills_on_disk=len([path for path in skills_dir.glob("*") if path.is_dir()]),
        scaffold_files=sum(1 for path in project.rglob("*") if path.is_file()),
    )


def profile_budget(preset: str) -> ProfileBudget:
    with tempfile.TemporaryDirectory(prefix="cos-budget-") as parent:
        project = scaffold(preset, Path(parent))
        return measure(project, profile=preset, stacks=preset_stacks(preset))


def format_table(budgets: list[ProfileBudget]) -> str:
    header = (
        f"{'profile':<20} {'stacks':<24} {'root':>7} {'core':>7} {'stack':>7} "
        f"{'TOTAL':>8} {'of 200k':>8} {'skills':>7}"
    )
    lines = [header, "-" * len(header)]
    for budget in budgets:
        lines.append(
            f"{budget.profile:<20} {','.join(budget.stacks)[:24]:<24} "
            f"{budget.root_instructions.tokens:>7,} {budget.core_rules.tokens:>7,} "
            f"{budget.stack_rules.tokens:>7,} {budget.total_tokens:>8,} "
            f"{budget.window_share_percent:>7.1f}% {budget.skills_on_disk:>7}"
        )
    lines += [
        "",
        "Columns are estimated tokens. root = CLAUDE.md · core = stack-agnostic rules ·",
        "stack = per-stack rules. Skills sit on disk but load lazily and are NOT counted.",
        f"Estimate is characters/{CHARS_PER_TOKEN}, the same heuristic the graph envelopes use.",
    ]
    return "\n".join(lines)


def format_markdown_table(budgets: list[ProfileBudget]) -> str:
    lines = [
        "| Profile | Stacks | Root | Core rules | Stack rules | **Always-on total** | Share of a 200k window | Skills on disk (lazy) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for budget in budgets:
        lines.append(
            f"| `{budget.profile}` | {', '.join(budget.stacks) or '—'} "
            f"| {budget.root_instructions.tokens:,} | {budget.core_rules.tokens:,} "
            f"| {budget.stack_rules.tokens:,} | **{budget.total_tokens:,}** "
            f"| {budget.window_share_percent:.1f}% | {budget.skills_on_disk} |"
        )
    return "\n".join(lines)


def collect_budgets(presets: list[str]) -> tuple[list[ProfileBudget], list[str]]:
    budgets: list[ProfileBudget] = []
    failures: list[str] = []
    for index, preset in enumerate(presets, start=1):
        print(
            f"[{index}/{len(presets)}] {preset} "
            f"[..] cos init scaffold (~{SECONDS_PER_SCAFFOLD_ESTIMATE}s)",
            file=sys.stderr,
        )
        try:
            budgets.append(profile_budget(preset))
        except ScaffoldError as exc:
            print(f"[FAIL] {preset}: {exc}", file=sys.stderr)
            failures.append(preset)
    return budgets, failures


def _resolve_presets(args: argparse.Namespace) -> list[str]:
    if args.all_presets:
        return available_presets()
    return args.preset or list(DEFAULT_PRESETS)


def _render(budgets: list[ProfileBudget], args: argparse.Namespace) -> None:
    payload = json.dumps([budget.to_dict() for budget in budgets], indent=2)
    if args.out:
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"[OK] wrote {args.out}", file=sys.stderr)
    if args.json:
        print(payload)
    elif args.markdown:
        print(format_markdown_table(budgets))
    else:
        print(format_table(budgets))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", action="append", default=[], help="preset id (repeatable)")
    parser.add_argument("--all-presets", action="store_true", help="measure every preset")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--markdown", action="store_true", help="emit a markdown table")
    parser.add_argument("--out", type=Path, default=None, help="also write JSON to this path")
    args = parser.parse_args(argv)

    presets = _resolve_presets(args)
    known = set(available_presets())
    unknown = [preset for preset in presets if preset not in known]
    if unknown:
        print(f"[FAIL] unknown preset(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"[SKIP] nothing measured — available: {', '.join(sorted(known))}", file=sys.stderr)
        return 2

    started = time.monotonic()
    budgets, failures = collect_budgets(presets)
    elapsed = time.monotonic() - started

    if budgets:
        _render(budgets, args)

    marker = "[FAIL]" if failures else "[OK]"
    summary = f"{marker} {len(budgets)} measured, {len(failures)} failed in {elapsed:.1f}s"
    if failures:
        rerun = " ".join(f"--preset {preset}" for preset in failures)
        summary += f" — rerun: uv run python src/scripts/context_budget.py {rerun}"
    print(summary, file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
