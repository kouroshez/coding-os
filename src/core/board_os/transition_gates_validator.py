"""Transition Gate validator (TASK-104)."""

from __future__ import annotations

import os
import re

from board_os._gates_override import (
    OverrideRequest as OverrideRequest,
    evaluate_override as evaluate_override,
)
from board_os._gates_result import (
    ValidationMessage as ValidationMessage,
    ValidationResult as ValidationResult,
    Verdict as Verdict,
)
from board_os.parser import _extract_body_sections, _extract_outcome
from board_os.transition_gates import (
    DoDKindRules,
    DoRKindRules,
    GatesConfig,
    SectionRule,
)

# ────────────────────────────────────────────────────────────────────
# Section evaluation
# ────────────────────────────────────────────────────────────────────


def _section_text_or_none(body: str, name: str) -> str | None:
    """Pull a section's body text. Outcome is special-cased (lives outside H2s).

    H2 headers in real task files often carry trailing decoration like
    "## Acceptance (G/W/T) — *this IS the Definition of Done*". Match by
    prefix so a rule named "Acceptance" still resolves to that header.
    """
    if name == "Outcome":
        return _extract_outcome(body)
    sections = _extract_body_sections(body)
    if name in sections:
        return sections[name]
    target = name.lower()
    for header, text in sections.items():
        # Prefix match — header must start with the configured name as a
        # whole word, not as a substring of a different word.
        norm = header.lower()
        if (
            norm == target
            or norm.startswith(target + " ")
            or norm.startswith(
                target + "(",
            )
        ):
            return text
    return None


def _count_list_items(text: str) -> int:
    """Count `- ` bullets in a section, ignoring empty lines."""
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("- "))


def _evaluate_section(
    name: str,
    rule: SectionRule,
    body: str,
    result: ValidationResult,
    project_root: str | None = None,
) -> None:
    """Apply one SectionRule and append messages on violation."""
    text = _section_text_or_none(body, name)

    if rule.required and (text is None or not text.strip()):
        result.add(
            ValidationMessage(
                code=f"DOR_{_slug(name)}_MISSING",
                severity=Verdict.BLOCK,
                field=name,
                message=(
                    f'Section "{name}" is required but missing or empty. '
                    f"Fill it in the task body before transitioning."
                ),
            ),
        )
        return  # downstream checks need text content

    if text is None:
        return  # not required and absent — fine

    stripped = text.strip()

    if rule.min_chars and len(stripped) < rule.min_chars:
        result.add(
            ValidationMessage(
                code=f"DOR_{_slug(name)}_TOO_SHORT",
                severity=Verdict.BLOCK,
                field=name,
                message=(
                    f'Section "{name}" has {len(stripped)} chars; needs '
                    f"at least {rule.min_chars}. Be more specific."
                ),
            ),
        )

    for sub in rule.forbid_substrings:
        if sub in stripped:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_PLACEHOLDER",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" still contains placeholder '
                        f'text "{sub}". Replace with real content.'
                    ),
                ),
            )

    for pat in rule.forbid_regex:
        try:
            if re.search(pat, stripped):
                result.add(
                    ValidationMessage(
                        code=f"DOR_{_slug(name)}_PLACEHOLDER",
                        severity=Verdict.BLOCK,
                        field=name,
                        message=(
                            f'Section "{name}" matches forbidden pattern '
                            f"/{pat}/. Replace with real content."
                        ),
                    ),
                )
        except re.error:
            # Bad regex in config — fail loud at validate-time but surface
            # as PASS so a config typo doesn't block real work.
            continue

    for sub in rule.required_subitems:
        if sub not in stripped:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_SUBITEM_MISSING",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" must include "{sub}". '
                        f"Acceptance follows the G/W/T template."
                    ),
                ),
            )

    if rule.min_items:
        items = _count_list_items(stripped)
        if items < rule.min_items:
            result.add(
                ValidationMessage(
                    code=f"DOR_{_slug(name)}_TOO_FEW_ITEMS",
                    severity=Verdict.BLOCK,
                    field=name,
                    message=(
                        f'Section "{name}" has {items} bullet(s); needs at least {rule.min_items}.'
                    ),
                ),
            )

    if name == "Read First" and project_root:
        missing = _read_first_missing_paths(stripped, project_root)
        if missing:
            shown = ", ".join(missing[:5])
            more = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
            result.add(
                ValidationMessage(
                    code="DOR_READ_FIRST_DEAD_LINK",
                    severity=Verdict.WARN,
                    field=name,
                    message=(
                        f"Read First references {len(missing)} path(s) that don't exist: "
                        f"{shown}{more}. Fix or drop them — a bogus Read First misleads the implementer."
                    ),
                ),
            )


# Repo-path shapes worth existence-checking: a markdown link target, or a bare
# path rooted at a known top dir. Prose, URLs, globs, #anchors and :line suffixes
# are ignored / normalised so only real files are stat'd (the check is WARN-only,
# so a CWD mismatch never blocks legitimate work).
_READ_FIRST_PATH_RE = re.compile(
    r"\]\(([^)]+)\)"
    r"|((?:src|docs|tests|infrastructure|scripts|\.github)/[\w./-]+)"
)


def _read_first_missing_paths(text: str, project_root: str) -> list[str]:
    from pathlib import Path

    root = Path(project_root)
    missing: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        if not line.lstrip().startswith("- "):
            continue
        for m in _READ_FIRST_PATH_RE.finditer(line):
            raw = (m.group(1) or m.group(2) or "").strip()
            if not raw or raw in seen:
                continue
            if raw.startswith(("http://", "https://", "#", "mailto:")) or "*" in raw:
                continue
            cand = raw.split("#", 1)[0].split(":", 1)[0].strip().rstrip("),.")
            if "/" not in cand:
                continue
            seen.add(raw)
            if not (root / cand).exists():
                missing.append(cand)
    return missing


def _slug(name: str) -> str:
    """Section name → uppercase ASCII tag for error codes."""
    return re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


# ────────────────────────────────────────────────────────────────────
# DoR / DoD entry points
# ────────────────────────────────────────────────────────────────────


def evaluate_dor(
    kind: str,
    body: str,
    config: GatesConfig,
    project_root: str | None = None,
) -> ValidationResult:
    """Check a task body against Definition-of-Ready for its kind.

    `project_root`, when given, enables the Read First dead-link check (paths
    are stat'd against it). Pure unit tests omit it and skip the filesystem
    touch; the real transition path passes the task's repo root.
    """
    result = ValidationResult()
    rules: DoRKindRules = config.definition_of_ready.for_kind(kind)
    for name, rule in rules.sections.items():
        if rule is None:
            continue
        _evaluate_section(name, rule, body, result, project_root)
    return result


def _acceptance_gap(kind: str, body: str, config: GatesConfig) -> Verdict | None:
    # BLOCK / WARN / None for the DoD acceptance-completeness check. Severity is
    # derived from the same DoR config that decides whether a kind has a binding
    # Acceptance section (no separate kind list to drift), so DoD stays symmetric
    # with the DoR gate: a kind whose DoR requires Acceptance BLOCKs on a
    # missing/malformed G/W/T; a kind that opts out (docs/chore/spike) only WARNs.
    dor = config.definition_of_ready.for_kind(kind)
    kind_rule = dor.sections.get("Acceptance")
    requires = kind_rule is not None and kind_rule.required
    # Well-formedness tokens come from config (kind rule, else the default) —
    # never hardcoded — so "well-formed" here matches what DoR enforced at
    # in_progress.
    rule = kind_rule or config.definition_of_ready.default.sections.get("Acceptance")
    subitems = rule.required_subitems if rule else []
    forbidden = rule.forbid_substrings if rule else []
    text = _section_text_or_none(body, "Acceptance")
    stripped = (text or "").strip()
    well_formed = (
        bool(stripped)
        and all(token in stripped for token in subitems)
        and not any(bad in stripped for bad in forbidden)
    )
    if well_formed:
        return None
    return Verdict.BLOCK if requires else Verdict.WARN


def evaluate_dod(
    kind: str,
    *,
    body: str,
    has_recent_verify: bool,
    verify_age_seconds: int | None,
    has_work_log: bool,
    config: GatesConfig,
) -> ValidationResult:
    """Check Definition-of-Done state for a kind.

    The validator does not read the verify file or DB itself — it accepts
    booleans/ages from the caller. This keeps the validator pure and
    testable without filesystem fixtures. `body` is threaded in so the
    acceptance-completeness gate can re-check the G/W/T section at complete.
    """
    result = ValidationResult()
    rules: DoDKindRules = config.definition_of_done.for_kind(kind)

    if rules.require_acceptance_met:
        gap = _acceptance_gap(kind, body, config)
        if gap is not None:
            result.add(
                ValidationMessage(
                    code="DOD_ACCEPTANCE_MISSING",
                    severity=gap,
                    field="Acceptance",
                    message=(
                        f"Definition of Done: kind={kind!r} is completing without a "
                        f"well-formed Acceptance (Given/When/Then) section — the "
                        f"acceptance criteria ARE the definition of done. Fill or fix "
                        f"the Acceptance block before task-done."
                    ),
                ),
            )

    if rules.require_verify:
        if not has_recent_verify:
            result.add(
                ValidationMessage(
                    code="DOD_VERIFY_MISSING",
                    severity=Verdict.BLOCK,
                    message=(
                        f"Definition of Done: kind={kind!r} requires a "
                        f"recent verify run. None recorded. Run `make verify` "
                        f"(or the matrix command) before task-done."
                    ),
                ),
            )
        elif verify_age_seconds is not None and verify_age_seconds > rules.verify_max_age_seconds:
            result.add(
                ValidationMessage(
                    code="DOD_VERIFY_STALE",
                    severity=Verdict.BLOCK,
                    message=(
                        f"Verify is {verify_age_seconds}s old; max allowed "
                        f"is {rules.verify_max_age_seconds}s. Re-run verify."
                    ),
                ),
            )

    if rules.require_work_log and not has_work_log:
        result.add(
            ValidationMessage(
                code="DOD_WORK_LOG_MISSING",
                severity=Verdict.WARN,
                message=(
                    f"Definition of Done: kind={kind!r} expects at least "
                    f"one Work Log entry. Append a one-liner before "
                    f"task-done."
                ),
            ),
        )
    return result


# ────────────────────────────────────────────────────────────────────
# High-level entry point — used by hook + workflow alike
# ────────────────────────────────────────────────────────────────────


def validate_transition(
    *,
    task_id: str,
    kind: str,
    body: str,
    new_status: str,
    config: GatesConfig,
    has_recent_verify: bool = False,
    verify_age_seconds: int | None = None,
    has_work_log: bool = False,
    override_reason: str | None = None,
    override_actor: str | None = None,
    project_root: str | None = None,
) -> ValidationResult:
    """Single dispatch: route to the right evaluator based on `new_status`.

    Override semantics: if `COS_DOR_OVERRIDE=1` (or DoD/WIP/verify equivalents)
    is set in the environment, AND `override_reason` is provided and meets
    policy, the gate's BLOCK messages are downgraded to WARN. Otherwise the
    override request is rejected and the original BLOCK stands.

    `task_id` is unused today but accepted so future audit emission can
    correlate with the DB row without an extra parameter.
    """
    del task_id  # reserved for audit emission — see

    if new_status == "in_progress":
        result = evaluate_dor(kind, body, config, project_root=project_root)
        gate_name = "dor"
        env_flag = "COS_DOR_OVERRIDE"
    elif new_status == "complete":
        result = evaluate_dod(
            kind,
            body=body,
            has_recent_verify=has_recent_verify,
            verify_age_seconds=verify_age_seconds,
            has_work_log=has_work_log,
            config=config,
        )
        gate_name = "dod"
        env_flag = "COS_VERIFY_OVERRIDE"
    else:
        # Other transitions (testing, blocked, icebox, emergency) have no
        # body-based gate today.  WIP cap is checked elsewhere.
        return result_pass()

    if not result.blocked:
        return result

    if os.environ.get(env_flag) != "1":
        return result

    override_result, _ = evaluate_override(
        gate_name,
        reason=override_reason,
        actor=override_actor,
        config=config,
    )
    if override_result.blocked:
        # Override request itself was rejected — keep the gate blocking
        # AND surface the override-rejection reason.
        for msg in override_result.messages:
            result.add(msg)
        return result

    # Valid override — downgrade BLOCK messages to WARN so the audit row
    # captures what was bypassed.
    downgraded = ValidationResult()
    for m in result.messages:
        downgraded.add(
            ValidationMessage(
                code=m.code,
                severity=Verdict.WARN if m.severity is Verdict.BLOCK else m.severity,
                field=m.field,
                message=f"[OVERRIDDEN] {m.message}",
            ),
        )
    return downgraded


def result_pass() -> ValidationResult:
    return ValidationResult()


__all__ = [
    "OverrideRequest",
    "ValidationMessage",
    "ValidationResult",
    "Verdict",
    "evaluate_dod",
    "evaluate_dor",
    "evaluate_override",
    "result_pass",
    "validate_transition",
]
