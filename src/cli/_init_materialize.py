"""Write-once project artifacts rendered from the aggregated world — AGENTS.md,
the adapter entrypoint symlink, stack commands, the CI workflow, and Dockerfiles.

Every function here follows the `ensure_*` idiom: absent → write, present →
leave alone, so `init`, `add-adapter`, and `update` can all call them without
clobbering a consumer's edits.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli._data_types import AggregatedWorld


def ensure_agents_md(project: Path, world: AggregatedWorld) -> bool:
    """Generate AGENTS.md from fragments if missing. Idempotent.

    Returns True if the file was just created, False if it already existed.
    Never overwrites user-customized AGENTS.md — the `if not exists` guard
    is the contract that lets `init`, `add-adapter`, and `update` all call
    this safely without clobbering edits.
    """
    from cli.renderer import render_agents_md
    from cli.subsystems import module_state

    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        return False
    agents_md.write_text(render_agents_md(world, module_state(project)), encoding="utf-8")
    return True


def ensure_entrypoint_symlink(project: Path, entrypoint_file: str | None) -> bool:
    """Link an adapter's root entrypoint filename at AGENTS.md. Idempotent.

    Returns True if the symlink was just created. A relative link — never a
    copy — so the instruction SSOT cannot fork. An adapter that declares no
    entrypoint gets nothing, and an existing file or symlink of that name is
    left alone, which is what lets `init`, `add-adapter`, and `update` all
    call this without clobbering a user's own file.
    """
    if not entrypoint_file:
        return False
    link = project / entrypoint_file
    if link.exists() or link.is_symlink():
        return False
    if not (project / "AGENTS.md").exists():
        return False
    link.symlink_to("AGENTS.md")
    return True


def materialize_commands(project: Path, state: Path, world: AggregatedWorld) -> bool:
    """Store the stacks' named commands in .coding-os.yaml for `cos run`; retire legacy make files."""
    from cli._init_world import _load_config, _save_config

    commands = {command.name: command.cmd for command in world.commands}
    config = _load_config(project)
    changed = False
    if (config.get("commands") or {}) != commands:
        if commands:
            config["commands"] = commands
        else:
            config.pop("commands", None)
        _save_config(project, config)
        changed = True
    if _retire_legacy_makefiles(project, state):
        _rewrite_legacy_make_commands(project, commands)
        changed = True
    return changed


def materialize_ci_workflow(project: Path, world: AggregatedWorld) -> bool:
    """Render the delegating CI workflow into <project>/.github/workflows/ci.yml.

    Consumer-owned and write-once (the `ensure_*` idiom): written when absent,
    never overwritten — a `cos update` keeps any consumer edits. A world with no
    verifiable targets renders nothing → no file.
    """
    from cli.renderer import render_ci_workflow

    ci_path = project / ".github" / "workflows" / "ci.yml"
    if ci_path.exists():
        return False
    rendered = render_ci_workflow(world)
    if not rendered:
        return False
    ci_path.parent.mkdir(parents=True, exist_ok=True)
    ci_path.write_text(rendered, encoding="utf-8")
    return True


def materialize_dockerfiles(project: Path, world: AggregatedWorld) -> bool:
    """Write a Dockerfile + .dockerignore at every category=backend stack root.

    World-driven (overlay + relocation aware): the backend roots come from
    `world.anatomy`, the language from the matching verify row's glob — so a bare
    or exempt backend (no verify row, e.g. a `*-plain` stack) gets none, like
    frontend/mobile/library. Consumer-owned and write-once: never overwrites an
    existing file, so a `cos update` keeps the consumer's CMD/entrypoint edits.
    """
    from cli.renderer import language_for_glob, render_dockerfile, render_dockerignore

    language_by_root: dict[str, str] = {}
    for row in world.verify_rows:
        if "/**" not in row.glob:
            continue
        language = language_for_glob(row.glob)
        if language:
            language_by_root.setdefault(row.glob.split("/**", 1)[0].rstrip("/"), language)

    changed = False
    for entry in world.anatomy:
        if entry.category != "backend":
            continue
        root = entry.root.rstrip("/")
        content = render_dockerfile(language_by_root.get(root, ""))
        if not content:
            continue
        base = project / root if root else project
        for name, text in (("Dockerfile", content), (".dockerignore", render_dockerignore())):
            target = base / name
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            changed = True
    return changed


def _retire_legacy_makefiles(project: Path, state: Path) -> bool:
    changed = False
    for name in ("Makefile.base", "Makefile.stacks"):
        legacy = state / name
        if legacy.is_file():
            legacy.unlink()
            changed = True
    makefile = project / "Makefile"
    if not makefile.is_file():
        return changed
    state_rel = (
        state.relative_to(project).as_posix() if state.is_relative_to(project) else state.name
    )
    written_by_cos = {
        "# Project Makefile",
        "# coding-os universal targets",
        f"include {state_rel}/Makefile.base",
        f"-include {state_rel}/Makefile.stacks",
        "# Add your project-specific targets below:",
    }
    lines = makefile.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() not in written_by_cos]
    if kept == lines:
        return changed
    if not "".join(kept).strip():
        makefile.unlink()
    else:
        makefile.write_text("\n".join(kept).strip("\n") + "\n", encoding="utf-8")
    return True


_LEGACY_MAKE_TO_COS = {
    "`make session-init`": "`cos daily`",
    "`make docs-lint`": "`cos doc-lint`",
    "`make docs-index`": "`cos docs-index`",
    "`make memory-lint`": "`cos memory-lint`",
    "`make check-file-size`": "`cos check-file-size`",
    "`make verify`": "(none)",
}


def _rewrite_legacy_make_commands(project: Path, commands: dict[str, str]) -> None:
    from cli._init_world import _load_config, _save_config

    def to_cos(text: str) -> str:
        for legacy, current in _LEGACY_MAKE_TO_COS.items():
            text = text.replace(legacy, current)
        for name in commands:
            text = text.replace(f"make {name}", f"cos run {name}")
        return text

    agents_md = project / "AGENTS.md"
    if agents_md.is_file() and not agents_md.is_symlink():
        text = agents_md.read_text(encoding="utf-8")
        lines = [
            line for line in text.splitlines(keepends=True) if "`make verify-hooks`" not in line
        ]
        rewritten = to_cos("".join(lines))
        if rewritten != text:
            agents_md.write_text(rewritten, encoding="utf-8")
    config = _load_config(project)
    verify = config.get("verify") or {}
    rewritten_verify = {domain: to_cos(f"`{cmd}`").strip("`") for domain, cmd in verify.items()}
    rewritten_verify = {domain: cmd for domain, cmd in rewritten_verify.items() if cmd != "(none)"}
    if rewritten_verify != verify:
        config["verify"] = rewritten_verify
        _save_config(project, config)
