"""`cos setup` — bootstrap project docs after `cos init`.

Fills the gap between "scaffolded structure" and "enough doc content for
the agent to start working". Three modes:

  interactive — ask 5 questions, write 4 PRD files
  import-prd  — read an existing PRD file, split by keywords → docs/prd/
  skip        — no-op, return helpful pointer

Pure-Python, no LLM call. The `import-prd` path uses keyword routing to
map H2 sections to numbered PRD files. Nothing is overwritten — existing
files are preserved and the conflicting sections are collected under
`docs/prd/99-misc.md`.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
from pathlib import Path

import click
import yaml

CONFIG_FILE = ".coding-os.yaml"


# ---------------------------------------------------------------------------
# Classifier: heading keyword → target file
# ---------------------------------------------------------------------------

PRD_CLASSIFIER: dict[str, tuple[str, ...]] = {
    "01-snapshot-vision.md": ("vision", "elevator", "pitch", "overview", "snapshot"),
    "02-goals-kpis.md": ("goal", "kpi", "metric", "objective", "target", "success criteria"),
    "03-users-jobs.md": ("persona", "user", "audience", "customer", "jtbd", "jobs to be done"),
    "04-information-architecture.md": (
        "information architecture",
        "page tree",
        "navigation",
        "sitemap",
    ),
    "05-ux-conversion.md": ("ux", "conversion", "funnel", "user flow", "journey"),
    "06-product-pricing.md": ("pricing", "plan", "tier", "packaging", "revenue"),
    "07-policies-legal.md": ("legal", "policy", "terms", "compliance", "privacy", "gdpr"),
    "08-functional-requirements.md": ("requirement", "feature", "functional"),
    "09-data-model-apis.md": ("data model", "api", "schema", "entity", "contract"),
    "10-nfr-implementation.md": ("nfr", "non-functional", "performance", "security", "scale"),
    "11-appendices.md": ("appendix", "glossary", "reference", "acknowledg"),
}


def _load_config(project: Path) -> dict:
    path = project / CONFIG_FILE
    if not path.exists():
        raise click.ClickException(f"Not a coding-os project ({CONFIG_FILE} missing in {project})")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ---------------------------------------------------------------------------
# Mode: skip
# ---------------------------------------------------------------------------


def _run_skip(project: Path) -> None:
    click.echo(
        "Skipped. Docs scaffold is untouched.\n"
        "When ready: `cos setup` to bootstrap, or write docs/prd/*.md by hand."
    )


# ---------------------------------------------------------------------------
# Mode: interactive wizard
# ---------------------------------------------------------------------------


def _interactive_vision(project: Path) -> dict[str, str]:
    click.echo("\n=== Interactive PRD Setup ===")
    vision = click.prompt(
        "Project vision (one paragraph)",
        type=str,
        default="",
        show_default=False,
    )
    goals = click.prompt(
        "Top 3 KPIs (comma-separated)",
        type=str,
        default="",
        show_default=False,
    )
    persona = click.prompt(
        "Primary persona (who uses this?)",
        type=str,
        default="",
        show_default=False,
    )
    features = click.prompt(
        "Core features (comma-separated, optional)",
        type=str,
        default="",
        show_default=False,
    )
    return {
        "vision": vision,
        "goals": goals,
        "persona": persona,
        "features": features,
    }


def _render_vision_md(date: str, content: dict[str, str]) -> str:
    return (
        f"<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{date} -->\n"
        f"# Snapshot & Vision\n\n"
        f"Purpose: One-paragraph elevator pitch + medium-term vision.\n"
        f"Read when: Onboarding, aligning stakeholders on scope.\n"
        f"Skip when: The task is a pure implementation detail.\n"
        f"Read next: `02-goals-kpis.md`\n\n"
        f"> Nav: [PRD Index](./00-index.md)\n\n"
        f"## Vision\n\n"
        f"{content.get('vision') or '_(not provided — fill in before first feature task)_'}\n"
    )


def _render_goals_md(date: str, content: dict[str, str]) -> str:
    goals_raw = content.get("goals", "").strip()
    bullet_lines = (
        "\n".join(f"- {g.strip()}" for g in goals_raw.split(",") if g.strip())
        if goals_raw
        else "- _(not yet defined)_"
    )
    return (
        f"<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{date} -->\n"
        f"# Goals & KPIs\n\n"
        f"Purpose: Measurable outcomes that define product success.\n"
        f"Read when: Prioritizing work, reviewing trade-offs.\n"
        f"Skip when: Implementation-only task with no strategic dimension.\n"
        f"Read next: `03-users-jobs.md`\n\n"
        f"> Nav: [PRD Index](./00-index.md)\n\n"
        f"## Primary KPIs\n\n{bullet_lines}\n"
    )


def _render_users_md(date: str, content: dict[str, str]) -> str:
    persona = content.get("persona", "").strip() or "_(to be defined)_"
    return (
        f"<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{date} -->\n"
        f"# Users & Jobs-to-be-Done\n\n"
        f"Purpose: Who we build for and what they hire the product to do.\n"
        f"Read when: Feature discovery, acceptance criteria writing.\n"
        f"Skip when: Purely internal tooling with one stakeholder.\n"
        f"Read next: `04-information-architecture.md`\n\n"
        f"> Nav: [PRD Index](./00-index.md)\n\n"
        f"## Primary Persona\n\n{persona}\n\n"
        f"## Jobs-to-be-Done\n\n"
        f"- _(list the jobs they come to the product to get done)_\n"
    )


def _render_features_md(date: str, content: dict[str, str]) -> str:
    features_raw = content.get("features", "").strip()
    bullet_lines = (
        "\n".join(f"- {f.strip()}" for f in features_raw.split(",") if f.strip())
        if features_raw
        else "- _(none declared yet — add features as they're planned)_"
    )
    return (
        f"<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{date} -->\n"
        f"# Functional Requirements\n\n"
        f"Purpose: Feature inventory with priority and scope.\n"
        f"Read when: Planning tasks, scoping epics.\n"
        f"Skip when: Only touching internals with no feature implication.\n"
        f"Read next: `09-data-model-apis.md`\n\n"
        f"> Nav: [PRD Index](./00-index.md)\n\n"
        f"## Core Features\n\n{bullet_lines}\n"
    )


def _run_interactive(project: Path) -> int:
    answers = _interactive_vision(project)
    date = _dt.date.today().isoformat()
    prd_dir = project / "docs" / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    writes = {
        "01-snapshot-vision.md": _render_vision_md(date, answers),
        "02-goals-kpis.md": _render_goals_md(date, answers),
        "03-users-jobs.md": _render_users_md(date, answers),
        "08-functional-requirements.md": _render_features_md(date, answers),
    }
    written = 0
    for name, content in writes.items():
        target = prd_dir / name
        if target.exists():
            click.echo(f"  SKIP existing: docs/prd/{name}")
            continue
        target.write_text(content, encoding="utf-8")
        written += 1
        click.echo(f"  Wrote docs/prd/{name}")
    return written


# ---------------------------------------------------------------------------
# Mode: import-prd (pure structural parsing, no LLM)
# ---------------------------------------------------------------------------


_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _parse_markdown_sections(content: str) -> list[tuple[str, str]]:
    """Split markdown into [(h2_title, body), ...].

    H2 is the granularity — each H2 block becomes a candidate "section".
    Content before the first H2 is ignored (usually just the H1 + intro).
    """
    lines = content.splitlines(keepends=True)
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_body: list[str] = []
    for line in lines:
        m = _H2_RE.match(line)
        if m:
            if current_title is not None:
                sections.append((current_title, current_body))
            current_title = m.group(1).strip()
            current_body = []
        elif current_title is not None:
            current_body.append(line)
    if current_title is not None:
        sections.append((current_title, current_body))
    return [(title, "".join(body)) for title, body in sections]


def _classify_section(title: str) -> str:
    """Return the target filename for this H2 title, or '99-misc.md'."""
    lower = title.lower()
    for target, keywords in PRD_CLASSIFIER.items():
        if any(kw in lower for kw in keywords):
            return target
    return "99-misc.md"


def _build_prd_file_content(date: str, target: str, grouped: list[tuple[str, str]]) -> str:
    header_title = target.replace(".md", "").replace("-", " ").title()
    # Strip leading numeric prefix like "01 " for display title.
    pretty = re.sub(r"^\d+\s+", "", header_title)
    parts = [
        f"<!-- domain:PRODUCT | layer:spec | ssot:true | updated:{date} -->",
        f"# {pretty}",
        "",
        f"Purpose: Imported from legacy PRD on {date}.",
        "Read when: Feature work in this area.",
        f"Skip when: Task is not related to {pretty.lower()}.",
        "Read next: The next numbered PRD file.",
        "",
        "> Nav: [PRD Index](./00-index.md)",
        "",
    ]
    for title, body in grouped:
        parts.append(f"## {title}")
        parts.append("")
        parts.append(body.rstrip())
        parts.append("")
    return "\n".join(parts) + "\n"


def _run_import_prd(project: Path, source: Path, yes: bool) -> int:
    if not source.exists():
        raise click.ClickException(f"Source PRD not found: {source}")
    raw = source.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(raw)
    if not sections:
        raise click.ClickException(
            f"No H2 sections found in {source}. The importer splits on `## `."
        )

    # Group sections by target file.
    grouped: dict[str, list[tuple[str, str]]] = {}
    for title, body in sections:
        target = _classify_section(title)
        grouped.setdefault(target, []).append((title, body))

    click.echo(f"\nProposed layout for {source.name} ({len(sections)} sections):")
    for target in sorted(grouped):
        titles = ", ".join(t for t, _ in grouped[target])
        if len(titles) > 60:
            titles = titles[:57] + "..."
        click.echo(f"  docs/prd/{target:36s} ← {titles}")

    if not yes and not click.confirm("Proceed?", default=True):
        click.echo("Aborted.")
        return 0

    date = _dt.date.today().isoformat()
    prd_dir = project / "docs" / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for target, rows in sorted(grouped.items()):
        out = prd_dir / target
        if out.exists():
            click.echo(f"  SKIP existing: docs/prd/{target}")
            continue
        out.write_text(_build_prd_file_content(date, target, rows), encoding="utf-8")
        written += 1
        click.echo(f"  Wrote docs/prd/{target}")
    return written


# ---------------------------------------------------------------------------
# Post-setup: make docs-index (best-effort)
# ---------------------------------------------------------------------------


def _post_setup(project: Path) -> None:
    mk = project / "Makefile"
    if not mk.exists():
        return
    try:
        subprocess.run(
            ["make", "docs-index"],
            cwd=str(project),
            check=False,
            capture_output=True,
            timeout=60,
        )
        click.echo("  Ran `make docs-index` (best-effort)")
    except Exception:  # pragma: no cover
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command("setup")
@click.option("--project-dir", "-d", default=".", help="Project directory")
@click.option(
    "--mode",
    type=click.Choice(["interactive", "import-prd", "skip"]),
    default=None,
    help="Bootstrap mode. Prompted if omitted.",
)
@click.option("--source", default=None, help="Path to existing PRD file (for --mode import-prd)")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompts")
def setup(
    project_dir: str,
    mode: str | None,
    source: str | None,
    yes: bool,
) -> None:
    """Bootstrap project docs after `cos init`.

    Writes initial PRD files (01-snapshot-vision, 02-goals-kpis, etc.)
    either by asking short questions, by splitting an existing PRD, or by
    skipping. Idempotent — never overwrites existing files.
    """
    project = Path(project_dir).resolve()
    _ = _load_config(project)  # raises if not a coding-os project

    if mode is None:
        if yes:
            raise click.ClickException("--mode is required with --yes")
        mode = click.prompt(
            "Setup mode",
            type=click.Choice(["interactive", "import-prd", "skip"]),
            default="interactive",
        )

    if mode == "skip":
        _run_skip(project)
        return

    if mode == "import-prd":
        if source is None:
            if yes:
                raise click.ClickException("--source is required with --mode import-prd --yes")
            source = click.prompt("Path to PRD file", type=str)
        written = _run_import_prd(project, Path(source).expanduser(), yes)
    else:  # interactive
        written = _run_interactive(project)

    if written > 0:
        _post_setup(project)
        click.echo(f"\nSetup complete. {written} file(s) written.")
        click.echo('Next: review docs/prd/*, then `cos task-create --title "..." --swimlane <lane> --kind <kind>`')
    else:
        click.echo("\nNo files written (all already existed).")
