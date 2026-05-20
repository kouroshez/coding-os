#!/usr/bin/env python3
"""
Thinking OS — Bootstrap task_outcomes from docs/tasks.md (one-time).

Reads completed tasks ([x]) from the task index, infers domain/type/complexity,
and inserts into task_outcomes. Then runs learn_extract to discover patterns.

Usage:
    python3 core/thinking_os/bootstrap_outcomes.py          # run
    python3 core/thinking_os/bootstrap_outcomes.py --dry-run # preview
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection

TASKS_FILE = Path("docs/tasks.md")

DOMAIN_MAP = {
    "BACKEND": "BACKEND",
    "FRONTEND": "FRONTEND",
    "DOCS": "DOCS",
    "INFRA": "INFRA",
    "DESIGN": "FRONTEND",
    "SEO": "FRONTEND",
    "SECURITY": "BACKEND",
    "DEVOPS": "INFRA",
    "CI": "INFRA",
    "CONTENT": "DOCS",
    "AUTH": "BACKEND",
    "PAYMENT": "BACKEND",
    "COMMERCE": "BACKEND",
    "CATALOG": "BACKEND",
    "DOWNLOADS": "BACKEND",
    "NOTIFICATIONS": "BACKEND",
    "ANALYTICS": "BACKEND",
}

TYPE_HINTS = {
    "scaffold": "feat",
    "implement": "feat",
    "add": "feat",
    "create": "feat",
    "complete": "feat",
    "setup": "feat",
    "build": "feat",
    "wire": "feat",
    "integrate": "feat",
    "fix": "fix",
    "repair": "fix",
    "resolve": "fix",
    "patch": "fix",
    "hotfix": "fix",
    "refactor": "refactor",
    "restructure": "refactor",
    "reorganize": "refactor",
    "audit": "docs",
    "document": "docs",
    "write": "docs",
    "lock": "docs",
    "test": "test",
    "harden": "refactor",
    "optimize": "refactor",
}


def _detect_domain(title: str) -> str:
    """Infer domain from task title [DOMAIN] tag or keywords."""
    m = re.search(r"\[([A-Z]+)\]", title)
    if m:
        tag = m.group(1)
        return DOMAIN_MAP.get(tag, "INFRA")

    title_upper = title.upper()
    for keyword, domain in DOMAIN_MAP.items():
        if keyword in title_upper:
            return domain
    return "INFRA"


def _detect_type(title: str) -> str:
    """Infer task type from title keywords."""
    title_lower = title.lower()
    for keyword, ttype in TYPE_HINTS.items():
        if keyword in title_lower:
            return ttype
    return "feat"


def _estimate_complexity(title: str) -> tuple[str, int]:
    """Estimate complexity from title. Returns (classification, dimensions)."""
    title_lower = title.lower()
    complex_keywords = [
        "architecture",
        "system",
        "orchestration",
        "refactor",
        "migration",
        "security",
    ]
    simple_keywords = ["fix", "patch", "rename", "typo", "lint", "format"]

    if any(k in title_lower for k in simple_keywords):
        return "CLEAR", 1
    if any(k in title_lower for k in complex_keywords):
        return "COMPLICATED", 3
    return "COMPLICATED", 2


def bootstrap(dry_run: bool = False) -> dict:
    """Parse completed tasks and insert into task_outcomes."""
    if not TASKS_FILE.exists():
        return {"error": f"{TASKS_FILE} not found"}

    conn = get_connection(DEFAULT_DB_PATH)
    try:
        # Get existing task IDs to avoid duplicates
        existing = {r[0] for r in conn.execute("SELECT task_id FROM task_outcomes").fetchall()}

        text = TASKS_FILE.read_text()
        pattern = re.compile(r"^- \[x\] (TASK-\d+):\s*(.+)$", re.MULTILINE)
        matches = pattern.findall(text)

        inserted = 0
        skipped = 0

        for task_id, title in matches:
            if task_id in existing:
                skipped += 1
                continue

            domain = _detect_domain(title)
            task_type = _detect_type(title)
            complexity, dims = _estimate_complexity(title)

            if not dry_run:
                conn.execute(
                    "INSERT INTO task_outcomes "
                    "(task_id, type, domain, complexity, dimensions, outcome) "
                    "VALUES (?, ?, ?, ?, ?, 'success')",
                    (task_id, task_type, domain, complexity, dims),
                )
            inserted += 1

        if not dry_run:
            conn.commit()

        # Run learn_extract after bootstrap
        extracted = []
        if not dry_run and inserted > 0:
            try:
                from tools.learning import learn_extract

                result = learn_extract(conn, min_occurrences=2)
                extracted = result.get("extracted", [])
            except Exception as e:
                extracted = [{"error": str(e)}]

        return {
            "status": "ok",
            "total_completed": len(matches),
            "inserted": inserted,
            "skipped_existing": skipped,
            "patterns_extracted": len(extracted),
            "patterns": extracted,
        }
    finally:
        conn.close()


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("DRY RUN — no changes")

    result = bootstrap(dry_run=dry_run)
    print("Bootstrap results:")
    for k, v in result.items():
        if k != "patterns":
            print(f"  {k}: {v}")

    if result.get("patterns"):
        print("\nExtracted patterns:")
        for p in result["patterns"]:
            if "error" in p:
                print(f"  ERROR: {p['error']}")
            else:
                print(
                    f"  [{p.get('action', '?')}] {p.get('pattern', '?')} (conf: {p.get('confidence', '?')})"
                )


if __name__ == "__main__":
    main()
