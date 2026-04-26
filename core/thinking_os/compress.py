#!/usr/bin/env python3
"""
Thinking OS — Observation compression via Claude API (TASK-155).

Batch script that processes raw observations (narrative IS NULL)
and generates AI-structured summaries using Claude Haiku.
Runs via `make thinking_os-compress`.

Falls back gracefully if:
  - ANTHROPIC_API_KEY not set
  - API call fails
  - DB absent
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import DEFAULT_DB_PATH, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("thinking_os.compress")

BATCH_LIMIT = 10
DELAY_BETWEEN_CALLS = 1.0  # seconds


def _call_claude_api(title: str, files_modified: str) -> dict | None:
    """Call Claude Haiku to generate structured summary.

    Returns dict with narrative, facts, concepts or None on failure.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed. Run: uv add anthropic")
        return None

    prompt = (
        f"Given this code change observation:\n"
        f"Title: {title}\n"
        f"Files: {files_modified}\n\n"
        f"Generate a JSON object with:\n"
        f'- "narrative": 1-2 sentence summary of what was done and why (infer from file paths)\n'
        f'- "facts": key insights as a JSON object (e.g. {{"file_type": "model", "domain": "products"}})\n'
        f'- "concepts": array of 3-5 concept tags (e.g. ["django", "models", "products"])\n\n'
        f"Respond with ONLY the JSON object, no markdown."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        # Parse JSON from response
        if text.startswith("{"):
            return json.loads(text)
        # Try to extract JSON from markdown code block
        if "```" in text:
            json_text = text.split("```")[1].strip()
            if json_text.startswith("json"):
                json_text = json_text[4:].strip()
            return json.loads(json_text)
        return None
    except Exception as exc:
        logger.warning("API call failed for '%s': %s", title, exc)
        return None


def compress_observations(db_path: str | Path | None = None, *, dry_run: bool = False) -> dict:
    """Process raw observations and generate AI summaries.

    Args:
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.
        dry_run: If True, don't write to DB or call API.

    Returns:
        Dict with stats.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        logger.info("No DB at %s, skipping", path)
        return {"status": "no_db"}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set. Set it to enable compression.")
        return {"status": "no_api_key", "message": "API key not configured. Set ANTHROPIC_API_KEY to enable compression."}

    conn = get_connection(path)
    try:
        rows = conn.execute(
            "SELECT id, title, files_modified FROM observations "
            "WHERE narrative IS NULL AND title IS NOT NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (BATCH_LIMIT,),
        ).fetchall()

        stats = {"total_pending": len(rows), "compressed": 0, "failed": 0, "skipped": 0}

        for row in rows:
            d = dict(row)

            if dry_run:
                stats["skipped"] += 1
                continue

            result = _call_claude_api(d["title"] or "", d["files_modified"] or "")

            if result:
                narrative = result.get("narrative", d["title"])
                facts = json.dumps(result.get("facts", {}))
                concepts = json.dumps(result.get("concepts", []))

                conn.execute(
                    "UPDATE observations SET narrative = ?, facts = ?, concepts = ? WHERE id = ?",
                    (narrative, facts, concepts, d["id"]),
                )
                conn.commit()
                stats["compressed"] += 1
                logger.info("Compressed observation %d: %s", d["id"], d["title"])
            else:
                stats["failed"] += 1

            time.sleep(DELAY_BETWEEN_CALLS)

        return stats
    finally:
        conn.close()


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        logger.info("DRY RUN — no API calls or DB writes")

    stats = compress_observations(dry_run=dry_run)
    logger.info("Compression results: %s", stats)


if __name__ == "__main__":
    main()
