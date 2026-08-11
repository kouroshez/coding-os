"""doctor check: the cognition registries — roles, presets, situations, agents.

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

    - roles/F{1..11}_*.yaml all exist with id + activation + prompt_prefix
    - presets/registry.yaml parses and has ≥8 curated presets
    - situations/registry.yaml parses and has ≥6 situations
    - agents/F{1..11}_*.md all exist with valid YAML frontmatter
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

    # Role registry (primary, semantic names)
    roles_dir = thinking_os / "roles"
    if not roles_dir.is_dir():
        issues.append("roles/ directory missing")
    else:
        for role in _EXPECTED_ROLES:
            yaml_file = roles_dir / f"{role}.yaml"
            if not yaml_file.exists():
                issues.append(f"roles/{role}.yaml missing")
                continue
            try:
                import yaml as _yaml

                data = _yaml.safe_load(yaml_file.read_text()) or {}
                if data.get("id") != role:
                    issues.append(f"{yaml_file.name}: id mismatch (expected {role})")
                for required in (
                    "activation",
                    "prompt_prefix",
                    "criteria_required",
                    "intensity_steps",
                ):
                    if required not in data:
                        issues.append(f"{yaml_file.name}: missing '{required}'")
            except Exception as exc:
                issues.append(f"{yaml_file.name}: invalid YAML: {exc}")

    # Preset registry
    preset_reg = thinking_os / "presets" / "registry.yaml"
    if not preset_reg.exists():
        issues.append("presets/registry.yaml missing")
    else:
        try:
            import yaml as _yaml

            data = _yaml.safe_load(preset_reg.read_text()) or {}
            presets = data.get("presets", []) if isinstance(data, dict) else []
            count = len(presets) if isinstance(presets, list) else 0
            if count < 8:
                issues.append(f"presets/registry.yaml has {count} presets (need ≥8)")
            else:
                # Validate preset shape
                for preset in presets:
                    if "id" not in preset or "match" not in preset or "score" not in preset:
                        issues.append(f"preset malformed: {preset.get('id', '?')}")
                        break
        except Exception as exc:
            issues.append(f"presets/registry.yaml invalid YAML: {exc}")

    # Situation registry
    situation_reg = thinking_os / "situations" / "registry.yaml"
    if not situation_reg.exists():
        issues.append("situations/registry.yaml missing")
    else:
        try:
            import yaml as _yaml

            data = _yaml.safe_load(situation_reg.read_text()) or {}
            situations = data.get("situations", []) if isinstance(data, dict) else []
            count = len(situations) if isinstance(situations, list) else 0
            if count < 6:
                issues.append(f"situations/registry.yaml has {count} situations (need ≥6)")
        except Exception as exc:
            issues.append(f"situations/registry.yaml invalid YAML: {exc}")

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
                f"Roles/presets/situations OK (11 roles, 12+ presets, 6 situations, 11 agents); {'; '.join(warnings)}",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "cognition.registries_present",
                SEV_PASS,
                "Cognition registries: 11 roles, 12+ presets, 6 situations, 11 formula-agents — all valid",
            )
        )

