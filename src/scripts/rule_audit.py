"""Rank the always-on rules by what they actually prevent, per token they occupy.

Instruction density is not free: the published evidence is that adherence falls as
the number of concurrent instructions rises, with a bias toward whatever appears
first. So "28 critical rules is fine" needs measuring, not asserting.

Blocks come from the agent transcripts rather than the hook log, because the hook
log is capped at 500 lines while the transcripts hold months. Every hook BLOCK
appears in a transcript as a tool error naming the hook script, which makes the
count durable and re-derivable by anyone with the same session history.

A rule with no enforcing hook is not automatically waste — it is a *convention*,
whose only mechanism is the model reading it. Those are exactly the rules that
instruction-density research says degrade first, so the report names them.

Spec: docs/engineering/context-budget.md

Usage:
    uv run python src/scripts/rule_audit.py
    uv run python src/scripts/rule_audit.py --days 90 --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_DIR = REPO_ROOT / ".claude" / "rules"
CHARS_PER_TOKEN = 4
DEFAULT_WINDOW_DAYS = 180
SECONDS_PER_DAY = 86_400

_HOOK_IN_ERROR = re.compile(r"hooks/([a-z0-9][a-z0-9-]*)\.sh")

# Which hooks enforce which rule. Curated on purpose: no static analysis can tell
# you that `test-governor` exists to serve test-discipline. A rule missing from
# this map is an error, not a default — adding a rule must state its mechanism.
ENFORCED_BY: dict[str, tuple[str, ...]] = {
    "anti-overengineering.md": ("block-bad-patterns",),
    "api-contract-discipline.md": (),
    "dimension-registry.md": (),
    "git-workflow.md": ("branch-guard", "enforce-commit-message", "block-secrets"),
    "memory.md": ("enforce-memory-check",),
    "model-routing.md": ("nudge-model-routing",),
    "skill-enforcement.md": ("enforce-skill",),
    "test-discipline.md": ("enforce-verify", "test-governor"),
    "thinking_os.md": ("thinking_os-gate", "enforce-zoom"),
    "transparency-banner.md": (),
    "meta-graph-first.md": ("enforce-graph-context", "enforce-rename-plan"),
    "meta-hook-author.md": (),
    "meta-mcp-tool-author.md": (),
    "meta-meta-engineering.md": (),
}

ENFORCED = "enforced"
DORMANT = "dormant"
CONVENTION = "convention"


class AuditError(RuntimeError):
    """The audit cannot produce a trustworthy number."""


@dataclass(frozen=True)
class BlockStats:
    count: int
    last_seen_epoch: float | None

    def days_since(self, now: float) -> float | None:
        if self.last_seen_epoch is None:
            return None
        return (now - self.last_seen_epoch) / SECONDS_PER_DAY


@dataclass(frozen=True)
class RuleRow:
    rule: str
    tokens: int
    hooks: list[str]
    blocks: int
    days_since_last_block: float | None
    verdict: str

    @property
    def blocks_per_thousand_tokens(self) -> float:
        return self.blocks / (self.tokens / 1000) if self.tokens else 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blocks_per_thousand_tokens"] = round(self.blocks_per_thousand_tokens, 2)
        return payload


def transcript_dir(project: Path) -> Path:
    slug = re.sub(r"[/.]", "-", str(project.resolve()))
    return Path.home() / ".claude" / "projects" / slug


def scan_blocks(transcripts: Path, *, since_epoch: float) -> tuple[dict[str, BlockStats], int]:
    """Count hook blocks per hook script across the session transcripts."""
    if not transcripts.is_dir():
        raise AuditError(f"no transcript directory at {transcripts}")

    counts: Counter[str] = Counter()
    last_seen: dict[str, float] = {}
    sessions = 0
    for path in transcripts.rglob("*.jsonl"):
        try:
            modified = path.stat().st_mtime
            if modified < since_epoch:
                continue
            sessions += 1
            with path.open(errors="ignore") as handle:
                for line in handle:
                    if "BLOCKED" not in line and "hook error" not in line:
                        continue
                    for hook in set(_HOOK_IN_ERROR.findall(line)):
                        counts[hook] += 1
                        last_seen[hook] = max(last_seen.get(hook, 0.0), modified)
        except OSError as exc:
            raise AuditError(f"cannot read {path}: {exc}") from exc

    stats = {
        hook: BlockStats(count=n, last_seen_epoch=last_seen.get(hook)) for hook, n in counts.items()
    }
    return stats, sessions


def _verdict(hooks: tuple[str, ...], blocks: int) -> str:
    if not hooks:
        return CONVENTION
    return ENFORCED if blocks else DORMANT


def audit_rules(stats: dict[str, BlockStats], *, now: float) -> list[RuleRow]:
    rows = []
    for path in sorted(RULES_DIR.glob("*.md")):
        if path.name not in ENFORCED_BY:
            raise AuditError(
                f"{path.name} has no entry in ENFORCED_BY — name the hook that enforces it, "
                f"or record it as a convention with an empty tuple"
            )
        hooks = ENFORCED_BY[path.name]
        blocks = sum(stats[h].count for h in hooks if h in stats)
        last = [stats[h].last_seen_epoch for h in hooks if h in stats and stats[h].last_seen_epoch]
        rows.append(
            RuleRow(
                rule=path.name,
                tokens=round(
                    len(path.read_text(encoding="utf-8", errors="replace")) / CHARS_PER_TOKEN
                ),
                hooks=list(hooks),
                blocks=blocks,
                days_since_last_block=round((now - max(last)) / SECONDS_PER_DAY, 1)
                if last
                else None,
                verdict=_verdict(hooks, blocks),
            )
        )
    rows.sort(key=lambda row: (-row.blocks_per_thousand_tokens, row.rule))
    return rows


def format_table(rows: list[RuleRow], *, sessions: int, days: int) -> str:
    header = f"{'rule':30} {'tokens':>7} {'blocks':>7} {'per 1k':>7} {'last':>7}  verdict"
    lines = [
        f"Always-on rules, {sessions} sessions in the last {days} days",
        "",
        header,
        "-" * len(header),
    ]
    for row in rows:
        last = (
            f"{row.days_since_last_block:.0f}d"
            if row.days_since_last_block is not None
            else "never"
        )
        lines.append(
            f"{row.rule:30} {row.tokens:>7,} {row.blocks:>7,} "
            f"{row.blocks_per_thousand_tokens:>7.1f} {last:>7}  {row.verdict}"
        )

    total = sum(row.tokens for row in rows)
    conventions = [row for row in rows if row.verdict == CONVENTION]
    dormant = [row for row in rows if row.verdict == DORMANT]
    lines += [
        "-" * len(header),
        f"{'TOTAL':30} {total:>7,}",
        "",
        f"{len(conventions)} rules are conventions with no enforcing hook "
        f"({sum(r.tokens for r in conventions):,} tokens): "
        f"{', '.join(r.rule for r in conventions) or 'none'}",
        f"{len(dormant)} rules have a hook that never fired in the window "
        f"({sum(r.tokens for r in dormant):,} tokens): "
        f"{', '.join(r.rule for r in dormant) or 'none'}",
        "",
        "A convention is not automatically waste — but it is carried entirely by the",
        "model's attention, which is the budget instruction density spends first.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_WINDOW_DAYS, help="lookback window")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument("--project", type=Path, default=REPO_ROOT, help="project to audit")
    args = parser.parse_args(argv)

    now = time.time()
    try:
        stats, sessions = scan_blocks(
            transcript_dir(args.project), since_epoch=now - args.days * SECONDS_PER_DAY
        )
        rows = audit_rules(stats, now=now)
    except AuditError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps([row.to_dict() for row in rows], indent=2))
    else:
        print(format_table(rows, sessions=sessions, days=args.days))

    # Piped stdout is block-buffered; without this the summary jumps the table.
    sys.stdout.flush()
    total_blocks = sum(row.blocks for row in rows)
    print(
        f"[OK] {len(rows)} rules audited over {sessions} sessions, {total_blocks:,} attributed blocks",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
