#!/usr/bin/env python3
"""
Thinking OS — Observation compression via Claude API (TASK-155).

Batch script that processes raw observations (narrative IS NULL)
and generates AI-structured summaries using Claude Haiku.
Runs via `make thinking_os-compress`.

Summaries preserve the observation Title's symbols verbatim and are tagged
with a `_generated_by` provenance marker; the original Title row is never
overwritten, so ground-truth memory survives a faulty summary.

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

from database import DEFAULT_DB_PATH, get_connection

from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os.compress")

BATCH_LIMIT = 10
DELAY_BETWEEN_CALLS = 1.0  # seconds


def _build_prompt(title: str, files_modified: str) -> str:
    # Symbol fidelity is non-negotiable: cos_search matches on narrative/concepts,
    # so a dropped or renamed identifier becomes a silently-wrong memory a future
    # session trusts. The prompt forbids invention and pins every Title symbol.
    return (
        "You are summarising a code-change observation for a developer memory index.\n"
        f"Title: {title}\n"
        f"Files: {files_modified}\n\n"
        "Rules:\n"
        "- Preserve every identifier, symbol, file path, function and class name from "
        "the Title VERBATIM. Never rename, abbreviate, translate, or invent them.\n"
        "- Use ONLY information supported by the Title and Files; do not invent facts.\n"
        "- If you cannot summarise faithfully, set narrative to the Title unchanged.\n\n"
        "Return ONLY a JSON object (no markdown):\n"
        '- "narrative": 1-2 sentence summary of what changed and why, keeping all symbols verbatim\n'
        '- "facts": JSON object of key/value insights grounded in the Title/Files\n'
        '- "concepts": array of 3-5 lowercase concept tags drawn from the Title/Files\n'
    )


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    if "```" in text:
        json_text = text.split("```")[1].strip()
        if json_text.startswith("json"):
            json_text = json_text[4:].strip()
        return json.loads(json_text)
    return None


def _call_claude_api(title: str, files_modified: str) -> dict | None:
    """Call Claude Haiku for a structured summary that preserves the Title's symbols.

    Returns dict with narrative, facts, concepts or None on failure. Generated
    facts carry a `_generated_by` provenance marker; the original observation
    Title row is never overwritten.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed. Run: uv add anthropic")
        return None

    # Model selection — env-overridable for enterprise deployments that pin to a
    # specific model snapshot. Default is the cheapest model fit for narrative.
    model_id = os.environ.get("COS_COMPRESS_MODEL", "claude-haiku-4-5-20251001")
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_id,
            max_tokens=300,
            messages=[{"role": "user", "content": _build_prompt(title, files_modified)}],
        )
        parsed = _parse_json(response.content[0].text)
        # Provenance: tag generated facts so cos_search consumers can tell a
        # machine-inferred summary from an authored observation. `facts` is not
        # in cos_search's WHERE clause, so the marker is non-intrusive.
        if isinstance(parsed, dict) and isinstance(parsed.get("facts"), dict):
            parsed["facts"]["_generated_by"] = model_id
        return parsed
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
        return {
            "status": "no_api_key",
            "message": "API key not configured. Set ANTHROPIC_API_KEY to enable compression.",
        }

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
