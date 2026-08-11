"""Thinking OS — Health Check human-readable report renderer."""

from __future__ import annotations


def print_human_readable(results: dict) -> None:
    """Print a human-readable health report."""
    status_icon = {"PASS": "✅", "WARN": "⚠���", "FAIL": "��"}

    print("╔══════════════════════════════════════════════════════╗")
    print("║  THINKING OS HEALTH CHECK                           ║")
    print(f"║  {results['timestamp'][:19]}                       ║")
    print("╚═══════���═══════════════════��══════════════════════════╝")
    print()

    # Database
    db = results["database"]
    print(f"── Database {status_icon.get(db['status'], '?')} ─────────────────────────────────")
    if db.get("stats"):
        s = db["stats"]
        print(
            f"  Size: {s.get('db_size_mb', '?')} MB  |  Schema: v{s.get('schema_version', '?')}  |  FTS5: {s.get('fts5_available', '?')}"
        )
        if "tables" in s:
            print("  Tables:")
            for table, count in s["tables"].items():
                marker = "✅" if (count or 0) > 0 else "��"
                print(f"    {marker} {table}: {count or 0}")
        print(
            f"  Learning tables active: {s.get('learning_tables_active', 0)}/{s.get('learning_tables_total', 0)}"
        )
        if "session_null_ratio_pct" in s:
            print(f"  Session null ratio: {s['session_null_ratio_pct']}%")
        if "observations_narrative_null_pct" in s:
            print(f"  Observations narrative null: {s['observations_narrative_null_pct']}%")
    print()

    # Hooks
    hooks = results["hooks"]
    print(f"── Hooks {status_icon.get(hooks['status'], '?')} ────────────────────────────────────")
    ok_count = sum(
        1 for h in hooks.get("hooks", {}).values() if h.get("exists") and h.get("syntax_ok")
    )
    total = len(hooks.get("hooks", {}))
    print(
        f"  {ok_count}/{total} hooks OK  |  Test suite: {'✅' if hooks.get('test_suite_exists') else '❌'}"
    )
    print()

    # Gates
    gates = results["gates"]
    print(
        f"── Gates {status_icon.get(gates['status'], '?')} ──────���─────────────────────────────"
    )
    print(f"  Session: {gates.get('session_id', 'none')}")
    for name, info in gates.get("gates", {}).items():
        if info["exists"]:
            match = "✅" if info.get("session_match") else "❌"
            stale = " (STALE)" if info.get("stale") else ""
            print(
                f"  {name}: {info.get('value', '?')} [session:{match}] [{info.get('age_minutes', '?')}min]{stale}"
            )
        else:
            print(f"  {name}: not set")
    print()

    # Learning Pipeline
    lp = results["learning_pipeline"]
    print(f"��─ Learning Pipeline {status_icon.get(lp['status'], '?')} ─────────────────────────")
    for script, info in lp.get("components", {}).items():
        if isinstance(info, dict) and "exists" in info:
            marker = "✅" if info["exists"] else "❌"
            print(f"  {marker} {script}: {info.get('description', '')}")
        elif isinstance(info, bool):
            marker = "✅" if info else "❌"
            print(f"  {marker} {script}")
    print()

    # Issues
    issues = results.get("all_issues", [])
    if issues:
        print(f"── Issues ({len(issues)}) ─────��────────────────────────────────")
        for issue in issues:
            print(f"  ⚠️  {issue}")
        print()

    # Overall
    overall = results["overall"]
    print("══════════════════════════════════════════════════════════")
    print(f"  OVERALL: {status_icon.get(overall, '?')} {overall}")
    print("════════��═══════════════════════════���═════════════════════")
