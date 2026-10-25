"""doctor check: the formula-agent role definitions dispatch reads.

Private sibling of cli.doctor; the check is re-exported by
`cli.doctor_checks_runtime`.
"""

from __future__ import annotations

from pathlib import Path

from ._doctor_shared import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)


def _check_cognition_registries(project: Path, report: DoctorReport) -> None:
    """cognition.registries_present — Cognition registries valid.

    - agents/<role>.md all exist with valid YAML frontmatter and a matching id
    """
    import re as _re

    thinking_os = project / "src" / "core" / "thinking_os"
    if not thinking_os.is_dir():
        report.checks.append(
            CheckResult("cognition.registries_present", SEV_PASS, "no thinking_os/ (skip)")
        )
        return

    issues: list[str] = []
    warnings: list[str] = []

    _EXPECTED_ROLES = [
        "researcher",
        "analyst",
        "architect",
        "documenter",
        "implementer",
        "reviewer",
        "debugger",
        "security_auditor",
        "deployer",
        "observer",
        "refactorer",
    ]

    # Formula-agent files (semantic names — one file per role; reuses _EXPECTED_ROLES above)
    agents_dir = thinking_os / "agents"
    _ROLE_ID_RE = _re.compile(r"^id:\s*(\w+)", _re.MULTILINE)
    for role in _EXPECTED_ROLES:
        agent_file = agents_dir / f"{role}.md"
        if not agent_file.exists():
            issues.append(f"agents/{role}.md missing")
            continue
        content = agent_file.read_text(encoding="utf-8")
        if not content.startswith("---"):
            issues.append(f"{agent_file.name}: missing YAML frontmatter")
        else:
            m = _ROLE_ID_RE.search(content)
            if not m or m.group(1) != role:
                issues.append(f"{agent_file.name}: missing or wrong 'id: {role}' in frontmatter")

    if issues:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_FAIL,
                "; ".join(issues),
                {"issues": issues, "warnings": warnings},
            )
        )
    elif warnings:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_WARN,
                f"Role definitions OK (11 agents); {'; '.join(warnings)}",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_PASS,
                "Role definitions: 11 formula-agents — all valid",
            )
        )
