"""core.web.routes.audits — /api/audits — active intent-enforcement audits.

Surfaces the audit-*.md files written by the agent under exhaustive
intent (TASK-004 G12).  Each row reports its frontmatter
(audit_id, task_id, predicates, status) plus a count of unchecked
category-table rows so the Hub UI can render a progress bar.

Endpoints:
  GET /api/audits                   list all audits (filterable by status)
  GET /api/audits/{audit_id}        full markdown body
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/audits", tags=["audits"])


def _audits_dir() -> Path:
    try:
        from web._project_context import current_project_root  # type: ignore
        root = current_project_root()
    except Exception:
        root = Path.cwd()
    return Path(root) / "docs" / "tasks" / "audits"


_FM_KEYS = (
    "audit_id",
    "task_id",
    "intent_detected_at",
    "matched_exhaustive",
    "matched_scope",
    "predicates",
    "status",
    "created",
    "completed",
)


def _parse_frontmatter(text: str) -> dict:
    out: dict = {}
    if not text.startswith("---"):
        return out
    end = text.find("\n---", 3)
    if end == -1:
        return out
    fm = text[3:end].strip()
    for line in fm.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key not in _FM_KEYS:
            continue
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            out[key] = [
                v.strip().strip('"').strip("'") for v in inner.split(",") if v.strip()
            ]
        else:
            out[key] = value.strip('"').strip("'")
    return out


def _row_counts(text: str) -> dict:
    data_rows = re.findall(r"^\|\s*\d+\s*\|", text, flags=re.MULTILINE)
    unchecked = re.findall(r"^\|.*\|\s*no\s*\|", text, flags=re.MULTILINE)
    return {"total": len(data_rows), "unchecked": len(unchecked)}


def _scan_audits() -> list[dict]:
    audits: list[dict] = []
    audit_dir = _audits_dir()
    if not audit_dir.is_dir():
        return audits
    for path in sorted(audit_dir.glob("audit-*.md")):
        try:
            text = path.read_text()
        except OSError:
            continue
        fm = _parse_frontmatter(text)
        counts = _row_counts(text)
        audits.append(
            {
                "audit_id": fm.get("audit_id") or path.stem.replace("audit-", ""),
                "task_id": fm.get("task_id"),
                "status": fm.get("status") or "unknown",
                "predicates": fm.get("predicates") or [],
                "matched_exhaustive": fm.get("matched_exhaustive") or [],
                "matched_scope": fm.get("matched_scope") or [],
                "rows_total": counts["total"],
                "rows_unchecked": counts["unchecked"],
                "path": str(path.relative_to(audit_dir.parents[2]))
                if audit_dir.exists() else str(path),
            }
        )
    return audits


@router.get("")
async def list_audits(status: str = "") -> dict:
    """List all audit artifacts with their progress state.

    Optional `status` filter narrows to e.g. status=in_progress.
    """
    audits = _scan_audits()
    if status:
        audits = [a for a in audits if a.get("status") == status]
    return {
        "ok": True,
        "data": {
            "audits": audits,
            "count": len(audits),
        },
        "meta": {"layer": "audits", "source": "web.routes.audits"},
    }


@router.get("/{audit_id}")
async def get_audit(audit_id: str) -> dict:
    """Full markdown body for one audit_id."""
    audit_dir = _audits_dir()
    candidates = list(audit_dir.glob(f"audit-{audit_id}*.md"))
    if not candidates:
        candidates = list(audit_dir.glob("audit-*.md"))
        candidates = [p for p in candidates if audit_id in p.stem]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"audit {audit_id} not found")
    path = candidates[0]
    try:
        body = path.read_text()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    fm = _parse_frontmatter(body)
    counts = _row_counts(body)
    return {
        "ok": True,
        "data": {
            "audit_id": fm.get("audit_id") or audit_id,
            "task_id": fm.get("task_id"),
            "status": fm.get("status"),
            "predicates": fm.get("predicates") or [],
            "rows_total": counts["total"],
            "rows_unchecked": counts["unchecked"],
            "markdown": body,
            "path": str(path),
        },
        "meta": {"layer": "audits", "source": "web.routes.audits"},
    }
