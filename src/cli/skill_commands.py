"""`cos skill new|lint|add|list|consent` — public skill standard (TASK-369).

Spec SSOT: docs/engineering/skill-architecture.md § Public skill standard.
Community skills live in ~/.coding-os/skills ($COS_USER_SKILLS_DIR override)
with a .provenance.json sidecar; the import gate normalizes vanilla
Agent-Skills files, scans for exfil/destructive patterns, and forces the
community trust tier. Scripts of community skills run only after recorded
consent.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from cli._resources import core_dir, templates_dir
from cli.skill_registry import load_skill_registry

PROVENANCE_FILENAME = ".provenance.json"

# Static exfil/destructive shapes. Defense-in-depth, not a sandbox — the
# consent tier is the second layer (skill-architecture.md § import gate).
_SECURITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"curl[^|\n]*\|\s*(ba)?sh", "piped shell-from-curl"),
    (r"wget[^|\n]*\|\s*(ba)?sh", "piped shell-from-wget"),
    (r"base64\s+(-d|--decode)[^\n]*\|\s*(ba)?sh", "base64-decoded shell execution"),
    (r"\beval\s*\(\s*atob", "base64+eval execution"),
    (r"rm\s+-rf\s+[/~]", "destructive recursive delete at root/home"),
    (
        r"(curl|wget|fetch)[^\n]*\$(\{)?(ANTHROPIC|OPENAI|AWS|GITHUB|API)_?[A-Z_]*KEY",
        "credential exfiltration to a remote host",
    ),
    (r"nc\s+(-e|\S+\s+\d+\s*<)", "reverse-shell idiom (netcat)"),
    (r"/dev/tcp/", "raw tcp shell redirection"),
    (r"chmod\s+777", "world-writable permissions"),
)


def user_skills_dir() -> Path:
    """Community skill install root. Override with $COS_USER_SKILLS_DIR."""
    override = os.environ.get("COS_USER_SKILLS_DIR")
    if override:
        return Path(override)
    return Path.home() / ".coding-os" / "skills"


def _reserved_skill_names() -> set[str]:
    names = set(load_skill_registry(core_dir("skills")).skills.keys())
    for stack_dir in templates_dir().iterdir():
        stack_skills = stack_dir / "skills"
        if stack_skills.is_dir():
            names |= set(load_skill_registry(stack_skills).skills.keys())
    return names


_SKILL_TEMPLATE = """---
name: {name}
tier: cross-cutting
domain: [universal]
description: Use when <the concrete situation this skill helps with>. Triggers on <file globs or keywords>. Covers <the 2-3 things it actually teaches>.
globs: "**/*"
license: MIT
last_reviewed: "{today}"
---

# {name}

Purpose: <one paragraph — the problem this skill removes>.

Read when: <the task shapes that should load it>.
Skip when: <where it adds noise>.

## The rules

1. <rule with the WHY>
2. <rule with the WHY>

## Anti-patterns

- <thing reviewers should reject on sight>
"""


def scan_skill_security(skill_dir: Path) -> list[str]:
    """Named findings for exfil/destructive patterns across the skill's files."""
    findings: list[str] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == PROVENANCE_FILENAME:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern, label in _SECURITY_PATTERNS:
            if re.search(pattern, text):
                findings.append(f"{path.relative_to(skill_dir)}: {label}")
    return findings


def _normalize_frontmatter(skill_md: Path) -> list[str]:
    """Fill missing coding-os taxonomy fields. Returns notes.

    Taxonomy `tier:` stays whatever the author claims (it describes WHAT the
    skill is); TRUST is recorded community-side in provenance only and can
    never be claimed from inside the file."""
    notes: list[str] = []
    text = skill_md.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise click.ClickException(f"{skill_md} has no frontmatter — not a skill file")
    head, _, body = text[3:].partition("\n---")
    lines = list(head.strip().split("\n"))
    keys = {line.split(":", 1)[0].strip() for line in lines if ":" in line}

    if "tier" not in keys:
        lines.append("tier: cross-cutting")
        notes.append("taxonomy tier defaulted to cross-cutting")
    if "domain" not in keys:
        lines.append("domain: [universal]")
        notes.append("domain defaulted to [universal]")
    if "globs" not in keys:
        lines.append('globs: "**/*"')
        notes.append("globs defaulted to **/* (narrow this for real routing)")

    skill_md.write_text("---\n" + "\n".join(lines) + "\n---" + body, encoding="utf-8")
    return notes


def _file_checksums(skill_dir: Path) -> dict[str, str]:
    return {
        str(path.relative_to(skill_dir)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(skill_dir.rglob("*"))
        if path.is_file() and path.name != PROVENANCE_FILENAME
    }


def _license_note(skill_dir: Path) -> str | None:
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    match = re.search(r"^license:\s*(.+)$", skill_md, re.MULTILINE)
    if match:
        return match.group(1).strip()
    if any((skill_dir / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
        return "LICENSE file"
    return None


@click.group("skill")
def skill_group() -> None:
    """Author, lint, import and manage skills (public skill standard)."""


@skill_group.command("new")
@click.argument("name")
@click.option("--dir", "target_dir", default=".", help="Parent directory (default: cwd).")
def skill_new(name: str, target_dir: str) -> None:
    """Scaffold a spec-compliant skill that passes `cos skill lint` as-is."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise click.ClickException("name must be lowercase kebab-case")
    skill_dir = Path(target_dir) / name
    if skill_dir.exists():
        raise click.ClickException(f"{skill_dir} already exists")
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        _SKILL_TEMPLATE.format(name=name, today=_dt.date.today().isoformat()),
        encoding="utf-8",
    )
    click.echo(
        f"created {skill_dir}/SKILL.md — fill the <placeholders>, then: cos skill lint {skill_dir}"
    )


@skill_group.command("lint")
@click.argument("path", type=click.Path(exists=True, file_okay=False, path_type=Path))
def skill_lint(path: Path) -> None:
    """Validate a skill dir through the SAME loader the runtime uses."""
    registry = load_skill_registry(path.parent)
    name = path.name
    relevant = [w for w in registry.warnings if f"/{name}/" in w]
    if name in registry.skills and not relevant:
        click.echo(f"{name}: PASS")
        return
    for warning in relevant or registry.warnings:
        click.echo(f"  {warning}", err=True)
    raise SystemExit(1)


@skill_group.command("add")
@click.argument("source")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt.")
def skill_add(source: str, yes: bool) -> None:
    """Import a third-party skill through the trust gate (normalize → scan → provenance)."""
    cleanup: Path | None = None
    if re.match(r"^(https?://|git@)", source):
        cleanup = Path(tempfile.mkdtemp(prefix="cos-skill-"))
        clone = subprocess.run(
            ["git", "clone", "--depth", "1", source, str(cleanup / "repo")],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if clone.returncode != 0:
            raise click.ClickException(f"git clone failed: {clone.stderr.strip()[-300:]}")
        source_dir = cleanup / "repo"
    else:
        source_dir = Path(source)

    try:
        if (source_dir / "SKILL.md").is_file():
            skill_root = source_dir
        else:
            candidates = [p.parent for p in source_dir.glob("*/SKILL.md")]
            if len(candidates) != 1:
                raise click.ClickException(
                    f"{source}: expected exactly one SKILL.md (found {len(candidates)})"
                )
            skill_root = candidates[0]

        match = re.search(
            r"^name:\s*(\S+)",
            (skill_root / "SKILL.md").read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if not match:
            raise click.ClickException("SKILL.md has no name: field")
        name = match.group(1)

        if name in _reserved_skill_names():
            raise click.ClickException(
                f"'{name}' is a core/stack skill name — community skills may not shadow it"
            )
        target = user_skills_dir() / name
        if target.exists():
            raise click.ClickException(f"{target} already exists — remove it first")

        findings = scan_skill_security(skill_root)
        if findings:
            click.echo("BLOCKED — security scan findings:", err=True)
            for finding in findings:
                click.echo(f"  {finding}", err=True)
            raise SystemExit(1)

        staged = Path(tempfile.mkdtemp(prefix="cos-skill-stage-")) / name
        shutil.copytree(skill_root, staged)
        notes = _normalize_frontmatter(staged / "SKILL.md")
        license_note = _license_note(staged)
        if license_note is None:
            click.echo(
                "  WARN: no license declared (license: frontmatter or LICENSE file)", err=True
            )

        registry = load_skill_registry(staged.parent)
        if name not in registry.skills:
            raise click.ClickException(
                "normalized skill failed validation — " + "; ".join(registry.warnings[-3:])
            )

        has_scripts = any((staged / sub).is_dir() for sub in ("scripts", "bin"))
        if not yes and not click.confirm(
            f"Install '{name}' at trust tier community"
            + (" (has scripts/ — execution stays locked until consent)" if has_scripts else ""),
            default=True,
        ):
            click.echo("Aborted.")
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, target)
        provenance = {
            "source": source,
            "imported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "trust": "community",
            "license": license_note,
            "scripts_consent": False if has_scripts else None,
            "checksums": _file_checksums(target),
        }
        (target / PROVENANCE_FILENAME).write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
        click.echo(f"installed {target} (trust: community)")
        for note in notes:
            click.echo(f"  normalized: {note}")
        if has_scripts:
            click.echo(f"  scripts locked — allow with: cos skill consent {name}")
    finally:
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)


@skill_group.command("list")
def skill_list() -> None:
    """List community skills with trust tier, consent and provenance."""
    root = user_skills_dir()
    if not root.is_dir() or not any(root.iterdir()):
        click.echo("(no community skills installed — `cos skill add <path|git-url>`)")
        return
    for skill_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        provenance_path = skill_dir / PROVENANCE_FILENAME
        if not provenance_path.is_file():
            click.echo(f"  {skill_dir.name:<24} trust=UNKNOWN (no provenance)")
            continue
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
        consent = data.get("scripts_consent")
        consent_label = (
            "" if consent is None else ("  scripts=allowed" if consent else "  scripts=LOCKED")
        )
        click.echo(
            f"  {skill_dir.name:<24} trust={data.get('trust', '?')}"
            f"  source={data.get('source', '?')}{consent_label}"
        )


@skill_group.command("consent")
@click.argument("name")
def skill_consent(name: str) -> None:
    """Record consent for a community skill's scripts to execute."""
    provenance_path = user_skills_dir() / name / PROVENANCE_FILENAME
    if not provenance_path.is_file():
        raise click.ClickException(f"no imported skill '{name}' (see `cos skill list`)")
    data = json.loads(provenance_path.read_text(encoding="utf-8"))
    if data.get("scripts_consent") is None:
        click.echo(f"'{name}' has no scripts — nothing to consent to")
        return
    data["scripts_consent"] = True
    data["consented_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    provenance_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    click.echo(f"consent recorded — '{name}' scripts may now execute")


# --- Per-project extra skills (TASK-370) ---------------------------------
# SSOT is `.coding-os.yaml::extra_skills` (written by init/wizard since
# TASK-356/359) — no second YAML file. enable/disable mutate that list and
# (for community skills) maintain symlinks in every installed adapter's
# skills dir; core/stack skills are already wholesale-linked by the adapter.


def _project_config_path(project_root: Path) -> Path:
    return project_root / ".coding-os.yaml"


def _find_project_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".coding-os.yaml").is_file():
            return candidate
    raise click.ClickException("not inside a coding-os project (.coding-os.yaml not found)")


def _load_project_config(project_root: Path) -> dict:
    import yaml

    return yaml.safe_load(_project_config_path(project_root).read_text(encoding="utf-8")) or {}


def _save_project_config(project_root: Path, config: dict) -> None:
    import yaml

    _project_config_path(project_root).write_text(
        yaml.dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _installed_adapter_skills_dirs(project_root: Path) -> list[Path]:
    from cli._resources import adapters_dir
    from cli.adapter_registry import load_adapter_registry

    dirs: list[Path] = []
    for adapter in load_adapter_registry(adapters_dir()).values():
        if not adapter.skills_dir:
            continue
        agent_dir = project_root / adapter.skills_dir
        if agent_dir.parent.is_dir():
            dirs.append(agent_dir)
    return dirs


def _known_skill_provenance(name: str) -> str | None:
    """'core' | 'stack' | 'community' | None — where this skill name resolves."""
    if (core_dir("skills") / name / "SKILL.md").is_file():
        return "core"
    for stack_dir in templates_dir().iterdir():
        if (stack_dir / "skills" / name / "SKILL.md").is_file():
            return "stack"
    if (user_skills_dir() / name / "SKILL.md").is_file():
        return "community"
    return None


def _skill_source_skill_md(name: str, provenance: str) -> Path | None:
    """Absolute path to the source SKILL.md for a core/stack/community skill."""
    if provenance == "core":
        return core_dir("skills") / name / "SKILL.md"
    if provenance == "community":
        return user_skills_dir() / name / "SKILL.md"
    if provenance == "stack":
        for stack_dir in templates_dir().iterdir():
            candidate = stack_dir / "skills" / name / "SKILL.md"
            if candidate.is_file():
                return candidate
    return None


def _relink_core_stack_skill(
    project_root: Path, name: str, source_skill_md: Path, *, link: bool
) -> int:
    """Re-link (or unlink) a core/stack skill's SKILL.md in every installed
    adapter skills dir. Returns links touched. Linked as
    `<skills_dir>/<name>/SKILL.md` (parity with install-adapter.sh step 6)."""
    touched = 0
    for skills_root in _installed_adapter_skills_dirs(project_root):
        skill_dir = skills_root / name
        link_path = skill_dir / "SKILL.md"
        if link:
            skill_dir.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source_skill_md)
                touched += 1
        else:
            if link_path.is_symlink() or link_path.exists():
                link_path.unlink()
                touched += 1
            try:
                skill_dir.rmdir()
            except OSError:
                pass  # dir not empty / absent — leave it
    return touched


def _relink_community_skill(project_root: Path, name: str, *, link: bool) -> int:
    """Re-link (or unlink) a community skill as a whole-DIR symlink so its
    supporting scripts ride along. Returns links touched."""
    source = user_skills_dir() / name
    touched = 0
    for skills_root in _installed_adapter_skills_dirs(project_root):
        link_path = skills_root / name
        if link:
            skills_root.mkdir(parents=True, exist_ok=True)
            if link_path.is_symlink() and not link_path.exists():
                link_path.unlink()  # dangling link (target moved) — clear before relink
            if not link_path.exists():
                link_path.symlink_to(source)
                touched += 1
        elif link_path.is_symlink():
            link_path.unlink()
            touched += 1
    return touched


def _installed_stack_skills(config: dict) -> set[str]:
    """Required skill names provided by the project's installed stacks."""
    from cli.skills_list import collect_stack_skill_groups

    out: set[str] = set()
    for stack_id in config.get("templates") or []:
        try:
            groups = collect_stack_skill_groups(stack_id)
        except Exception:
            continue
        out |= {entry["name"] for entry in groups.get("required", [])}
    return out


def set_project_skill(project_root: Path, name: str, enabled: bool) -> dict:
    """Shared CLI/web mutator: toggle any skill (core/stack/community) for a
    project. Community skills ride `extra_skills`; core/stack skills ride
    `disabled_skills` (a sibling key — one .coding-os.yaml store, no second
    file). The adapter SKILL.md symlink is relinked/unlinked inline so the
    toggle takes effect without a re-install."""
    provenance = _known_skill_provenance(name)
    if provenance is None:
        raise click.ClickException(
            f"unknown skill '{name}' — not in core, stack, or imported community skills"
        )
    config = _load_project_config(project_root)
    extras = list(config.get("extra_skills") or [])
    disabled = list(config.get("disabled_skills") or [])
    stack_skills = _installed_stack_skills(config)
    source = _skill_source_skill_md(name, provenance)

    # Community skills are opt-IN via extras; core/stack ship by default and are
    # opt-OUT via the disabled list. The two lists are mutually exclusive per id.
    if provenance == "community":
        if enabled:
            if name in extras:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already enabled",
                }
            extras.append(name)
        else:
            if name not in extras:
                raise click.ClickException(f"'{name}' is not an extra skill of this project")
            extras.remove(name)
    else:  # core | stack
        if enabled:
            if name not in disabled:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already enabled (core/stack skills ship by default)",
                }
            disabled.remove(name)
        else:
            if name in disabled:
                return {
                    "name": name,
                    "provenance": provenance,
                    "changed": False,
                    "note": "already disabled",
                }
            # A stack skill not installed by any current stack cannot be disabled.
            if provenance == "stack" and name not in stack_skills:
                raise click.ClickException(
                    f"'{name}' is a stack skill but no installed stack provides it"
                )
            disabled.append(name)

    config["extra_skills"] = extras
    config["disabled_skills"] = sorted(disabled)
    _save_project_config(project_root, config)

    if provenance == "community":
        links_touched = _relink_community_skill(project_root, name, link=enabled)
    elif source is not None:
        links_touched = _relink_core_stack_skill(project_root, name, source, link=enabled)
    else:
        links_touched = 0

    return {"name": name, "provenance": provenance, "changed": True, "links": links_touched}


# --- Module→skill cascade (TASK-475) -------------------------------------
# A module owns the skills it declares in subsystems.yaml::modules[].skills.
# Invariant: an owned skill is LINKED iff (at least one owning module is enabled)
# AND (the user has not opted it out via .coding-os.yaml::disabled_skills). The
# cascade is TARGETED per toggle (mirrors remove_stack._unlink_stack_skills), not
# a global reconcile. It records NOTHING in disabled_skills — that list is the
# user's explicit override, and conflating "module off" with "user opted out"
# would make a module re-enable unable to tell them apart; the linked-state is
# derived instead, and `cos doctor` surfaces any residue (modules.skill_drift).


def _safe_project_config(project_root: Path) -> dict:
    try:
        return _load_project_config(project_root)
    except (OSError, click.ClickException):
        return {}


def _toggle_skill_link(project_root: Path, name: str, *, link: bool) -> int:
    """Link/unlink one skill by provenance; 0 when the skill cannot be resolved."""
    provenance = _known_skill_provenance(name)
    if provenance is None:
        return 0
    if provenance == "community":
        return _relink_community_skill(project_root, name, link=link)
    source = _skill_source_skill_md(name, provenance)
    if source is None:
        return 0
    return _relink_core_stack_skill(project_root, name, source, link=link)


def planned_skill_unlinks(
    project_root: Path, module_id: str, modules: dict | None = None
) -> list[str]:
    """Owned skills `cos module disable <id>` would unlink now — ref-counted
    against other ENABLED owners (never the module itself). Drives the confirm."""
    from cli.subsystems import load_subsystems, module_state

    modules = modules or load_subsystems()
    if module_id not in modules:
        return []
    state = module_state(project_root, modules)
    still_owned = {
        skill
        for mid, module in modules.items()
        if mid != module_id and state.get(mid, True)
        for skill in module.skills
    }
    return [s for s in sorted(modules[module_id].skills) if s not in still_owned]


def cascade_module_skills(
    project_root: Path,
    module_id: str,
    enabled: bool,
    *,
    keep_skills: bool = False,
    modules: dict | None = None,
) -> dict:
    """Relink/unlink a module's owned skills after a module toggle.

    enable → relink each owned skill unless the user opted it out; disable →
    unlink each owned skill unless another enabled module still owns it (ref-count)
    or --keep-skills is set. Idempotent; returns the names touched per bucket."""
    from cli.subsystems import load_subsystems

    modules = modules or load_subsystems()
    owned = sorted(modules[module_id].skills) if module_id in modules else []
    if not owned:
        return {"module": module_id, "linked": [], "unlinked": [], "kept": []}

    config = _safe_project_config(project_root)
    user_disabled = set(config.get("disabled_skills") or [])
    installed_stack_skills = _installed_stack_skills(config)
    linked: list[str] = []
    unlinked: list[str] = []
    kept: list[str] = []

    if enabled:
        for name in owned:
            if name in user_disabled:
                kept.append(name)  # user override outranks the module relink
            elif _known_skill_provenance(name) == "stack" and name not in installed_stack_skills:
                # A meta-stack-owned skill (e.g. graph-os-authoring) that THIS
                # project never installed — never force-link it (mirrors the
                # set_project_skill stack guard, TASK-478). Only core skills ship
                # on every consumer, so only they cascade unconditionally.
                kept.append(name)
            elif _toggle_skill_link(project_root, name, link=True):
                linked.append(name)
    elif keep_skills:
        kept = owned
    else:
        candidates = set(planned_skill_unlinks(project_root, module_id, modules))
        for name in owned:
            if name not in candidates:
                kept.append(name)  # another enabled module still owns it
            elif _toggle_skill_link(project_root, name, link=False):
                unlinked.append(name)
    return {"module": module_id, "linked": linked, "unlinked": unlinked, "kept": kept}


@skill_group.command("enable")
@click.argument("name")
def skill_enable(name: str) -> None:
    """Enable a skill: add a community extra, or clear a core/stack disable."""
    outcome = set_project_skill(_find_project_root(), name, enabled=True)
    if not outcome["changed"]:
        click.echo(f"{name}: no change — {outcome['note']}")
        return
    suffix = f" ({outcome['links']} adapter link(s))" if outcome["links"] else ""
    click.echo(f"enabled {name} [{outcome['provenance']}]{suffix}")


@skill_group.command("disable")
@click.argument("name")
def skill_disable(name: str) -> None:
    """Disable a skill: remove a community extra, or opt a core/stack skill out."""
    outcome = set_project_skill(_find_project_root(), name, enabled=False)
    if not outcome["changed"]:
        click.echo(f"{name}: no change — {outcome['note']}")
        return
    suffix = f" ({outcome['links']} adapter link(s) removed)" if outcome["links"] else ""
    click.echo(f"disabled {name} [{outcome['provenance']}]{suffix}")


@skill_group.command("project")
def skill_project_list() -> None:
    """Show this project's skills: stack-provided vs extras, plus disabled."""
    project_root = _find_project_root()
    config = _load_project_config(project_root)
    disabled = set(config.get("disabled_skills") or [])
    from cli.skills_list import collect_stack_skill_groups

    for stack_id in config.get("templates") or []:
        try:
            groups = collect_stack_skill_groups(stack_id)
        except Exception:
            continue
        required = ", ".join(entry["name"] for entry in groups.get("required", []))
        if required:
            click.echo(f"  stack:{stack_id:<16} {required}")
    for name in config.get("extra_skills") or []:
        click.echo(f"  extra ({_known_skill_provenance(name) or 'missing!'}): {name}")
    for name in sorted(disabled):
        click.echo(f"  disabled ({_known_skill_provenance(name) or 'unknown'}): {name}")
