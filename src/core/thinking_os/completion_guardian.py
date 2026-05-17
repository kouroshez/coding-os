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


def _load_intent(agent_dir: Path) -> dict[str, Any] | None:
    intent_path = agent_dir / ".intent.json"
    if not intent_path.exists():
        return None
    try:
        return json.loads(intent_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"guardian: intent-read-failed: {exc}\n")
        return None


def _load_evidence_bundle(agent_dir: Path, session_id: str) -> dict[str, Any] | None:
    bundle_path = agent_dir / f"evidence_bundle_{session_id}.json"
    if not bundle_path.exists():
        return None
    try:
        return json.loads(bundle_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        sys.stderr.write(f"guardian: bundle-read-failed: {exc}\n")
        return None


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
        if re.search(r"^status:\s*in_progress\b", text, flags=re.MULTILINE):
            active.append(path)
    return active


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


def _predicate_gaps(
    intent: dict[str, Any] | None, bundle: dict[str, Any] | None
) -> list[str]:
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
    status="fail" iff exhaustive intent active AND gaps non-empty.
    """
    agent_dir = _agent_dir()
    repo = repo_root or Path.cwd()

    intent = _load_intent(agent_dir)
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

    result = GuardResult(
        status="fail" if (intent_exhaustive and gaps) else "pass",
        gaps=gaps,
        audits_checked=audits_checked,
        intent_exhaustive=intent_exhaustive,
        has_evidence_bundle=bundle is not None,
    )
    return result


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
    json.dump(result.to_dict(), sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0 if result.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
