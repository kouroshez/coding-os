"""Completion guardian — Stop-event evidence assertion for exhaustive intent.

Layer 3 of the 3-layer intent architecture (Layer 1 = SessionStart
intent-primer; Layer 2 = UserPromptSubmit detect-exhaustive-intent).

Called by src/core/hooks/verify-completion-claim.sh on every Stop event.
The hook should block the agent from stopping ONLY when:

  1. .intent.json shows exhaustive=true for the active prompt, AND
  2. An active audit artifact (docs/tasks/audits/audit-*.md with
     status:in_progress) has unfinished rows OR
  3. The EvidenceBundle predicates evaluate to gaps via
     cognition_schemas.validate_exhaustive_evidence.

If none of the above, allow stop (return GuardResult.status="pass").
This keeps the guardian off the critical path for ordinary turns and
fires only when the dogfood contract demands it.

See docs/engineering/intent-vocabulary.md for the predicate spec and
docs/_meta/audit-checklist-template.md for the artifact schema.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GuardResult:
    status: str  # "pass" | "fail"
    gaps: list[str] = field(default_factory=list)
    audits_checked: list[str] = field(default_factory=list)
    intent_exhaustive: bool = False
    has_evidence_bundle: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "gaps": self.gaps,
            "audits_checked": self.audits_checked,
            "intent_exhaustive": self.intent_exhaustive,
            "has_evidence_bundle": self.has_evidence_bundle,
        }


def _agent_dir() -> Path:
    base = os.environ.get("COS_AGENT_DIR")
    if base:
        return Path(base)
    state = os.environ.get("COS_STATE_DIR") or ".coding-os"
    agent = os.environ.get("COS_AGENT") or "claude"
    return Path(state) / agent


def _panel_dir() -> Path:
    panel = os.environ.get("COS_PANEL_DIR")
    if panel:
        return Path(panel)
    return _agent_dir()


def _load_intent(target_dir: Path) -> dict[str, Any] | None:
    # Panel-private intent first; falls back to legacy agent-dir location
    # during the migration window so historic consumer projects don't break.
    candidates = [target_dir / ".intent.json"]
    agent_dir = _agent_dir()
    if agent_dir != target_dir:
        candidates.append(agent_dir / ".intent.json")
    for intent_path in candidates:
        if not intent_path.exists():
            continue
        try:
            return json.loads(intent_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(f"guardian: intent-read-failed: {exc}\n")
            return None
    return None


def _intent_anchor_mtime(target_dir: Path) -> float | None:
    # mtime of the session's intent.json — used as the "current session"
    # cutoff for A2 (only audits touched after this anchor are this
    # session's concern). None when no intent file exists.
    candidates = [target_dir / ".intent.json"]
    agent_dir = _agent_dir()
    if agent_dir != target_dir:
        candidates.append(agent_dir / ".intent.json")
    for intent_path in candidates:
        try:
            if intent_path.exists():
                return intent_path.stat().st_mtime
        except OSError:
            continue
    return None


def _load_evidence_bundle(target_dir: Path, session_id: str) -> dict[str, Any] | None:
    candidates = [target_dir / f"evidence_bundle_{session_id}.json"]
    agent_dir = _agent_dir()
    if agent_dir != target_dir:
        candidates.append(agent_dir / f"evidence_bundle_{session_id}.json")
    for bundle_path in candidates:
        if not bundle_path.exists():
            continue
        try:
            return json.loads(bundle_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            sys.stderr.write(f"guardian: bundle-read-failed: {exc}\n")
            return None
    return None


def _guardian_db_path() -> str:
    db = os.environ.get("COS_DB_PATH")
    if db:
        return db
    state = os.environ.get("COS_STATE_DIR") or ".coding-os"
    return str(Path(state) / "coding-os.db")


def _evidence_dispatch_recorded(session_id: str) -> bool:
    # True iff a real cos_supervise_record_output(exhaustive_evidence, ok) row
    # exists in formula_dispatches for this session. The bundle JSON file alone
    # is not proof — it can be hand-authored. Fail-open: any DB error (missing
    # file/table/lock) returns True so the guardian never blocks legit work on
    # a transient DB read.
    if not session_id:
        return True
    db_path = _guardian_db_path()
    if not Path(db_path).exists():
        return True
    try:
        import sqlite3

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM formula_dispatches "
                "WHERE session_id=? AND formula_id='exhaustive_evidence' "
                "AND status='ok' LIMIT 1",
                (session_id,),
            ).fetchone()
        return row is not None
    except Exception as exc:
        sys.stderr.write(f"guardian: dispatch-check failed (fail-open): {exc}\n")
        return True


def _active_audit_files(repo_root: Path) -> list[Path]:
    audit_dir = repo_root / "docs" / "tasks" / "audits"
    if not audit_dir.is_dir():
        return []
    active: list[Path] = []
    for path in sorted(audit_dir.glob("audit-*.md")):
        try:
            text = path.read_text()
        except OSError:
            continue
        # Match BOTH conventions: YAML frontmatter (canonical per
        # audit-checklist-template.md) and markdown bold (historic /
        # lenient). Mirrors session-context.sh + enforce-audit-artifact.sh
        # so the guardian never under-counts active audits and lets a
        # markdown-form audit slip through as "no gaps detected".
        yaml_form = re.search(r"^status:\s*in_progress\b", text, flags=re.MULTILINE)
        md_form = re.search(r"\*\*Status:\*\*\s+in_progress\b", text, flags=re.MULTILINE)
        if yaml_form or md_form:
            active.append(path)
    return active


_EVIDENCE_CHECKBOX = re.compile(r"-\s*\[[xX]\]\s*EvidenceBundle submitted", flags=re.MULTILINE)
_STATUS_COMPLETED = re.compile(
    r"^status:\s*completed\b|\*\*Status:\*\*\s+completed\b", flags=re.MULTILINE
)


def _audit_claims_completion(text: str) -> bool:
    # An audit "claims completion" when its frontmatter/body marks it done
    # OR the Closing Checklist EvidenceBundle box is ticked. Either is an
    # attestation the Stop guardian must be able to cross-check against a
    # real cos_supervise_record_output dispatch row.
    return bool(_STATUS_COMPLETED.search(text) or _EVIDENCE_CHECKBOX.search(text))


def _completed_audit_files(repo_root: Path, since_mtime: float) -> list[Path]:
    # Only audits TOUCHED in the current session (file mtime >= the session
    # anchor) are this session's concern. This keeps A2 from re-flagging the
    # dozens of historical status:completed audits every Stop — their mtime
    # predates the anchor, so they never match. since_mtime is the intent.json
    # mtime (a per-session file written by detect-exhaustive-intent.sh).
    audit_dir = repo_root / "docs" / "tasks" / "audits"
    if not audit_dir.is_dir():
        return []
    claimed: list[Path] = []
    for path in sorted(audit_dir.glob("audit-*.md")):
        try:
            if path.stat().st_mtime < since_mtime:
                continue
            text = path.read_text()
        except OSError:
            continue
        if _audit_claims_completion(text):
            claimed.append(path)
    return claimed


def _count_unchecked_rows(text: str) -> int:
    # Mandatory table column 8 = Verified. Unchecked rows have `| no |`.
    return len(re.findall(r"^\|.*\|\s*no\s*\|", text, flags=re.MULTILINE))


def _audit_gaps(audit_path: Path) -> list[str]:
    try:
        text = audit_path.read_text()
    except OSError as exc:
        return [f"audit-read-failed: {audit_path.name}: {exc}"]
    unchecked = _count_unchecked_rows(text)
    if unchecked == 0:
        return []
    return [f"{audit_path.name}: {unchecked} unchecked category rows"]


def _predicate_gaps(intent: dict[str, Any] | None, bundle: dict[str, Any] | None) -> list[str]:
    if not intent:
        return []
    predicates = intent.get("predicates") or []
    if not predicates:
        return []
    if not bundle:
        return [f"predicates_unsatisfied: no EvidenceBundle for predicates {predicates}"]
    ee = bundle.get("exhaustive_evidence")
    if ee is None:
        return [f"predicates_unsatisfied: no exhaustive_evidence for predicates {predicates}"]
    schemas = _import_schemas()
    if schemas is None:
        return []
    try:
        evidence = schemas.ExhaustiveEvidence.model_validate(ee)
    except Exception as exc:
        return [f"exhaustive_evidence-malformed: {exc}"]
    return list(schemas.validate_exhaustive_evidence(evidence, predicates))


def _import_schemas():
    try:
        import cognition_schemas as schemas

        return schemas
    except ImportError as exc:
        sys.stderr.write(f"guardian: cognition_schemas direct import: {exc}\n")
    here = Path(__file__).resolve().parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    try:
        import cognition_schemas as schemas

        return schemas
    except ImportError as exc:
        sys.stderr.write(f"guardian: cognition_schemas path-rescue import: {exc}\n")
        return None


def guard_completion(
    session_id: str = "",
    repo_root: Path | None = None,
) -> GuardResult:
    """Return a GuardResult for the current agent state.

    status="pass" iff no enforcement applies OR all gaps clean.
    status="fail" iff (exhaustive intent active AND gaps non-empty) OR a
    completed-audit forgery is detected (A2 — runtime-independent).
    """
    agent_dir = _panel_dir()
    repo = repo_root or Path.cwd()

    intent = _load_intent(agent_dir)
    # Reject session-mismatched intent: if intent.json was written under a
    # different session id than the one the Stop hook is running under, the
    # predicates belong to a prompt the current session never saw and the
    # bundle (keyed by session_id) cannot satisfy them. Treat as no intent.
    if intent and session_id and intent.get("session_id"):
        if intent.get("session_id") != session_id:
            intent = None
    intent_exhaustive = bool(intent and intent.get("exhaustive"))

    bundle = None
    if session_id:
        bundle = _load_evidence_bundle(agent_dir, session_id)

    gaps: list[str] = []
    audits_checked: list[str] = []

    if intent_exhaustive:
        for audit_path in _active_audit_files(repo):
            audits_checked.append(str(audit_path.relative_to(repo)))
            gaps.extend(_audit_gaps(audit_path))
        gaps.extend(_predicate_gaps(intent, bundle))
        # Cross-check the file-based bundle against the DB. A bundle that
        # claims exhaustive_evidence but has no matching ok dispatch row was
        # never persisted by cos_supervise_record_output — the audit checkbox
        # "EvidenceBundle submitted" is then a false attestation. Additive:
        # only fires when a bundle already claims evidence, so legit runs
        # (which always write the DB row alongside the file) keep passing.
        if bundle and bundle.get("exhaustive_evidence") is not None:
            if not _evidence_dispatch_recorded(session_id):
                gaps.append(
                    "evidence_dispatch_missing: bundle has exhaustive_evidence "
                    "but no formula_dispatches row — cos_supervise_record_output "
                    f"never ran for session {session_id}"
                )

    # A2 (TASK-062) — forgery check independent of intent.exhaustive: an audit
    # this session marked completed / ticked the EvidenceBundle box on must be
    # backed by a real cos_supervise_record_output dispatch row. Reads the audit
    # FILE (not the bundle), catching the Codex-CLI path that writes no bundle.
    # COVERAGE (do not overstate): this runs at the agent Stop event and is
    # anchored on intent.json (a UserPromptSubmit artifact), so it covers
    # Claude / Cursor / Codex-CLI but NOT Codex-GUI / human-direct (0 hooks).
    # That cross-runtime hole is closed by the git-level pre-commit backstop
    # pre_commit_batch._check_audit_evidence (matches audit task_id ->
    # formula_dispatches.task_marker; no schema change). The dispatch lookup
    # here is session-keyed (any exhaustive_evidence row this session clears
    # all its completed audits, not per-audit). Fail-open on DB / empty sid.
    forgery_gaps: list[str] = []
    anchor = _intent_anchor_mtime(agent_dir)
    if session_id and anchor is not None:
        completed = _completed_audit_files(repo, anchor)
        # session-keyed answer — query once, not per audit.
        if completed and not _evidence_dispatch_recorded(session_id):
            for audit_path in completed:
                rel = str(audit_path.relative_to(repo))
                if rel not in audits_checked:
                    audits_checked.append(rel)
                forgery_gaps.append(
                    f"audit_completion_forged: {audit_path.name} claims completion "
                    "but no formula_dispatches row — cos_supervise_record_output "
                    f"never ran for session {session_id}"
                )
    gaps.extend(forgery_gaps)

    failed = (intent_exhaustive and gaps) or bool(forgery_gaps)
    result = GuardResult(
        status="fail" if failed else "pass",
        gaps=gaps,
        audits_checked=audits_checked,
        intent_exhaustive=intent_exhaustive,
        has_evidence_bundle=bundle is not None,
    )
    return result


def _record_gap_observation_safe(session_id: str, result: GuardResult) -> None:
    """Append a completion_gap observation row so the learning loop (G11)
    can surface recurring premature-done patterns across sessions.

    Fire-and-forget: never propagates a DB error to the hook flow.
    """
    db_path = _guardian_db_path()
    if not Path(db_path).exists():
        return
    try:
        import sqlite3

        title = f"completion_gap: {len(result.gaps)} gap(s)"
        narrative = " | ".join(result.gaps[:10])
        facts = json.dumps(
            {
                "audits_checked": result.audits_checked,
                "has_evidence_bundle": result.has_evidence_bundle,
                "gap_count": len(result.gaps),
            },
            ensure_ascii=False,
        )
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO observations "
                "(session_id, tool_name, observation_type, memory_type, "
                "impact_score, title, narrative, facts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    session_id or "unknown",
                    "completion_guardian",
                    "completion_gap",
                    "error",
                    0.8,
                    title,
                    narrative,
                    facts,
                ),
            )
    except Exception as exc:
        sys.stderr.write(f"guardian: observation insert failed: {exc}\n")


def main(argv: list[str]) -> int:
    session_id = ""
    try:
        payload = json.load(sys.stdin)
        session_id = (
            payload.get("session_id")
            or payload.get("sessionId")
            or os.environ.get("CLAUDE_SESSION_ID", "")
        )
    except (json.JSONDecodeError, ValueError):
        session_id = os.environ.get("CLAUDE_SESSION_ID", "")

    result = guard_completion(session_id=session_id)

    if result.status == "fail":
        _record_gap_observation_safe(session_id, result)

    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
