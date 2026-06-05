"""Flag Postgres/Supabase tables created without Row Level Security enabled.

PURPOSE:      A table in a public schema without RLS is reachable by the anon
              key = fully public. This scans migration SQL and lists every
              CREATE TABLE that has no matching ENABLE ROW LEVEL SECURITY.
INPUT:        one or more .sql file paths (migrations). [--schema public]
              only flag tables in this schema (default public; "" = all). [--json]
OUTPUT:       Findings on stderr; "clean"/"N table(s) without RLS" on stdout.
              Exit 0 clean, 1 if any unguarded table, 2 usage.
DEPENDENCIES: stdlib only. Static SQL scan — no database needed.
NOTES:        Heuristic regex parse (not a full SQL grammar); a clean pass is
              necessary not sufficient. Pure scan() is unit-testable.
              Spec: docs/playbooks/skill-authoring.md; craft: ../SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# create table [if not exists] [schema.]name   — capture optional schema + name
_CREATE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
    r"(?:\"?(?P<schema>\w+)\"?\.)?\"?(?P<name>\w+)\"?",
    re.IGNORECASE,
)
_ENABLE = re.compile(
    r"alter\s+table\s+(?:if\s+exists\s+)?"
    r"(?:\"?\w+\"?\.)?\"?(?P<name>\w+)\"?\s+enable\s+row\s+level\s+security",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def scan(sql: str, schema: str = "public") -> list[str]:
    """Return table names created (in `schema`, or any if schema=="") without RLS."""
    body = _strip_sql_comments(sql)
    created: list[tuple[str, str]] = [
        (m.group("schema") or "public", m.group("name")) for m in _CREATE.finditer(body)
    ]
    rls_enabled = {m.group("name").lower() for m in _ENABLE.finditer(body)}
    missing: list[str] = []
    for sch, name in created:
        if schema and sch.lower() != schema.lower():
            continue
        if name.lower() not in rls_enabled:
            missing.append(name)
    return missing


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    combined = ""
    for path in args.files:
        try:
            combined += "\n" + open(path, encoding="utf-8").read()
        except FileNotFoundError:
            print(f"error: {path} not found", file=sys.stderr)
            return 2

    missing = scan(combined, args.schema)
    for name in missing:
        print(f"  ✗ table '{name}': no ENABLE ROW LEVEL SECURITY — public via anon key", file=sys.stderr)
    if args.as_json:
        print(json.dumps({"missing_rls": missing, "count": len(missing)}))
    else:
        print("clean" if not missing else f"{len(missing)} table(s) without RLS")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
