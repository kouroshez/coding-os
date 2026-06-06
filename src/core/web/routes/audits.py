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
    except Exception as exc:
        # Fire-and-forget per Rule 6: log to stderr so debug isn't
        # blind, then fall back to cwd. Hub usually provides
        # project_context, but standalone test / CLI invocation may not.
        sys.stderr.write(f"audits: project_context fallback to cwd: {exc}\n")
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

# SSOT for audit frontmatter `status:` field. Free-form drift produced
# `complete` (typo) + `completed` (canonical) in the wild. Enum +
# canonicaliser keeps every downstream consumer (Hub UI, guardian,
# hooks) reading one shape.
AUDIT_STATUS_VALUES: tuple[str, ...] = ("in_progress", "completed", "cancelled")
_STATUS_ALIASES: dict[str, str] = {
    # historic typo — agents used `complete` before the enum landed.
    "complete": "completed",
    "done": "completed",
    "open": "in_progress",
    "active": "in_progress",
    "abandoned": "cancelled",
}


def _canonical_status(raw: str | None) -> str:
    if not raw:
        return "unknown"
    v = raw.strip().lower()
    v = _STATUS_ALIASES.get(v, v)
    return v if v in AUDIT_STATUS_VALUES else "unknown"


# Match `**Key:** value` — colon is INSIDE the bold span. Stop value at
# next `**`, `·`, or newline so cell continues like `· **Status:** X` chain.
_MD_BOLD_KV_RE = re.compile(
    r"\*\*(?P<key>[A-Za-z][\w\s]*?):\*\*\s*(?P<value>[^*·\n]+)",
)


def _parse_markdown_header(text: str, out: dict) -> None:
    # Lenient markdown-bold form used by historic audits — mirrors the
    # session-context.sh / inject-resume-prompt.sh fallback so the Hub UI
    # surfaces the same status the agent banner reads.
    # Examples we must catch:
    #   **Status:** in_progress
    #   **Task:** TASK-032 · **Status:** in_progress
    # Only scan the doc header (first ~30 lines) so severity-bold table
    # entries (**CRITICAL** etc.) don't pollute the keys.
    head = "\n".join(text.splitlines()[:30])
    for m in _MD_BOLD_KV_RE.finditer(head):
        key_raw = m.group("key").strip().lower().replace(" ", "_")
        value = m.group("value").strip()
        # Normalise to YAML key shape — "Task" → "task_id".
        if key_raw == "task":
            key_raw = "task_id"
        if key_raw in _FM_KEYS and key_raw not in out:
            # Strip parenthetical suffix on status like
            # `complete (all 14 fixes landed ...)` so consumers
            # see the canonical state, not the prose elaboration.
            if key_raw == "status":
                value = re.split(r"[\s(]", value, maxsplit=1)[0].strip()
            out[key_raw] = value


def _parse_frontmatter(text: str) -> dict:
    out: dict = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
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
    # Markdown fallback for historic audits that lack YAML frontmatter
    # (e.g. **Status:** in_progress on the second line). Lenient parser
    # only fills missing keys — YAML stays authoritative when present.
    _parse_markdown_header(text, out)
    return out


def _row_counts(text: str) -> dict:
    # Audit category tables carry an ID in the first cell — bare numeric
    # (`| 1 |`), prefixed (`| L1 |`, `| G10 |`), or prefixed-with-summary
    # (`| F1/#2 resolve column-order |`). Match when the first cell
    # STARTS with the ID token, accepting trailing prose. Reject pure
    # header rows (`| ID | …`) by requiring at least one digit.
    data_rows = re.findall(
        r"^\|\s*(?:\d+|[A-Za-z]+\d+[\w/.\-#]*)\b[^|]*\|",
        text,
        flags=re.MULTILINE,
    )
    # "Unchecked" = a status cell still open. Tables use either a yes/no
    # Verified column or a pending/todo/done status column.
    unchecked = re.findall(
        r"^\|.*\|\s*(?:no|pending|todo)\s*\|?\s*$",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Checklist-shaped audits use markdown checkboxes instead of tables.
    # Surface those so the Hub UI gets a progress signal here too.
    # Filter out checkboxes under "deferred"/"skipped"/"out of scope"
    # sections — those represent explicit non-work, not unfinished gaps.
    work_text = _strip_non_work_sections(text)
    checkbox_done = re.findall(r"^\s*-\s\[[xX]\]", work_text, flags=re.MULTILINE)
    checkbox_todo = re.findall(r"^\s*-\s\[\s\]", work_text, flags=re.MULTILINE)
    total = len(data_rows) + len(checkbox_done) + len(checkbox_todo)
    return {
        "total": total,
        "unchecked": len(unchecked) + len(checkbox_todo),
    }


_NON_WORK_HEADING_RE = re.compile(
    r"^#{1,6}\s+(?:deferred|skipped|out of scope|not in scope|icebox|won.?t fix)\b",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_non_work_sections(text: str) -> str:
    # Drop everything from a `## Deferred` (etc.) heading until the next
    # heading at the same-or-shallower depth. Keeps the rest intact so
    # legitimate `- [ ]` items in the active work sections still count.
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    skip_until_depth: int | None = None
    for ln in lines:
        h_match = re.match(r"^(#{1,6})\s", ln)
        if h_match:
            depth = len(h_match.group(1))
            if skip_until_depth is not None and depth <= skip_until_depth:
                skip_until_depth = None  # exit skip block
            if skip_until_depth is None and _NON_WORK_HEADING_RE.match(ln):
                skip_until_depth = depth
                continue
        if skip_until_depth is not None:
            continue
        out.append(ln)
    return "".join(out)


def _as_str_list(value: object) -> list[str]:
    # Producer-side contract guard (api-contract-discipline): predicates /
    # matched_* are list-typed in the Hub UI, but a frontmatter author can
    # write a free-form prose scalar. The naive line parser then stores a
    # string, and `or []` only catches None/empty — so a truthy string used
    # to reach the UI and crash `(a.predicates ?? []).join(...)`. Coerce
    # here so the producer always emits the array shape the consumer reads.
    if isinstance(value, list):
        return [str(v) for v in value]
    if value in (None, ""):
        return []
    return [str(value)]


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
                "status": _canonical_status(fm.get("status")),
                "status_raw": fm.get("status") or "",
                "predicates": _as_str_list(fm.get("predicates")),
                "matched_exhaustive": _as_str_list(fm.get("matched_exhaustive")),
                "matched_scope": _as_str_list(fm.get("matched_scope")),
                "rows_total": counts["total"],
                "rows_unchecked": counts["unchecked"],
                "path": str(path.relative_to(audit_dir.parents[2]))
                if audit_dir.exists()
                else str(path),
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
            "status": _canonical_status(fm.get("status")),
            "status_raw": fm.get("status") or "",
            "predicates": _as_str_list(fm.get("predicates")),
            "rows_total": counts["total"],
            "rows_unchecked": counts["unchecked"],
            "markdown": body,
            "path": str(path),
        },
        "meta": {"layer": "audits", "source": "web.routes.audits"},
    }
