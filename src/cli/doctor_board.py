"""cos doctor checks for board_os.

board.wip_within_caps      WIP state within cap (or flagged warning on active violation)
board.no_stale_tasks       no stale `in_progress` tasks
                           (stale = no Work Log append > 3 days OR elapsed > 2× appetite)
board.frontmatter_valid    frontmatter schema valid on every `docs/tasks/*.md`
board.index_synced         `docs/tasks.md` index (if present) in sync with frontmatter
board.git_tracked          every DB task row's `docs/tasks/*.md` is git-tracked & committed
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

SEV_PASS = "PASS"
SEV_WARN = "WARN"
SEV_FAIL = "FAIL"


_APPETITE_TO_HOURS: dict[str, float] = {
    "m": 1 / 60,
    "h": 1.0,
    "d": 24.0,
    "w": 24.0 * 7.0,
    "cy": 24.0 * 7.0 * 6.0,
}
_APPETITE_RE = re.compile(r"^(\d+)(m|h|d|w|cy)$")


def _appetite_hours(appetite: str | None) -> float | None:
    if not appetite:
        return None
    m = _APPETITE_RE.match(appetite)
    if not m:
        return None
    return int(m.group(1)) * _APPETITE_TO_HOURS[m.group(2)]


def _open_conn(state_dir: Path) -> sqlite3.Connection | None:
    if state_dir is None:
        return None
    db_path = Path(state_dir) / "coding-os.db"
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(str(db_path))
    except sqlite3.OperationalError:
        return None


def _check_wip_within_caps(report, conn: sqlite3.Connection, project: Path) -> None:
    from cli.doctor import CheckResult as _CR

    try:
        from board_os.config import load_config
        from board_os.workflow import check_wip
    except ImportError as exc:
        report.checks.append(
            _CR("board.wip_within_caps", SEV_WARN, f"board_os not importable: {exc}")
        )
        return

    try:
        cfg = load_config(project)
    except FileNotFoundError:
        report.checks.append(
            _CR(
                "board.wip_within_caps",
                SEV_WARN,
                "scrumban-config.yaml missing — run `cos board-config --init`",
            )
        )
        return
    except Exception as exc:
        report.checks.append(_CR("board.wip_within_caps", SEV_WARN, f"config parse: {exc}"))
        return

    state = check_wip(conn, cfg)
    if state.violations:
        parts = []
        for col in state.violations:
            parts.append(f"{col} {state.counts[col]}/{state.caps[col]}")
        report.checks.append(
            _CR(
                "board.wip_within_caps",
                SEV_WARN,
                f"WIP cap exceeded: {', '.join(parts)}",
                {"counts": state.counts, "caps": state.caps, "violations": list(state.violations)},
            )
        )
    else:
        report.checks.append(
            _CR(
                "board.wip_within_caps",
                SEV_PASS,
                f"WIP within caps (in_progress {state.counts.get('in_progress', 0)}/"
                f"{state.caps.get('in_progress')}, testing "
                f"{state.counts.get('testing', 0)}/{state.caps.get('testing')}, "
                f"emergency {state.counts.get('emergency', 0)}/"
                f"{state.caps.get('emergency')})",
            )
        )


def _check_no_stale_tasks(report, conn: sqlite3.Connection) -> None:
    from cli.doctor import CheckResult as _CR

    rows = conn.execute(
        "SELECT task_id, title, appetite, started_at, work_log_last_5 "
        "FROM tasks WHERE status = 'in_progress'"
    ).fetchall()
    if not rows:
        report.checks.append(_CR("board.no_stale_tasks", SEV_PASS, "no in_progress tasks"))
        return

    now = int(time.time())
    stale: list[dict[str, object]] = []
    for task_id, title, appetite, started_at, work_log_json in rows:
        reasons: list[str] = []
        try:
            log_lines = json.loads(work_log_json or "[]")
        except Exception:
            log_lines = []
        last_log_date = None
        if log_lines:
            m = re.search(r"\d{4}-\d{2}-\d{2}", log_lines[-1])
            if m:
                try:
                    from datetime import datetime, timezone

                    last_log_date = int(
                        datetime.fromisoformat(m.group(0)).replace(tzinfo=timezone.utc).timestamp()
                    )
                except Exception:
                    last_log_date = None
        log_age_hours = ((now - last_log_date) / 3600.0) if last_log_date else None
        if log_age_hours is None or log_age_hours > 72:
            reasons.append(
                f"Work Log {'never appended' if log_age_hours is None else f'{int(log_age_hours)}h old'}"
            )
        if started_at and appetite:
            elapsed_h = (now - int(started_at)) / 3600.0
            budget_h = _appetite_hours(appetite)
            if budget_h and elapsed_h > 2 * budget_h:
                reasons.append(f"elapsed {int(elapsed_h)}h > 2× appetite {appetite}")
        if reasons:
            stale.append(
                {
                    "task_id": task_id,
                    "title": title,
                    "reasons": reasons,
                }
            )

    if stale:
        summary = "; ".join(
            f"{s['task_id']} ({', '.join(s['reasons'])})"
            for s in stale  # type: ignore[arg-type]
        )
        report.checks.append(
            _CR(
                "board.no_stale_tasks",
                SEV_WARN,
                f"{len(stale)} stale in_progress task(s): {summary}",
                {"stale": stale},
            )
        )
    else:
        report.checks.append(
            _CR(
                "board.no_stale_tasks",
                SEV_PASS,
                f"all {len(rows)} in_progress task(s) have recent activity",
            )
        )


def _check_frontmatter_valid(report, project: Path) -> None:
    from cli.doctor import CheckResult as _CR

    try:
        from board_os.parser import parse_task
    except ImportError as exc:
        report.checks.append(
            _CR("board.frontmatter_valid", SEV_WARN, f"board_os parser unavailable: {exc}")
        )
        return

    tasks_dir = project / "docs" / "tasks"
    if not tasks_dir.exists():
        report.checks.append(
            _CR("board.frontmatter_valid", SEV_PASS, "no docs/tasks/ directory (empty board)")
        )
        return

    broken: list[dict[str, str]] = []
    legacy: list[str] = []
    total = 0
    for p in sorted(tasks_dir.glob("TASK-*.md")):
        total += 1
        content = p.read_text(encoding="utf-8")
        parsed = parse_task(content, path=p)
        if parsed is None:
            broken.append({"file": p.name, "reason": "unparseable"})
            continue
        if not parsed.is_lean:
            legacy.append(p.name)

    if broken:
        report.checks.append(
            _CR(
                "board.frontmatter_valid",
                SEV_FAIL,
                f"{len(broken)}/{total} task(s) unparseable",
                {"broken": broken},
            )
        )
        return
    if legacy:
        report.checks.append(
            _CR(
                "board.frontmatter_valid",
                SEV_WARN,
                f"{len(legacy)}/{total} task(s) still in legacy 12-section format "
                f"— run `cos task-migrate`",
                {"legacy_count": len(legacy)},
            )
        )
        return
    report.checks.append(
        _CR(
            "board.frontmatter_valid",
            SEV_PASS,
            f"all {total} task file(s) parse as lean frontmatter",
        )
    )


def _check_index_synced(report, project: Path) -> None:
    from cli.doctor import CheckResult as _CR

    index = project / "docs" / "tasks.md"
    tasks_dir = project / "docs" / "tasks"
    if not index.exists() or not tasks_dir.exists():
        report.checks.append(
            _CR("board.index_synced", SEV_PASS, "no legacy docs/tasks.md index to audit")
        )
        return

    index_text = index.read_text(encoding="utf-8")
    indexed_ids = set(re.findall(r"TASK-(?:[A-Z][A-Z0-9]*-)?\d+", index_text))
    file_ids: set[str] = set()
    for p in tasks_dir.glob("TASK-*.md"):
        m = re.match(r"(TASK-(?:[A-Z][A-Z0-9]*-)?\d+)", p.name)
        if m:
            file_ids.add(m.group(1))
    missing_from_index = file_ids - indexed_ids
    orphan_in_index = indexed_ids - file_ids

    if missing_from_index or orphan_in_index:
        report.checks.append(
            _CR(
                "board.index_synced",
                SEV_WARN,
                f"drift — {len(missing_from_index)} file(s) not in index, "
                f"{len(orphan_in_index)} index entry(ies) without files",
                {
                    "missing_from_index": sorted(missing_from_index),
                    "orphan_in_index": sorted(orphan_in_index),
                },
            )
        )
    else:
        report.checks.append(
            _CR(
                "board.index_synced",
                SEV_PASS,
                f"index and filesystem agree on {len(file_ids)} task(s)",
            )
        )


def _check_git_tracked(report, conn: sqlite3.Connection, project: Path) -> None:
    from board_os.git_coherence import detect_board_git_drift, task_rows_from_db
    from cli.doctor import CheckResult as _CR

    # Detection extracted to core/board_os/git_coherence.py so the
    # nightly cron task-filer + CI gate share ONE detector with this check.
    drift = detect_board_git_drift(project, task_rows_from_db(conn))
    if not drift.is_git_root:
        if drift.git_unavailable:
            report.checks.append(
                _CR(
                    "board.git_tracked",
                    SEV_WARN,
                    f"git unavailable — skipped ({drift.skip_reason})",
                )
            )
        else:
            report.checks.append(
                _CR("board.git_tracked", SEV_PASS, "project is not a git work-tree root — skipped")
            )
        return
    if drift.skip_reason:  # real repo, but git status failed
        report.checks.append(
            _CR("board.git_tracked", SEV_WARN, f"git status failed — skipped ({drift.skip_reason})")
        )
        return
    if drift.checked == 0:
        report.checks.append(_CR("board.git_tracked", SEV_PASS, "no task rows to check"))
        return
    if drift.has_drift:
        report.checks.append(
            _CR(
                "board.git_tracked",
                SEV_WARN,
                drift.summary(),
                {
                    "untracked": sorted(drift.untracked),
                    "modified": sorted(drift.modified),
                    "missing_file": sorted(drift.missing),
                },
            )
        )
    else:
        report.checks.append(
            _CR(
                "board.git_tracked",
                SEV_PASS,
                f"all {drift.checked} task file(s) tracked & committed",
            )
        )


def run_board_checks(report, project: Path, state_dir: Path) -> None:
    """Entry point called from src/cli/doctor.py::run_doctor."""
    from cli.doctor import CheckResult as _CR

    conn = _open_conn(state_dir)
    if conn is None:
        report.checks.append(
            _CR(
                "board.wip_within_caps",
                SEV_WARN,
                "board DB not reachable — skipping board.wip_within_caps-board.index_synced",
            )
        )
        return

    try:
        _check_wip_within_caps(report, conn, project)
        _check_no_stale_tasks(report, conn)
        _check_frontmatter_valid(report, project)
        _check_index_synced(report, project)
        _check_git_tracked(report, conn, project)
    finally:
        conn.close()


__all__ = ["run_board_checks"]
