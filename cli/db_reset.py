"""cos db-reset — wipe coding-os databases with backup + safety guards.

Destructive command. Default dry-run; --confirm required to execute.
Always backs up before deleting. Spec: docs/playbooks/db-reset.md
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import click

logger = logging.getLogger("coding_os.cli.db_reset")

STATE_DIR = ".coding-os"
DB_FILE = "coding-os.db"
KUZU_DIR = "graph_os.kuzu"
KUZU_BAK_DIR = "graph_os.kuzu.empty-bak"
AGENT_DIRS = ("claude", "codex", "cursor", "amb", "bt")


def _bytes(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _path_size(p: Path) -> int:
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for sub in p.rglob("*"):
        if sub.is_file():
            try:
                total += sub.stat().st_size
            except OSError as exc:
                logger.debug("stat skipped for %s: %s", sub, exc)
    return total


def _print_extractor_latency(db_path: Path) -> None:
    """Show median + p95 duration_ms per extractor_chain. Skips when column missing."""
    if not db_path.exists():
        return
    try:
        with sqlite3.connect(db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(file_index_state)").fetchall()}
            if "duration_ms" not in cols:
                return
            rows = conn.execute(
                "SELECT extractor_chain, COUNT(*) AS n, "
                "       AVG(duration_ms), MAX(duration_ms) "
                "FROM file_index_state "
                "WHERE duration_ms IS NOT NULL "
                "GROUP BY extractor_chain "
                "ORDER BY n DESC"
            ).fetchall()
    except sqlite3.Error:
        return
    if not rows:
        return
    click.echo(f"{'Extractor':<28s} {'files':>6s} {'avg(ms)':>10s} {'max(ms)':>10s}")
    click.echo("-" * 58)
    for chain, n, avg, mx in rows:
        click.echo(f"{(chain or '(none)')[:28]:<28s} {n:>6d} {(avg or 0):>10.1f} {(mx or 0):>10d}")
    click.echo("")


def _table_summary(db_path: Path) -> list[tuple[str, int]]:
    if not db_path.exists():
        return []
    rows: list[tuple[str, int]] = []
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '%_fts%' AND name NOT LIKE '%_idx%' "
                "ORDER BY name;"
            )
            tables = [r[0] for r in cur.fetchall()]
            for t in tables:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {t};").fetchone()[0]
                except sqlite3.Error as exc:
                    logger.debug("row-count failed for %s: %s", t, exc)
                    cnt = -1
                rows.append((t, cnt))
    except sqlite3.Error as exc:
        logger.debug("table summary failed: %s", exc)
    return rows


def register(cli: click.Group) -> None:
    """Attach `cos db-stats` and `cos db-reset` to the root CLI."""

    @cli.command("db-stats")
    @click.option("--project-dir", "-d", default=".", help="Project directory")
    def db_stats(project_dir: str) -> None:
        """Show row counts per table + total DB size."""
        project = Path(project_dir).resolve()
        state = project / STATE_DIR
        db_path = state / DB_FILE
        kuzu = state / KUZU_DIR

        click.echo(f"SQLite DB : {db_path}")
        click.echo(f"  exists  : {db_path.exists()}")
        if db_path.exists():
            click.echo(f"  size    : {_bytes(db_path.stat().st_size)}")
        click.echo(f"Kuzu graph: {kuzu}")
        click.echo(f"  exists  : {kuzu.exists()}")
        if kuzu.exists():
            click.echo(f"  size    : {_bytes(_path_size(kuzu))}")
        click.echo("")

        # Per-extractor latency telemetry (v28+).
        _print_extractor_latency(db_path)

        rows = _table_summary(db_path)
        if not rows:
            click.echo("(no tables)")
            return

        click.echo(f"{'Table':<35s} {'Rows':>10s}")
        click.echo("-" * 47)
        for name, cnt in rows:
            click.echo(f"{name:<35s} {cnt:>10d}")
        click.echo("-" * 47)
        click.echo(f"{'Total tables':<35s} {len(rows):>10d}")

    @cli.command("db-reset")
    @click.option("--project-dir", "-d", default=".", help="Project directory")
    @click.option("--confirm", is_flag=True, default=False, help="Actually perform the reset (default is dry-run)")
    @click.option("--wipe-sessions", is_flag=True, default=False, help="Also delete .coding-os/<agent>/ (gates, traces, markers)")
    @click.option("--wipe-tasks", is_flag=True, default=False, help="Also delete docs/tasks/TASK-*.md (use with care — disk SSOT)")
    @click.option("--no-backup", is_flag=True, default=False, help="Skip backup (NOT recommended)")
    @click.option("--no-reindex", is_flag=True, default=False, help="Do not run cos graph-reindex after reset")
    def db_reset(
        project_dir: str,
        confirm: bool,
        wipe_sessions: bool,
        wipe_tasks: bool,
        no_backup: bool,
        no_reindex: bool,
    ) -> None:
        """Wipe coding-os DB + graph. Default: dry-run report; pass --confirm to execute."""
        project = Path(project_dir).resolve()
        state = project / STATE_DIR
        db_path = state / DB_FILE
        kuzu = state / KUZU_DIR
        kuzu_bak = state / KUZU_BAK_DIR

        targets: list[tuple[str, Path, int]] = []
        if db_path.exists():
            targets.append(("SQLite DB", db_path, db_path.stat().st_size))
        if kuzu.exists():
            targets.append(("Kuzu graph", kuzu, _path_size(kuzu)))
        if wipe_sessions:
            for agent in AGENT_DIRS:
                ad = state / agent
                if ad.exists():
                    targets.append((f"agent state ({agent})", ad, _path_size(ad)))
        if wipe_tasks:
            tasks_dir = project / "docs" / "tasks"
            if tasks_dir.exists():
                for f in sorted(tasks_dir.glob("TASK-*.md")):
                    targets.append(("task file", f, f.stat().st_size))

        if not targets:
            click.echo("Nothing to wipe — DB already empty.")
            return

        click.echo("Reset targets:")
        total = 0
        for label, p, size in targets:
            click.echo(f"  {label:<24s} {str(p):<60s} {_bytes(size)}")
            total += size
        click.echo(f"  {'TOTAL':<24s} {'':<60s} {_bytes(total)}")
        click.echo("")

        rows = _table_summary(db_path)
        if rows:
            populated = [r for r in rows if r[1] > 0]
            click.echo(f"DB content: {len(rows)} tables, {len(populated)} populated")
            click.echo("Top populated tables:")
            for name, cnt in sorted(rows, key=lambda x: -x[1])[:5]:
                if cnt > 0:
                    click.echo(f"  {name:<35s} {cnt:>10d}")
            click.echo("")

        if not confirm:
            click.echo("DRY RUN. Re-run with --confirm to execute.")
            click.echo("Backups go to .coding-os/backups/reset-<ts>/ unless --no-backup.")
            return

        ts = time.strftime("%Y%m%d-%H%M%S")
        bak_root = state / "backups" / f"reset-{ts}"
        if not no_backup:
            bak_root.mkdir(parents=True, exist_ok=True)
            click.echo(f"Backup -> {bak_root}")
            for label, p, _ in targets:
                dst = bak_root / p.name
                try:
                    if p.is_dir():
                        shutil.copytree(p, dst)
                    else:
                        shutil.copy2(p, dst)
                except OSError as exc:
                    click.echo(f"  backup failed for {p}: {exc}", err=True)
                    sys.exit(1)
            click.echo(f"  backup size: {_bytes(_path_size(bak_root))}")

        click.echo("Wiping...")
        wiped: list[str] = []
        for label, p, _ in targets:
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                wiped.append(str(p))
                click.echo(f"  removed: {p}")
            except OSError as exc:
                click.echo(f"  remove failed for {p}: {exc}", err=True)

        if not kuzu.exists():
            try:
                if kuzu_bak.exists():
                    shutil.copytree(kuzu_bak, kuzu)
                    click.echo(f"  restored empty Kuzu skeleton from {kuzu_bak}")
                else:
                    kuzu.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                click.echo(f"  kuzu skeleton restore failed: {exc}", err=True)

        click.echo("")
        click.echo(f"Wiped {len(wiped)} target(s).")
        if not no_backup:
            click.echo(f"Restore: cp -r {bak_root}/* .coding-os/")

        click.echo("")
        click.echo("Next steps:")
        click.echo("  1. Restart the agent so the MCP server runs migrations on a fresh DB.")
        if no_reindex:
            click.echo("  2. Run `cos graph-reindex` when ready to repopulate the graph.")
        else:
            click.echo("  2. Running `cos graph-reindex`...")
            try:
                subprocess.run(["cos", "graph-reindex"], check=False, cwd=str(project))
            except FileNotFoundError:
                click.echo("     `cos` not on PATH; run manually: cos graph-reindex", err=True)
        if not wipe_tasks:
            click.echo("  3. Task files preserved on disk; task_sync re-indexes on next agent prompt.")
