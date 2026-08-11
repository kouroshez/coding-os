"""Write-once project artifacts rendered from the aggregated world — AGENTS.md,
the adapter entrypoint symlink, make targets, the CI workflow, and Dockerfiles.

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


def materialize_makefile_targets(project: Path, state: Path, world: AggregatedWorld) -> bool:
    """Render stack-contributed make targets into a generated include and wire
    it into the project Makefile.

    Writes `world.makefile_targets` to ``<state>/Makefile.stacks`` and ensures
    the project Makefile pulls it in via ``-include``. Returns True if anything
    changed. The user-authored Makefile is never rewritten beyond ensuring the
    single include line is present — so re-running on an edited Makefile is safe.
    """
    from cli.renderer import render_makefile_targets

    stacks_path = state / "Makefile.stacks"
    rendered = render_makefile_targets(world)
    changed = not stacks_path.exists() or stacks_path.read_text(encoding="utf-8") != rendered
    if changed:
        stacks_path.parent.mkdir(parents=True, exist_ok=True)
        stacks_path.write_text(rendered, encoding="utf-8")

    # Wire the `-include` ONLY when a stack actually contributes targets. With an
    # empty world (e.g. the meta stack) the .stacks file is just a placeholder, so
    # adding an include to a hand-authored Makefile would dirty it on every `cos
    # update` for no benefit — the line appears the moment a stack first contributes.
    makefile = project / "Makefile"
    if makefile.exists() and world.makefile_targets:
        state_rel = (
            state.relative_to(project).as_posix() if state.is_relative_to(project) else state.name
        )
        if _ensure_stacks_include(makefile, state_rel):
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


def _ensure_stacks_include(makefile: Path, state_rel: str) -> bool:
    text = makefile.read_text(encoding="utf-8")
    if "Makefile.stacks" in text:
        return False
    include_line = f"-include {state_rel}/Makefile.stacks\n"
    base_marker = f"include {state_rel}/Makefile.base\n"
    if base_marker in text:
        text = text.replace(base_marker, base_marker + include_line, 1)
    else:
        text = text.rstrip("\n") + "\n" + include_line
    makefile.write_text(text, encoding="utf-8")
    return True
