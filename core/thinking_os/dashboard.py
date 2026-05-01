#!/usr/bin/env python3
"""
Thinking OS — Terminal dashboard (TASK-149).

Prints a text-based dashboard showing system health:
  - Pattern count + confidence distribution
  - Model success rates
  - Domain failure hotspots
  - Observation stats
  - DB size

Run via `make thinking_os-stats`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import DEFAULT_DB_PATH, get_connection, get_db_stats, get_schema_version


def _format_size(bytes_: int) -> str:
    """Format bytes to human-readable size."""
    if bytes_ < 1024:
        return f"{bytes_} B"
    elif bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.1f} KB"
    else:
        return f"{bytes_ / (1024 * 1024):.1f} MB"


def _bar(value: int, max_value: int, width: int = 20) -> str:
    """Render a text bar chart."""
    if max_value <= 0:
        return ""
    filled = min(width, int(value / max_value * width))
    return "█" * filled + "░" * (width - filled)


def generate_dashboard(db_path: str | Path | None = None) -> str:
    """Generate the full dashboard text.

    Args:
        db_path: Path to coding-os.db. Defaults to DEFAULT_DB_PATH.

    Returns:
        Formatted dashboard string.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        return (
            "╔══════════════════════════════════════════════════╗\n"
            "║  Thinking OS — No DB Found                      ║\n"
            "╚══════════════════════════════════════════════════╝\n"
            "\n"
            "No coding-os.db found.\n"
            "Run tasks with outcome tracking to start collecting data."
        )

    conn = get_connection(path)
    try:
        lines: list[str] = []
        stats = get_db_stats(conn)

        lines.append("╔══════════════════════════════════════════════════╗")
        lines.append("║  Thinking OS — Dashboard                        ║")
        lines.append("╚══════════════════════════════════════════════════╝")
        lines.append("")

        # --- Section 1: Overview ---
        lines.append("── Overview ───────────────────────────────────────")
        lines.append(f"  Schema version : v{stats['schema_version']}")
        lines.append(f"  FTS5 available : {'yes' if stats['fts5_available'] else 'no'}")
        lines.append(f"  DB size        : {_format_size(stats['db_size_bytes'])}")
        lines.append(f"  Patterns       : {stats['tables']['learned_patterns']}")
        lines.append(f"  Observations   : {stats['tables']['observations']}")
        lines.append(f"  Task outcomes  : {stats['tables']['task_outcomes']}")
        lines.append(f"  Agent metrics  : {stats['tables']['agent_metrics']}")
        lines.append(f"  Experiments    : {stats['tables']['experiment_log']}")
        lines.append(f"  Sessions       : {stats['tables']['session_summaries']}")
        lines.append("")

        # --- Section 2: Confidence Distribution ---
        lines.append("── Confidence Distribution ────────────────────────")
        buckets = [
            ("archived (≤0.1)", "confidence <= 0.1"),
            ("weak (0.1-0.3)", "confidence > 0.1 AND confidence <= 0.3"),
            ("emerging (0.3-0.5)", "confidence > 0.3 AND confidence <= 0.5"),
            ("moderate (0.5-0.7)", "confidence > 0.5 AND confidence <= 0.7"),
            ("strong (0.7-0.9)", "confidence > 0.7 AND confidence <= 0.9"),
            ("validated (0.9+)", "confidence > 0.9"),
        ]
        total_patterns = stats["tables"]["learned_patterns"] or 0
        for label, condition in buckets:
            count = conn.execute(
                f"SELECT COUNT(*) FROM learned_patterns WHERE {condition}"  # noqa: S608 — conditions are hardcoded
            ).fetchone()[0]
            bar = _bar(count, max(total_patterns, 1))
            lines.append(f"  {label:20s} {bar} {count}")
        lines.append("")

        # --- Section 3: Model Success Rates ---
        lines.append("── Model Success Rates ────────────────────────────")
        model_rows = conn.execute(
            "SELECT model, "
            "SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS wins, "
            "COUNT(*) AS total "
            "FROM task_outcomes WHERE model IS NOT NULL "
            "GROUP BY model ORDER BY total DESC"
        ).fetchall()
        if model_rows:
            for row in model_rows:
                d = dict(row)
                rate = d["wins"] / d["total"] if d["total"] > 0 else 0
                bar = _bar(int(rate * 100), 100, 15)
                lines.append(f"  {d['model'] or 'unknown':12s} {bar} {rate:5.0%} ({d['wins']}/{d['total']})")
        else:
            lines.append("  (no data)")
        lines.append("")

        # --- Section 4: Domain Failure Hotspots ---
        lines.append("── Domain Failure Hotspots ────────────────────────")
        domain_rows = conn.execute(
            "SELECT domain, "
            "SUM(CASE WHEN outcome = 'rework' THEN 1 ELSE 0 END) AS reworks, "
            "COUNT(*) AS total "
            "FROM task_outcomes "
            "GROUP BY domain ORDER BY reworks DESC"
        ).fetchall()
        if domain_rows:
            for row in domain_rows:
                d = dict(row)
                rate = d["reworks"] / d["total"] if d["total"] > 0 else 0
                indicator = "🔴" if rate > 0.3 else "🟡" if rate > 0.15 else "🟢"
                lines.append(
                    f"  {indicator} {d['domain'] or 'unknown':12s} "
                    f"{d['reworks']}/{d['total']} rework ({rate:.0%})"
                )
        else:
            lines.append("  (no data)")
        lines.append("")

        # --- Section 5: Recent Experiments ---
        lines.append("── Recent Experiments (last 5) ────────────────────")
        exp_rows = conn.execute(
            "SELECT task_id, hypothesis, outcome FROM experiment_log "
            "ORDER BY created_at DESC LIMIT 5"
        ).fetchall()
        if exp_rows:
            for row in exp_rows:
                d = dict(row)
                icon = "✓" if d["outcome"] == "pass" else "✗" if d["outcome"] == "fail" else "?"
                hyp = (d["hypothesis"] or "")[:50]
                lines.append(f"  [{icon}] {d['task_id']}: {hyp}")
        else:
            lines.append("  (no experiments)")
        lines.append("")

        return "\n".join(lines)

    finally:
        conn.close()


def main() -> None:
    print(generate_dashboard())


if __name__ == "__main__":
    main()
