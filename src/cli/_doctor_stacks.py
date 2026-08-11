"""doctor checks over the stack registry — declared stacks resolve, categories
balance, and every stack skill is linked into the agent surface.

Private sibling of cli.doctor; the checks are re-exported by
`cli.doctor_checks_registry`.
"""

from __future__ import annotations

from pathlib import Path

from cli._resources import adapters_dir, templates_dir

from ._doctor_shared import (
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    CheckResult,
    DoctorReport,
)


def _check_stack_registry_consistency(report: DoctorReport) -> None:
    """stack.registry_valid — every stack declared in .coding-os.yaml::templates exists in the registry.

    If a stack was installed and later removed from the coding-os distribution,
    the project config still lists it — FAIL so the user knows to either add
    the stack back or remove it from their config.
    """
    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_WARN,
                f"could not load stack registry: {exc}",
            )
        )
        return

    missing = [t for t in report.templates if t not in registry]
    if missing:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_FAIL,
                f"stacks in config not found in templates/: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    elif not report.templates:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                "no stacks installed (base-only project)",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                f"all {len(report.templates)} installed stack(s) present in registry",
                {"installed": report.templates},
            )
        )


def _check_category_balance(report: DoctorReport) -> None:
    """stack.category_balance — informational WARN when two or more stacks of the same category
    are installed (e.g. two backend stacks). The project will work, but the
    later stack wins on conflicting substitution keys — the user should know."""
    if len(report.templates) < 2:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "single-stack or base-only project",
            )
        )
        return

    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "registry unavailable, skipping",
            )
        )
        return

    categories: dict[str, list[str]] = {}
    for stack_id in report.templates:
        if stack_id in registry:
            cat = registry[stack_id].category
            categories.setdefault(cat, []).append(stack_id)

    duplicates = {c: ids for c, ids in categories.items() if len(ids) >= 2}
    if duplicates:
        details = ", ".join(f"{cat}: {', '.join(ids)}" for cat, ids in duplicates.items())
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_WARN,
                f"multiple stacks in same category ({details}) — last stack wins on conflicts",
                {"duplicates": duplicates},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                f"{len(report.templates)} stacks in {len(categories)} distinct categories",
            )
        )


def _check_stack_skills_linked(project: Path, report: DoctorReport) -> None:
    """stack.skills_linked — every installed stack's skills are symlinked into the agent's skills dir.

    Detects the B1 regression where `.claude/skills/python-django/SKILL.md`
    was missing even though `--template django` was declared. We consult the
    adapter registry to find `skills_dir` (null for Codex → skip check) and
    the src/templates/<stack>/skills/ source of truth.
    """
    if not report.templates:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no stacks installed"))
        return
    if not report.agent:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no agent configured"))
        return
    try:
        from cli.adapter_registry import load_adapter_registry

        adapters = load_adapter_registry(adapters_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return
    profile = adapters.get(report.agent)
    if profile is None or not profile.skills_dir:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"adapter '{report.agent}' has no skills_dir — skipped",
            )
        )
        return

    skills_dir = project / profile.skills_dir
    expected: list[tuple[str, str]] = []  # (stack, skill_name)
    for stack in report.templates:
        stack_skills = templates_dir(stack, "skills")
        if not stack_skills.exists():
            continue
        for entry in stack_skills.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                expected.append((stack, entry.name))

    if not expected:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                "no stack skills to link",
            )
        )
        return

    missing = []
    for stack, name in expected:
        link = skills_dir / name / "SKILL.md"
        if not link.exists():
            missing.append(f"{stack}:{name}")

    if missing:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_FAIL,
                f"missing stack skill links: {', '.join(missing)} — run `cos update` to repair",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"all {len(expected)} stack skill(s) linked",
            )
        )
