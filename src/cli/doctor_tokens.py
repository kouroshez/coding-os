"""Token-usage audit over agent transcript JSONLs (cos doctor --tokens).

Reads the Claude Code transcript directory for a project, sums the per-turn
``usage`` records, and reports burn-rate diagnostics: weighted totals, average
context per turn, marathon sessions, and the session-start baseline. Spec:
docs/playbooks/doctor-checks.md § Tokens.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)

# Approximate usage-limit weighting: output is ~5x input, cache writes ~1.25x,
# cache reads ~0.1x. Good enough to rank levers; not a billing statement.
WEIGHT_INPUT = 1.0
WEIGHT_OUTPUT = 5.0
WEIGHT_CACHE_WRITE = 1.25
WEIGHT_CACHE_READ = 0.1

DEFAULT_CONTEXT_BUDGET_TOKENS = 200_000
MARATHON_TURNS_THRESHOLD = 1_000
TOP_SESSIONS_SHOWN = 5


def transcript_dir_for(project: Path) -> Path:
    slug = re.sub(r"[/.]", "-", str(project.resolve()))
    return Path.home() / ".claude" / "projects" / slug


def _scan_file(path: Path) -> dict[str, Any]:
    totals: Counter[str] = Counter()
    turns = 0
    first_turn_context = 0
    with path.open(errors="ignore") as handle:
        for line in handle:
            if '"usage"' not in line:
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            usage = (record.get("message") or {}).get("usage") or {}
            if not usage:
                continue
            turns += 1
            for key in USAGE_KEYS:
                totals[key] += usage.get(key) or 0
            if turns == 1:
                first_turn_context = sum(
                    usage.get(key) or 0 for key in USAGE_KEYS if key != "output_tokens"
                )
    return {
        "name": path.stem,
        "is_subagent": path.parent.name == "subagents",
        "turns": turns,
        "first_turn_context": first_turn_context,
        **{key: totals[key] for key in USAGE_KEYS},
    }


def weighted_equivalent(totals: dict[str, int]) -> float:
    return (
        WEIGHT_INPUT * totals.get("input_tokens", 0)
        + WEIGHT_OUTPUT * totals.get("output_tokens", 0)
        + WEIGHT_CACHE_WRITE * totals.get("cache_creation_input_tokens", 0)
        + WEIGHT_CACHE_READ * totals.get("cache_read_input_tokens", 0)
    )


def analyze_tokens(
    project: Path,
    *,
    days: int = 7,
    transcripts_dir: Path | None = None,
) -> dict[str, Any]:
    transcripts = transcripts_dir or transcript_dir_for(project)
    if not transcripts.is_dir():
        return {"transcripts_dir": str(transcripts), "found": False}

    cutoff = time.time() - days * 86_400
    sessions: list[dict[str, Any]] = []
    for path in transcripts.rglob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff:
                continue
            sessions.append(_scan_file(path))
        except OSError:
            continue
    sessions = [s for s in sessions if s["turns"] > 0]

    totals: Counter[str] = Counter()
    for session in sessions:
        for key in USAGE_KEYS:
            totals[key] += session[key]
    total_turns = sum(s["turns"] for s in sessions)

    main_baselines = sorted(
        s["first_turn_context"]
        for s in sessions
        if not s["is_subagent"] and s["first_turn_context"]
    )
    median_baseline = main_baselines[len(main_baselines) // 2] if main_baselines else 0
    avg_context = totals["cache_read_input_tokens"] // total_turns if total_turns else 0

    top_sessions = sorted(sessions, key=lambda s: s["cache_read_input_tokens"], reverse=True)
    context_budget = int(os.environ.get("COS_CONTEXT_BUDGET", DEFAULT_CONTEXT_BUDGET_TOKENS))

    return {
        "transcripts_dir": str(transcripts),
        "found": True,
        "days": days,
        "sessions": len(sessions),
        "subagent_sessions": sum(1 for s in sessions if s["is_subagent"]),
        "turns": total_turns,
        "totals": {key: totals[key] for key in USAGE_KEYS},
        "weighted_input_equivalent": int(weighted_equivalent(totals)),
        "avg_context_per_turn": avg_context,
        "median_session_baseline": median_baseline,
        "context_budget": context_budget,
        "over_budget": avg_context > context_budget,
        "marathon_sessions": [
            {"name": s["name"], "turns": s["turns"]}
            for s in sessions
            if s["turns"] >= MARATHON_TURNS_THRESHOLD
        ],
        "top_sessions": [
            {
                "name": s["name"],
                "turns": s["turns"],
                "cache_read": s["cache_read_input_tokens"],
                "output": s["output_tokens"],
                "subagent": s["is_subagent"],
            }
            for s in top_sessions[:TOP_SESSIONS_SHOWN]
        ],
    }


def format_tokens_text(report: dict[str, Any]) -> str:
    if not report["found"]:
        return (
            f"no transcript directory at {report['transcripts_dir']} — "
            "nothing to analyze (transcripts are agent-runtime-specific)."
        )
    lines = [
        f"Token usage — last {report['days']}d "
        f"({report['sessions']} sessions, {report['subagent_sessions']} subagents, "
        f"{report['turns']:,} API turns)",
        "",
    ]
    for key in USAGE_KEYS:
        lines.append(f"  {key:35s} {report['totals'][key]:>16,}")
    lines += [
        "",
        f"  weighted input-equivalent           {report['weighted_input_equivalent']:>16,}",
        f"  avg context per turn                {report['avg_context_per_turn']:>16,}",
        f"  median session baseline             {report['median_session_baseline']:>16,}",
        "",
    ]
    budget = report["context_budget"]
    if report["over_budget"]:
        lines.append(
            f"  WARN: avg context/turn exceeds budget ({budget:,}). "
            "Use /compact mid-task; /clear between unrelated tasks to cut burn."
        )
    else:
        lines.append(f"  OK: avg context/turn within budget ({budget:,}).")
    if report["marathon_sessions"]:
        names = ", ".join(
            f"{m['name'][:8]}({m['turns']} turns)" for m in report["marathon_sessions"]
        )
        lines.append(f"  WARN: marathon sessions (>= {MARATHON_TURNS_THRESHOLD} turns): {names}")
    if report["top_sessions"]:
        lines += ["", "  top sessions by cache-read burn:"]
        for s in report["top_sessions"]:
            tag = " [subagent]" if s["subagent"] else ""
            lines.append(
                f"    {s['cache_read']:>16,} cache-read  {s['turns']:>5} turns  "
                f"out={s['output']:>12,}  {s['name'][:8]}{tag}"
            )
    return "\n".join(lines)
