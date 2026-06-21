from __future__ import annotations

import sqlite3

DEFAULT_LIMIT = 50
MAX_LIMIT = 2000

# Severity ladder mirrors logging_os.config.Level. log_events stores WARN+ only,
# so a level floor expands to the IN-set of labels at or above it (text column,
# no numeric severity stored).
_LEVEL_ORDER = ["DEBUG", "INFO", "OK", "WARN", "ERROR", "FATAL"]


def _levels_at_or_above(floor: str) -> list[str]:
    floor_up = floor.strip().upper()
    if floor_up not in _LEVEL_ORDER:
        return []
    return _LEVEL_ORDER[_LEVEL_ORDER.index(floor_up) :]


def log_query(
    conn: sqlite3.Connection,
    *,
    level: str | None = None,
    scope: str | None = None,
    since: str | None = None,
    search: str | None = None,
    session_id: str | None = None,
    trace_id: str | None = None,
    fingerprint: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    limit = max(1, min(MAX_LIMIT, int(limit)))

    where: list[str] = []
    params: list = []

    if level:
        levels = _levels_at_or_above(level)
        if not levels:
            raise ValueError(f"Invalid level '{level}'. One of: {_LEVEL_ORDER}")
        where.append(f"lvl IN ({','.join('?' for _ in levels)})")
        params.extend(levels)
    if scope:
        where.append("scope LIKE ?")
        params.append(scope.replace("*", "%"))  # fnmatch-style glob → SQL LIKE
    if since:
        where.append("ts >= ?")  # ISO8601 is lexicographically sortable
        params.append(since)
    if search:
        where.append("msg LIKE ?")
        params.append(f"%{search}%")
    if session_id:
        where.append("session_id = ?")
        params.append(session_id)
    if trace_id:
        where.append("trace_id = ?")
        params.append(trace_id)
    if fingerprint:
        where.append("fingerprint = ?")
        params.append(fingerprint)

    where_sql = " AND ".join(where) if where else "1=1"

    total = conn.execute(f"SELECT COUNT(*) FROM log_events WHERE {where_sql}", params).fetchone()[0]

    rows = conn.execute(
        f"SELECT id, ts, lvl, scope, msg, kv, exc_type, stack, "
        f"session_id, trace_id, fingerprint "
        f"FROM log_events WHERE {where_sql} "
        f"ORDER BY ts DESC, id DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    return {
        "total": total,
        "count": len(rows),
        "rows": [dict(r) for r in rows],
    }
