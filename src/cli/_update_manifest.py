"""Installed-asset manifest engine behind `cos update`.

Enumerates every symlink an install should carry (adapter hooks/rules/skills/
commands plus stack skills, minus assets owned only by disabled modules),
scans what the project actually has, diffs the two, applies the diff, and
records the `installed-manifest.json` snapshot. The `cos update` command
itself — version skew, AGENTS.md backfill, migrations, hub bounce — stays in
cli.update.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import click
import yaml

from cli._resources import adapters_dir, core_dir, data_root, overlay_adapter_dirs, templates_dir
from cli.core_version import stamp_core_version

logger = logging.getLogger(__name__)

# Resolved via importlib so update works under both a src-layout
# editable install and a built wheel — and keeps working after the meta-repo
# is moved and reinstalled. CODING_OS_ROOT is informational (installed-manifest).
CODING_OS_ROOT = data_root().parent
ADAPTERS_DIR = adapters_dir()
CORE_DIR = core_dir()
TEMPLATES_DIR = templates_dir()
CONFIG_FILE = ".coding-os.yaml"
STATE_DIR = ".coding-os"
INSTALLED_MANIFEST = "installed-manifest.json"


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class AssetRef:
    """Logical asset: a name + where it should live under the agent root.

    `name` is the filename (hook/rule/command) or skill folder name.
    `rel_link` is the project-relative path where the symlink lives.
    `source_path` is the absolute path in CODING_OS_ROOT that it targets.
    """

    name: str
    rel_link: str
    source_path: Path


@dataclass
class ManifestDiff:
    added: dict[str, list[AssetRef]] = field(default_factory=dict)
    removed: dict[str, list[str]] = field(default_factory=dict)

    @property
    def has_changes(self) -> bool:
        return any(self.added.values()) or any(self.removed.values())


# ---------------------------------------------------------------------------
# Manifest builders
# ---------------------------------------------------------------------------


def _load_config(project: Path) -> dict:
    path = project / CONFIG_FILE
    if not path.exists():
        raise click.ClickException(f"Not a coding-os project ({CONFIG_FILE} missing in {project})")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_adapter(agent: str):
    from cli.adapter_registry import load_adapter_registry

    adapters = load_adapter_registry(ADAPTERS_DIR, overlay_dirs=overlay_adapter_dirs())
    if agent not in adapters:
        raise click.ClickException(f"adapter '{agent}' not in registry")
    return adapters[agent]


# install-adapter.sh deliberately leaves these two unlinked (on-demand reference
# only, audit 2026-06 token-economics C1). Enumerating them here made every fresh
# install report drift on the very next `cos update`.
_NON_ACTIVE_RULES = frozenset({"dimension-registry.md", "skill-enforcement.md"})


def _module_disabled_assets(project: Path | None, key: str) -> frozenset[str]:
    """Core rule/command filenames owned ONLY by disabled subsystem modules.

    Mirrors install-adapter.sh's ref-counted sweep so `cos update` expects the
    same set the installer actually links (TASK-876).
    """
    if project is None:
        return frozenset()
    try:
        manifest = yaml.safe_load((CORE_DIR / "subsystems.yaml").read_text(encoding="utf-8")) or {}
        state = json.loads(
            (project / ".coding-os" / "subsystems-state.json").read_text(encoding="utf-8")
        )
    except (OSError, yaml.YAMLError, json.JSONDecodeError):
        return frozenset()
    disabled = {str(x) for x in (state.get("disabled") or [])}
    if not disabled:
        return frozenset()
    modules = manifest.get("modules") or []

    def _enabled(module: dict) -> bool:
        return bool(module.get("kernel")) or str(module.get("id")) not in disabled

    owned_by_enabled = {n for m in modules if _enabled(m) for n in (m.get(key) or [])}
    return frozenset(
        name
        for m in modules
        if not _enabled(m)
        for name in (m.get(key) or [])
        if name not in owned_by_enabled
    )


def _disabled_skills(project: Path | None) -> frozenset[str]:
    """Skill names the project opted out of via `.coding-os.yaml::disabled_skills`.

    install-adapter.sh skips AND unlinks these, for core and stack skills alike.
    Enumerating them as expected assets made `cos update` report every disabled
    skill as missing and relink it, silently undoing `cos skill disable`.
    """
    if project is None:
        return frozenset()
    from cli._skill_project import _safe_project_config

    return frozenset(
        str(name) for name in (_safe_project_config(project).get("disabled_skills") or [])
    )


def _build_target_assets(
    agent: str, templates: list[str], project: Path | None = None
) -> dict[str, list[AssetRef]]:
    """Enumerate every symlink we expect to exist for this install."""
    adapter = _load_adapter(agent)
    result: dict[str, list[AssetRef]] = {
        "hooks": [],
        "skills": [],
        "rules": [],
        "commands": [],
    }

    # Hooks — the agent-agnostic core set, PLUS the adapter's own hooks. Omitting
    # the adapter-owned ones made them look unknown to the diff, so `cos update`
    # deleted them: for Codex that is every dispatcher, i.e. its whole hook
    # parity mechanism. Helper .py files sit beside the .sh and link the same way.
    hooks_dir_rel = adapter.hooks_dir
    if hooks_dir_rel:
        sources = [*sorted((CORE_DIR / "hooks").glob("*.sh"))]
        adapter_hooks = ADAPTERS_DIR / agent / "hooks"
        if adapter_hooks.is_dir():
            sources += sorted(
                path
                for path in adapter_hooks.iterdir()
                if path.is_file() and path.suffix in (".sh", ".py")
            )
        for hook in sources:
            result["hooks"].append(
                AssetRef(
                    name=hook.name,
                    rel_link=f"{hooks_dir_rel}/{hook.name}",
                    source_path=hook,
                )
            )

    # Rules — only when adapter supports them.
    rules_dir_rel = adapter.rules_dir
    if rules_dir_rel:
        skip_rules = _NON_ACTIVE_RULES | _module_disabled_assets(project, "rules")
        for rule in sorted((CORE_DIR / "rules").glob("*.md")):
            if rule.name in skip_rules:
                continue
            result["rules"].append(
                AssetRef(
                    name=rule.name,
                    rel_link=f"{rules_dir_rel}/{rule.name}",
                    source_path=rule,
                )
            )

    # Core skills.
    skills_dir_rel = adapter.skills_dir
    if skills_dir_rel:
        skip_skills = _disabled_skills(project)
        for skill_dir in sorted((CORE_DIR / "skills").iterdir()):
            if not skill_dir.is_dir() or skill_dir.name in skip_skills:
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            result["skills"].append(
                AssetRef(
                    name=skill_dir.name,
                    rel_link=f"{skills_dir_rel}/{skill_dir.name}/SKILL.md",
                    source_path=skill_md,
                )
            )
        # Stack skills.
        for stack in templates:
            stack_skills = TEMPLATES_DIR / stack / "skills"
            if not stack_skills.exists():
                continue
            for skill_dir in sorted(stack_skills.iterdir()):
                if not skill_dir.is_dir() or skill_dir.name in skip_skills:
                    continue
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                result["skills"].append(
                    AssetRef(
                        name=skill_dir.name,
                        rel_link=f"{skills_dir_rel}/{skill_dir.name}/SKILL.md",
                        source_path=skill_md,
                    )
                )

    # Commands — adapters that declare commands_dir in adapter.yaml.
    # Adapters merging commands into a single instructions file leave
    # commands_dir null and skip this branch.
    commands_dir_rel = getattr(adapter, "commands_dir", None)
    if commands_dir_rel:
        commands_src = CORE_DIR / "commands"
        if commands_src.exists():
            skip_commands = {
                f"{stem}.md" for stem in _module_disabled_assets(project, "commands")
            } | _module_disabled_assets(project, "commands")
            for cmd in sorted(commands_src.glob("*.md")):
                if cmd.name in skip_commands:
                    continue
                result["commands"].append(
                    AssetRef(
                        name=cmd.name,
                        rel_link=f"{commands_dir_rel}/{cmd.name}",
                        source_path=cmd,
                    )
                )
        # Role-agent slash commands installed by install-adapter.sh §8.
        # Each semantic agent (researcher.md, analyst.md, …) is exposed as
        # /role-<name>. README.md is excluded (catalog, not a role).
        agents_src = CORE_DIR / "thinking_os" / "agents"
        if agents_src.exists():
            for agent in sorted(agents_src.glob("*.md")):
                if agent.name == "README.md":
                    continue
                role = agent.stem
                result["commands"].append(
                    AssetRef(
                        name=f"role-{role}.md",
                        rel_link=f"{commands_dir_rel}/role-{role}.md",
                        source_path=agent,
                    )
                )

    return result


def _scan_project_assets(
    project: Path, categories: list[str], adapter_id: str
) -> dict[str, list[str]]:
    """Collect the set of asset names currently present in the project.

    Categories → directory mapping for the given adapter. Returns dict
    mapping category → list of on-disk asset names (paths relative to
    project root). Only looks at symlinks — copied files are user content.
    """
    adapter = _load_adapter(adapter_id)
    dir_by_cat = {
        "hooks": adapter.hooks_dir,
        "rules": adapter.rules_dir,
        "skills": adapter.skills_dir,
        "commands": getattr(adapter, "commands_dir", None),
    }

    present: dict[str, list[str]] = {}
    for cat in categories:
        base_rel = dir_by_cat.get(cat)
        if not base_rel:
            present[cat] = []
            continue
        base = project / base_rel
        if not base.exists():
            present[cat] = []
            continue
        names: list[str] = []
        if cat == "skills":
            for skill_dir in sorted(base.iterdir()):
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    names.append(skill_dir.name)
        else:
            for entry in sorted(base.iterdir()):
                # Only track symlinks — copies are user-owned (e.g. path-scoped
                # stack rules like django-backend.md are regular files and
                # must not be flagged as orphans to remove).
                if entry.is_symlink():
                    names.append(entry.name)
        present[cat] = names
    return present


# ---------------------------------------------------------------------------
# Diff + apply
# ---------------------------------------------------------------------------


def _compute_diff(target: dict[str, list[AssetRef]], present: dict[str, list[str]]) -> ManifestDiff:
    diff = ManifestDiff()
    # For "skills", we compare skill_dir names; for others, file names.
    for cat, targets in target.items():
        current_names = set(present.get(cat, []))
        target_keys = {t.name: t for t in targets}
        # We need the skill-dir-name mapping: since rel_link for skill is
        # <dir>/<skill_name>/SKILL.md, the presence list stores <skill_name>.
        added = [t for key, t in target_keys.items() if key not in current_names]
        if added:
            diff.added[cat] = added
        removed = [n for n in current_names if n not in target_keys]
        if removed:
            diff.removed[cat] = removed
    return diff


def _apply_diff(project: Path, diff: ManifestDiff, adapter_id: str) -> None:
    """Create missing symlinks; remove orphans."""
    # Add
    for _cat, items in diff.added.items():
        for item in items:
            link = project / item.rel_link
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(item.source_path)
    # Remove orphans
    adapter = _load_adapter(adapter_id)
    dir_by_cat = {
        "hooks": adapter.hooks_dir,
        "rules": adapter.rules_dir,
        "skills": adapter.skills_dir,
        "commands": getattr(adapter, "commands_dir", None),
    }
    for cat, names in diff.removed.items():
        base_rel = dir_by_cat.get(cat)
        if not base_rel:
            continue
        base = project / base_rel
        for name in names:
            if cat == "skills":
                entry = base / name
                if entry.is_symlink():
                    # A symlinked skill dir is a community/extra link managed
                    # by `cos skill enable` — descending through it would
                    # delete the user's source files. Not update's to prune.
                    continue
                skill_md = entry / "SKILL.md"
                if skill_md.is_symlink() or skill_md.exists():
                    skill_md.unlink()
                try:
                    entry.rmdir()
                except OSError as exc:
                    logger.debug("orphan skill dir kept (non-empty): %s", exc)
            else:
                entry = base / name
                if entry.is_symlink() or entry.exists():
                    entry.unlink()


def _run_db_migrations(project: Path) -> bool:
    db = project / STATE_DIR / "coding-os.db"
    if not db.exists():
        return True
    import subprocess
    import sys

    brain = CORE_DIR / "thinking_os"
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path.insert(0, {str(brain)!r}); "
            f"from database import init_db; init_db({str(db)!r})",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        click.echo(f"  WARN: DB migration failed (exit {proc.returncode})", err=True)
        if proc.stderr:
            click.echo(proc.stderr.strip(), err=True)
        return False
    return True


def _write_installed_manifest(
    project: Path,
    agent: str,
    templates: list[str],
    target: dict[str, list[AssetRef]],
) -> Path:
    manifest = {
        "coding_os_root": str(CODING_OS_ROOT),
        "installed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "templates": templates,
        "linked_assets": {cat: [a.name for a in items] for cat, items in target.items()},
    }
    state = project / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    out = state / INSTALLED_MANIFEST
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    stamp_core_version(state)
    return out


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------


def _format_diff(diff: ManifestDiff) -> str:
    if not diff.has_changes:
        return "No changes — already up to date."
    lines = []
    for cat in ("hooks", "rules", "skills", "commands"):
        add = diff.added.get(cat, [])
        rem = diff.removed.get(cat, [])
        if add:
            lines.append(f"  Added {cat}: {', '.join(a.name for a in add)}")
        if rem:
            lines.append(f"  Removed {cat}: {', '.join(rem)}")
    return "\n".join(lines)
