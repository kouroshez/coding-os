"""Persian / multilingual retrieval precision harness (Phase I.1 gate).

PURPOSE:  Quantify how well the active embedding model (MiniLM vs
          BGE-M3 after migration) handles Persian queries against a
          fixture of mixed Persian/English document chunks.
INPUT:    --model NAME (default: active_model_name()).
OUTPUT:   JSON report with precision@1 and precision@3.
DEPENDS:  embeddings module + SQLite.
NOTES:    Small fixture (12 docs x 5 Persian queries) so the harness
          runs in seconds. The real payoff is running it once before
          and once after BGE-M3 migration and diffing the numbers.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve()
_CORE_DIR = _HERE.parent.parent.parent
_TOS_DIR = _CORE_DIR / "thinking_os"
for _p in (_CORE_DIR, _TOS_DIR):
    if _p.exists() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


FIXTURE: list[tuple[str, str]] = [
    ("doc:authentication", "User authentication flow: login, OAuth, JWT tokens"),
    ("doc:auth-persian", "جریان احراز هویت کاربر: ورود، OAuth، توکن‌های JWT"),
    ("doc:payment", "Payment processing: stripe integration, commission split"),
    ("doc:payment-persian", "پردازش پرداخت: یکپارچه‌سازی استرایپ، تقسیم کارمزد"),
    ("doc:commission-fa", "محاسبه کمیسیون فروش برای مشاور املاک"),
    ("doc:search", "Full-text search across products with FTS5"),
    ("doc:search-persian", "جستجوی متن کامل در محصولات با استفاده از FTS5"),
    ("doc:cache", "Redis cache layer with invalidation hooks"),
    ("doc:cache-persian", "لایه کش ردیس با قلاب‌های باطل‌سازی"),
    ("doc:analytics", "Product view analytics pipeline"),
    ("doc:analytics-persian", "خط لوله آمار بازدید محصول"),
    ("doc:misc", "General utility functions for date parsing"),
]


QUERIES: list[tuple[str, str]] = [
    ("احراز هویت کاربر", "doc:auth-persian"),
    ("تقسیم کارمزد", "doc:commission-fa"),
    ("جستجوی متن کامل", "doc:search-persian"),
    ("کش ردیس", "doc:cache-persian"),
    ("آمار محصول", "doc:analytics-persian"),
]


def _seed_fixture(conn: sqlite3.Connection, model_name: str) -> None:
    import embeddings  # type: ignore

    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS fixture ("
        "id INTEGER PRIMARY KEY, uid TEXT UNIQUE, content TEXT)"
    )
    for uid, content in FIXTURE:
        cursor.execute(
            "INSERT OR IGNORE INTO fixture (uid, content) VALUES (?, ?)",
            (uid, content),
        )
    conn.commit()
    rows = cursor.execute("SELECT id, content FROM fixture").fetchall()
    for row_id, content in rows:
        embeddings.upsert_embedding(
            conn, "fixture", int(row_id), content, model_name=model_name
        )


def _score(conn: sqlite3.Connection, model_name: str) -> dict:
    import embeddings  # type: ignore

    cursor = conn.cursor()
    hits_at_1 = hits_at_3 = 0
    results = []
    for query, expected_uid in QUERIES:
        vec = embeddings.embed_text(query, model_name=model_name)
        if vec is None:
            results.append({"query": query, "skipped": "embed failed"})
            continue
        candidates = cursor.execute(
            "SELECT e.source_id, e.embedding, f.uid FROM embeddings e "
            "JOIN fixture f ON e.source_id = f.id WHERE e.model_name = ?",
            (model_name,),
        ).fetchall()
        vectors = [row[1] for row in candidates]
        scores = embeddings.cosine_similarity(vec, vectors)
        ranked = sorted(
            zip((row[2] for row in candidates), scores),
            key=lambda pair: pair[1],
            reverse=True,
        )
        if ranked and ranked[0][0] == expected_uid:
            hits_at_1 += 1
        if any(uid == expected_uid for uid, _ in ranked[:3]):
            hits_at_3 += 1
        results.append(
            {
                "query": query,
                "expected": expected_uid,
                "top_3": [{"uid": u, "score": round(s, 4)} for u, s in ranked[:3]],
            }
        )
    total = len(QUERIES) or 1
    return {
        "model_name": model_name,
        "precision_at_1": hits_at_1 / total,
        "precision_at_3": hits_at_3 / total,
        "details": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    import embeddings  # type: ignore
    from db import init_db  # type: ignore

    model_name = args.model or embeddings.active_model_name()
    if not embeddings.is_available():
        print(json.dumps({"status": "skipped", "reason": "embeddings unavailable"}))
        return 0

    db_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    conn = init_db(str(db_path))
    try:
        _seed_fixture(conn, model_name=model_name)
        report = _score(conn, model_name=model_name)
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.output:
        Path(args.output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
