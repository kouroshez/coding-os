"""`cos stack-lint [<id>]` — factory-contract completeness check (TASK-361).

Contract SSOT: docs/playbooks/template-authoring.md § Stack bundle standard.
Hard rules exit non-zero (CI gate); soft rules print GAP lines so a stack's
completeness is visible without blocking iteration.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import click

from cli._resources import core_dir, templates_dir
from cli.stack_registry import StackProfile, load_stack_registry

_CODE_CATEGORIES = frozenset({"backend", "frontend", "mobile"})
_CATEGORY_VERIFY_KEY = {
    "backend": "VERIFY_BACKEND",
    "frontend": "VERIFY_FRONTEND",
    "mobile": "VERIFY_MOBILE",
}

# A code stack ships a buildable seed; map its language to the manifest names
# that make `cos init` output compile/run without hand-wiring.
_RUNTIME_MANIFESTS = {
    "python": ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
    "go": ("go.mod",),
    "typescript": ("package.json",),
    "javascript": ("package.json",),
    "rust": ("Cargo.toml",),
    "java": ("pom.xml", "build.gradle", "build.gradle.kts"),
    "kotlin": ("build.gradle.kts", "build.gradle", "pom.xml"),
    "ruby": ("Gemfile",),
    "php": ("composer.json",),
    "dart": ("pubspec.yaml",),
    "csharp": ("*.csproj",),
}

# A work-surface stack ships at least one runnable sample test so `cos init`
# output is green on day one. Map language -> the filename globs the stack's
# test runner discovers; languages that inline tests in the source file (Rust)
# are matched by a content marker instead.
_TEST_GLOBS = {
    "python": ("test_*.py", "*_test.py"),
    "go": ("*_test.go",),
    "typescript": ("*.test.ts", "*.test.tsx", "*.spec.ts", "*.spec.tsx"),
    "javascript": ("*.test.js", "*.spec.js", "*.test.mjs"),
    "java": ("*Test.java", "*Tests.java", "*IT.java"),
    "kotlin": ("*Test.kt", "*Tests.kt"),
    "ruby": ("*_test.rb", "*_spec.rb"),
    "php": ("*Test.php",),
    "dart": ("*_test.dart",),
    "csharp": ("*Test.cs", "*Tests.cs"),
}
_TEST_MARKERS = {
    "rust": (("*.rs",), ("#[cfg(test)]", "#[test]", "#[tokio::test]")),
}

# A verify command that names a linter should ship that linter's config so the
# rules are pinned, not left to whatever default the runner happens to have.
_LINT_CONFIGS = {
    "ruff": ("ruff.toml", ".ruff.toml", "pyproject.toml"),
    "eslint": (
        "eslint.config.js",
        "eslint.config.mjs",
        "eslint.config.cjs",
        "eslint.config.ts",
        ".eslintrc.json",
        ".eslintrc.js",
        ".eslintrc.cjs",
        ".eslintrc.yml",
        ".eslintrc.yaml",
    ),
    "golangci-lint": (".golangci.yml", ".golangci.yaml", ".golangci.toml"),
    "rubocop": (".rubocop.yml",),
    "phpcs": ("phpcs.xml", "phpcs.xml.dist"),
    "prettier": (
        ".prettierrc",
        ".prettierrc.json",
        ".prettierrc.yml",
        ".prettierrc.yaml",
        "prettier.config.js",
        "prettier.config.mjs",
    ),
    "clippy": ("clippy.toml", ".clippy.toml"),
}

_DOC_ROUTE_RE = re.compile(r"docs/[\w./-]+\.md")


@dataclass
class LintReport:
    stack_id: str
    hard: list[str] = field(default_factory=list)
    soft: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.hard


def _is_exempt_from_work_surfaces(profile: StackProfile) -> bool:
    """Plain-language and library stacks ship skeletons, not work surfaces."""
    return profile.category == "library" or profile.id == f"{profile.language}-plain"


def _skill_resolvable(profile: StackProfile, stack_dir: Path) -> bool:
    if not profile.primary_skill:
        return _is_exempt_from_work_surfaces(profile)
    candidates = (
        stack_dir / "skills" / profile.primary_skill / "SKILL.md",
        core_dir("skills") / profile.primary_skill / "SKILL.md",
    )
    return any(path.is_file() for path in candidates)


def _scaffold_has(scaffold: Path, names: tuple[str, ...]) -> bool:
    return scaffold.is_dir() and any(any(scaffold.rglob(name)) for name in names)


def _scaffold_has_sample_test(scaffold: Path, language: str) -> bool:
    globs = _TEST_GLOBS.get(language, ())
    if globs and _scaffold_has(scaffold, globs):
        return True
    src_globs, markers = _TEST_MARKERS.get(language, ((), ()))
    if markers and scaffold.is_dir():
        for src_glob in src_globs:
            for path in scaffold.rglob(src_glob):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if any(marker in text for marker in markers):
                    return True
    return False


def _verify_command_text(profile: StackProfile) -> str:
    parts = [
        value
        for key, value in profile.substitutions.items()
        if key.startswith("VERIFY_") and not key.endswith(("_GLOB", "_SUITES"))
    ]
    parts.extend(row.cmd for row in profile.verify)
    return " ".join(parts).lower()


def _verify_runs_test(profile: StackProfile) -> bool:
    # A stack that ships a sample test should name a test suite in the
    # VERIFY_<DOMAIN>_SUITES substitution — the source the rendered AGENTS.md
    # matrix and enforce-verify read, so a stale one silently tells the agent to
    # skip the test. The `test-*` target convention is runner-agnostic
    # (test-backend/test-frontend/...), catching an un-run test whether the
    # runner is pytest/vitest/rspec/phpunit. Reading the substitution (not the
    # verify: block) catches drift where the block was wired but the matrix left
    # stale.
    suites = " ".join(v for k, v in profile.substitutions.items() if k.endswith("_SUITES"))
    return "test" in suites.lower()


def lint_stack(
    profile: StackProfile, stack_dir: Path, golden_root: Path | None = None
) -> LintReport:
    """Apply the factory contract to one loaded stack profile."""
    report = LintReport(stack_id=profile.id)

    if not profile.language:
        report.hard.append("stack.yaml missing `language`")
    structure = profile.structure or {}
    if not structure.get("root"):
        report.hard.append("stack.yaml missing `structure.root`")
    if not structure.get("tree"):
        report.hard.append("stack.yaml missing `structure.tree`")

    if profile.category in _CODE_CATEGORIES:
        verify_key = _CATEGORY_VERIFY_KEY[profile.category]
        # The verification matrix renders from VERIFY_<CAT>_* substitutions —
        # that's the hard contract. `verify:` rows are the newer per-glob
        # mechanism (TASK-348 plain stacks); absence is a visible gap only.
        if not profile.substitutions.get(f"{verify_key}_GLOB"):
            report.hard.append(f"missing substitution `{verify_key}_GLOB`")
        if not profile.verify:
            report.soft.append("no `verify:` rows (per-glob suites — newer mechanism)")

    if profile.primary_skill and not _skill_resolvable(profile, stack_dir):
        report.hard.append(
            f"primary_skill '{profile.primary_skill}' has no SKILL.md in the stack or core skills"
        )
    if profile.primary_skill is None and not _is_exempt_from_work_surfaces(profile):
        report.hard.append("primary_skill is null but the stack is not plain/library")

    for routing_key in ("DOMAIN_ROUTES", "QUICK_ROUTING"):
        if not profile.substitutions.get(routing_key, "").strip():
            report.hard.append(f"missing substitution `{routing_key}`")

    if not _is_exempt_from_work_surfaces(profile):
        if not profile.dimensions:
            report.soft.append("no `dimensions:` rows (Classify-phase read list)")
        if not profile.skill_enforcement:
            report.soft.append("no `skill_enforcement:` globs (auto skill loading)")
        if (
            profile.category in _CODE_CATEGORIES
            and not (stack_dir / "scaffold-boundary.yaml").is_file()
        ):
            report.soft.append("no scaffold-boundary.yaml (write-boundary contract)")
        if not (stack_dir / "scaffold" / ".coding-os" / "scrumban-config.yaml").is_file():
            report.soft.append("no scrumban-config.yaml delta (board lanes)")

        scaffold_docs = stack_dir / "scaffold" / "docs"
        has_docs = scaffold_docs.is_dir() and any(scaffold_docs.rglob("*.md"))
        routes_to_playbook = "playbook" in profile.substitutions.get("DOMAIN_ROUTES", "").lower()
        if not has_docs and not routes_to_playbook:
            report.soft.append("no stack docs under scaffold/docs/ and no playbook routing")

    # --- Factory standard v2: runtime-manifest / lint-config / reference-integrity ---
    scaffold = stack_dir / "scaffold"

    # Reference integrity — a declared rule file that doesn't resolve is a dead
    # link in the rendered ruleset; checked for every stack that declares rules.
    for rule in profile.rules:
        if not (stack_dir / rule.file).is_file():
            report.hard.append(f"rules path '{rule.file}' does not resolve on disk")

    base_scaffold = templates_dir() / "_base" / "scaffold"
    # The dogfood (meta) stack routes to the repo's own docs/ rather than a
    # shipped scaffold copy — accept either location.
    repo_root = templates_dir().parent.parent
    # A repo-root doc (meta/dogfood routing) is only reachable from an editable
    # checkout; a packaged install ships no docs/ tree, so a non-resolution there
    # is unknowable, not a real dangling ref — don't HARD-fail on it.
    repo_docs_present = (repo_root / "docs").is_dir()
    routes = profile.substitutions.get("DOMAIN_ROUTES", "")
    for doc_path in dict.fromkeys(_DOC_ROUTE_RE.findall(routes)):
        resolves = (
            (scaffold / doc_path).is_file()
            or (base_scaffold / doc_path).is_file()
            or (repo_root / doc_path).is_file()
        )
        if not resolves and not (doc_path.startswith("docs/") and not repo_docs_present):
            report.hard.append(f"DOMAIN_ROUTES path '{doc_path}' does not resolve in scaffold")

    if not _is_exempt_from_work_surfaces(profile):
        if profile.category in _CODE_CATEGORIES:
            manifests = _RUNTIME_MANIFESTS.get(profile.language, ())
            if manifests and not _scaffold_has(scaffold, manifests):
                report.hard.append(
                    f"no runtime manifest ({' / '.join(manifests)}) under scaffold/"
                )
            if not _scaffold_has_sample_test(scaffold, profile.language):
                report.soft.append(
                    "no sample test under scaffold/ (a work-surface stack should "
                    "ship ≥1 runnable sample test for a green day-one `cos init`)"
                )
            elif not _verify_runs_test(profile):
                report.soft.append(
                    "ships a sample test but the verify command runs no test suite "
                    "(the test is decorative — wire a test target into verify)"
                )

        verify_text = _verify_command_text(profile)
        # Lint configs (ruff/eslint/prettier) ship once per language under
        # _base/lang/<language>/ and overlay into every consumer of that language,
        # so a config there satisfies the row as fully as a per-stack one.
        lang_bundle = templates_dir() / "_base" / "lang" / profile.language
        for linter, configs in _LINT_CONFIGS.items():
            if linter in verify_text and not (
                _scaffold_has(scaffold, configs) or _scaffold_has(lang_bundle, configs)
            ):
                report.hard.append(
                    f"verify names '{linter}' but no {linter} config ships (tool defaults)"
                )

        if profile.primary_skill:
            skill_md = stack_dir / "skills" / profile.primary_skill / "SKILL.md"
            anatomy = skill_md.parent / "references" / "anatomy.md"
            if (
                skill_md.is_file()
                and "anatomy.md" in skill_md.read_text(encoding="utf-8", errors="ignore")
                and not anatomy.is_file()
            ):
                report.soft.append(
                    f"primary skill '{profile.primary_skill}' SKILL.md references "
                    "anatomy.md but references/anatomy.md is missing"
                )

    golden_root = golden_root if golden_root is not None else Path("tests/golden")
    if golden_root.is_dir():
        sections = [p.name for p in golden_root.iterdir() if p.name.endswith(f"_{profile.id}")]
        if not sections:
            report.soft.append("no golden section (make golden-capture SECTION=<agent>_<id>)")

    return report


def lint_all(
    registry_dir: Path | None = None, golden_root: Path | None = None
) -> dict[str, LintReport]:
    root = registry_dir or templates_dir()
    # Lint ONLY the bundled stacks under `root` — a community overlay stack has
    # no golden to assert against (overlay_dirs=() opts out of the user overlay).
    registry = load_stack_registry(root, overlay_dirs=())
    reports = {
        stack_id: lint_stack(registry[stack_id], root / stack_id, golden_root)
        for stack_id in sorted(registry.keys())
    }
    # A schema-rejected stack never loads — surface the loader's precise
    # rejection as a hard failure instead of silently omitting the stack.
    for warning in registry.warnings:
        if not warning.startswith("skipping stack "):
            continue
        skipped_id = warning.split("skipping stack ", 1)[1].split(":", 1)[0].strip()
        reports.setdefault(skipped_id, LintReport(stack_id=skipped_id)).hard.append(warning)
    return reports


@click.command("stack-lint")
@click.argument("stack_id", required=False)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def stack_lint(stack_id: str | None, output_format: str) -> None:
    """Check stack bundle completeness against the factory contract."""
    reports = lint_all()
    if stack_id:
        if stack_id not in reports:
            raise click.ClickException(
                f"stack '{stack_id}' not found — available: {sorted(reports)}"
            )
        reports = {stack_id: reports[stack_id]}

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    sid: {"passed": r.passed, "hard": r.hard, "soft": r.soft}
                    for sid, r in reports.items()
                },
                indent=2,
            )
        )
    else:
        for sid, r in reports.items():
            status = "PASS" if r.passed else "FAIL"
            click.echo(f"{sid}: {status}")
            for issue in r.hard:
                click.echo(f"  HARD: {issue}")
            for gap in r.soft:
                click.echo(f"  GAP:  {gap}")

    if any(not r.passed for r in reports.values()):
        raise SystemExit(1)
