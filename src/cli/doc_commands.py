"""Doc lifecycle CLI — cos doc-new / doc-history / doc-lint.

Thin wrappers so the doc lifecycle is tool-driven, not hand-copied:
doc-new scaffolds the canonical header + opening block + nav; doc-history
shells `git log --follow`; doc-lint runs audit_doc_links.py and docs-lint.sh,
or the full `make docs-lint` (memory and module-tag checks too) in the coding-os
checkout this cos runs from.
No new parsers — the existing scripts + git are the engines.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import click

from cli._skill_project import _find_project_root

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "core" / "scripts"
_DOCS_LINT = _SCRIPTS_DIR / "docs-lint.sh"
_LINK_AUDIT = _SCRIPTS_DIR / "audit_doc_links.py"

_HEADER_TEMPLATE = """<!-- domain:{domain} | layer:{layer} | ssot:{ssot} | updated:{updated} -->
# {title}

Purpose: {{{{one-line purpose — what this doc is the SSOT for}}}}
Read when: {{{{when an agent should open this doc}}}}

> Nav: {nav}

{{{{first paragraph — fill in}}}}
"""


def _title_from_path(path: Path) -> str:
    words = path.stem.replace("-", " ").replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else path.stem


def _nav_for(path: Path) -> str:
    parts = path.parts
    if "docs" in parts:
        sub_dirs = parts[parts.index("docs") + 1 : -1]
    else:
        sub_dirs = ()
    up = "../" * len(sub_dirs) if sub_dirs else "./"
    nav = f"[docs/]({up})"
    if sub_dirs:
        nav += f" · [{sub_dirs[-1]}/](./)"
    return nav


@click.command("doc-new")
@click.option(
    "--layer",
    required=True,
    help="Doc layer: engineering / governance / architecture / playbooks / ...",
)
@click.option(
    "--path",
    "target",
    required=True,
    type=click.Path(),
    help="Target path, e.g. docs/engineering/foo.md",
)
@click.option("--title", default="", help="Doc title (default: derived from the filename).")
@click.option("--domain", default="CORE", show_default=True, help="Domain tag for the header.")
@click.option(
    "--ssot/--no-ssot", default=True, show_default=True, help="Mark the doc as a source of truth."
)
@click.option("--force", is_flag=True, help="Overwrite the file if it already exists.")
def doc_new_cmd(layer: str, target: str, title: str, domain: str, ssot: bool, force: bool) -> None:
    """Scaffold a new doc with the canonical header, opening block, and nav breadcrumb."""
    path = Path(target)
    if path.exists() and not force:
        click.echo(f"ERROR: {path} already exists (use --force to overwrite)", err=True)
        sys.exit(1)
    body = _HEADER_TEMPLATE.format(
        domain=domain.upper(),
        layer=layer.lower(),
        ssot=str(ssot).lower(),
        updated=date.today().isoformat(),
        title=title or _title_from_path(path),
        nav=_nav_for(path),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    click.echo(f"created {path} — fill the {{{{...}}}} placeholders, then `cos doc-lint {path}`")


@click.command("doc-history")
@click.argument("path", type=click.Path())
@click.option("-n", "--max-count", default=20, show_default=True, help="Max revisions to show.")
@click.option("--show", is_flag=True, help="Include the full diff of each revision (git log -p).")
def doc_history_cmd(path: str, max_count: int, show: bool) -> None:
    """Show the git revision history of a doc (git log --follow), oldest renames included."""
    cmd = ["git", "log", "--follow", f"-{max_count}", "--date=short"]
    if show:
        cmd.append("-p")
    else:
        cmd.append("--pretty=format:%h  %ad  %an  %s")
    cmd += ["--", path]
    sys.exit(subprocess.run(cmd).returncode)


@click.command("doc-lint")
@click.argument("paths", nargs=-1, type=click.Path())
def doc_lint_cmd(paths: tuple[str, ...]) -> None:
    """Lint the given docs, or with no paths every link, anchor and header in the project; exits non-zero on errors."""
    if not _DOCS_LINT.exists():
        click.echo(f"ERROR: docs-lint.sh not found at {_DOCS_LINT}", err=True)
        sys.exit(1)
    if paths:
        sys.exit(subprocess.run(["bash", str(_DOCS_LINT), *paths]).returncode)
    root = _find_project_root()
    if root.resolve() == Path(__file__).resolve().parents[2]:
        sys.exit(subprocess.run(["make", "docs-lint"], cwd=root).returncode)
    if not (root / "docs").is_dir():
        raise click.ClickException(f"no docs/ in {root} — nothing to lint")
    links = subprocess.run([sys.executable, str(_LINK_AUDIT), "--root", str(root)]).returncode
    headers = subprocess.run(
        ["bash", str(_DOCS_LINT)], cwd=root, env={**os.environ, "DOCS_DIR": "docs"}
    ).returncode
    sys.exit(links or headers)
