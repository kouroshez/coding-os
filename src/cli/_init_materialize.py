"""Write-once project artifacts rendered from the aggregated world — AGENTS.md,
the adapter entrypoint symlink, stack commands, the CI workflow, and Dockerfiles.

Every function here follows the `ensure_*` idiom: absent → write, present →
leave alone, so `init`, `add-adapter`, and `update` can all call them without
clobbering a consumer's edits.
"""

from __future__ import annotations

import re
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
    from cli._init_world import _load_config

    commands = {command.name: command.cmd for command in world.commands}
    changed = False
    if (_load_config(project).get("commands") or {}) != commands:
        _write_config_block(project, "commands", commands)
        changed = True
    ci_changed, ci_blocker = _migrate_legacy_ci(project, commands)
    if ci_blocker:
        import click

        click.echo(
            f"  WARN: .github/workflows/ci.yml still runs `make ${{{{ matrix.targets }}}}`: {ci_blocker},"
            " so the make files stay. Move ci.yml aside and run `cos update`.",
            err=True,
        )
    elif _retire_legacy_makefiles(project, state, commands):
        _rewrite_legacy_make_commands(project, commands)
        changed = True
    return changed or ci_changed


_LEGACY_CI_STEP = "        run: make ${{ matrix.targets }}"
_LEGACY_CI_LEG = re.compile(r'^(\s+)targets: "([^"\n]*)"$', re.MULTILINE)
_LEGACY_CI_HEADER = (
    "# Body delegates to the generated make targets so it never rots with tool\n"
    "# versions; adding a stack re-renders this with the new targets.\n"
)


def _migrate_legacy_ci(project: Path, commands: dict[str, str]) -> tuple[bool, str]:
    ci_path = project / ".github" / "workflows" / "ci.yml"
    if not ci_path.is_file():
        return False, ""
    text = ci_path.read_text(encoding="utf-8")
    if _LEGACY_CI_STEP not in text:
        return False, ""
    if ci_path.is_symlink():
        return False, "it is a symlink cos does not rewrite"
    unmapped: list[str] = []

    def leg(match: re.Match[str]) -> str:
        names = match.group(2).split()
        unmapped.extend(name for name in names if name not in commands)
        run = " && ".join(f"({commands[name]})" for name in names if name in commands)
        return f"{match.group(1)}run: '" + run.replace("'", "''") + "'"

    migrated, legs = _LEGACY_CI_LEG.subn(leg, text)
    if unmapped:
        return False, f"it names targets with no stack command ({', '.join(unmapped)})"
    if not legs or "targets:" in migrated:
        return False, 'its matrix legs are not the `targets: "..."` lines cos wrote'
    migrated = migrated.replace(
        _LEGACY_CI_STEP,
        "        env:\n          STACK_COMMANDS: ${{ matrix.run }}\n"
        '        run: bash -c "$STACK_COMMANDS"',
    ).replace(
        _LEGACY_CI_HEADER,
        "# Each leg runs the stack commands from .coding-os.yaml, so it never rots\n"
        "# with tool versions; adding a stack re-renders this with the new commands.\n",
    )
    ci_path.write_text(migrated, encoding="utf-8")
    return True, ""


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


def _write_config_block(project: Path, key: str, mapping: dict[str, str]) -> None:
    import yaml

    from cli._init_world import CONFIG_FILE

    path = project / CONFIG_FILE
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True) if path.exists() else []
    start = next((index for index, line in enumerate(lines) if line.startswith(f"{key}:")), None)
    block = yaml.dump({key: mapping}, default_flow_style=False, sort_keys=False) if mapping else ""
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(block)
    else:
        end = start + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        lines[start:end] = [block]
    path.write_text("".join(lines), encoding="utf-8")


_LEGACY_BASE_TARGETS = (
    "session-init",
    "board",
    "daily",
    "task-start",
    "task-done",
    "docs-lint",
    "docs-index",
    "memory-lint",
    "check-file-size",
    "verify-hooks",
    "log-write",
    "log-latest",
    "log-search",
)


def _retire_legacy_makefiles(project: Path, state: Path, commands: dict[str, str]) -> bool:
    makefile = project / "Makefile"
    changed = False
    if makefile.is_file() and not makefile.is_symlink():
        changed = _strip_cos_lines(project, state, makefile, commands)
    still_included = makefile.read_text(encoding="utf-8") if makefile.is_file() else ""
    for name in ("Makefile.base", "Makefile.stacks"):
        legacy = state / name
        if not legacy.is_file():
            continue
        if name in still_included:
            import click

            click.echo(
                f"  WARN: Makefile still includes {name}; kept it. Remove that include line,"
                " then run `cos update` again to retire it.",
                err=True,
            )
            continue
        legacy.unlink()
        changed = True
    return changed


def _strip_cos_lines(project: Path, state: Path, makefile: Path, commands: dict[str, str]) -> bool:
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
    includes = {f"include {state_rel}/Makefile.base", f"-include {state_rel}/Makefile.stacks"}
    if not includes & {line.strip() for line in lines}:
        return False
    kept = [line for line in lines if line.strip() not in written_by_cos]
    if not "".join(kept).strip():
        makefile.unlink()
        return True
    text = "\n".join(kept).strip("\n") + "\n"
    makefile.write_text(text, encoding="utf-8")
    orphaned = [
        t
        for t in (*_LEGACY_BASE_TARGETS, *commands)
        if re.search(
            rf"^[^#\n]*\bmake {re.escape(t)}(?![\w-])|^[^#\s][^:\n]*:[^\n#=]*(?<![\w-]){re.escape(t)}(?![\w-])",
            text,
            re.MULTILINE,
        )
    ]
    if orphaned:
        import click

        click.echo(
            f"  WARN: Makefile still names targets cos no longer provides: {', '.join(orphaned)}"
            "; use their cos commands (cos run, cos doc-lint, cos daily)",
            err=True,
        )
    return True


_LEGACY_MAKE_TO_COS = {
    "`make session-init`": "`cos daily`",
    "`make docs-lint`": "`cos doc-lint`",
    "`make docs-index`": "`cos docs-index`",
    "`make memory-lint`": "`cos memory-lint`",
    "`make check-file-size`": "`cos check-file-size`",
    "`log-latest [N]`": "`cos log-latest [N]`",
    '`log-write TYPE=t MSG="m" WHAT="w" FILES="f"`': '`cos log-write --type t --msg "m" --what "w" --files "f"`',
    '`log-search QUERY="q"`': '`cos log-search "q"`',
    "`log-latest`/`log-search`": "`cos log-latest`/`cos log-search`",
    "`cos-health`, `verify-hooks`": "`cos health`, `cos doctor`",
}
_LEGACY_TASK_TARGETS = {
    "task-next": "task-pick",
    "task-pick": "task-pick",
    "task-start": "task-start",
    "task-done": "task-done",
    "task-block": "task-block",
    "task-cancel": "task-cancel",
    "task-context": "task-show",
    "task-show": "task-show",
    "task-list": "board",
    "task-log": "task-log",
    "task-history": "task-history",
    "task-validate": "task-validate",
    "task-sync": "task-sync",
    "task-resync": "task-sync --force",
    "board": "board",
    "board-web": "board --web",
    "daily": "daily",
    "retro": "retro",
    "wip": "wip",
}
_LEGACY_TASK_COMMAND = re.compile(r"`make ([\w-]+)([^`]*)`")
_LEGACY_OWNED_TARGETS = sorted(
    {*_LEGACY_BASE_TARGETS, *_LEGACY_TASK_TARGETS, "task-create", "verify"}, key=len, reverse=True
)
_LEGACY_LEFTOVER = re.compile(
    r"`make (?:" + "|".join(map(re.escape, _LEGACY_OWNED_TARGETS)) + r")(?![\w-])[^`]*`"
    r"|`(?:log-latest|log-write|log-search|cos-health|verify-hooks|session-init|"
    r"task-next|task-context|task-list)\b"
)


def _task_command(match: re.Match[str]) -> str:
    target = _LEGACY_TASK_TARGETS.get(match.group(1))
    arguments = re.sub(r"\bREASON=", "--reason ", re.sub(r"\bTASK=", "TASK-", match.group(2)))
    if target is None or re.search(r"\b[A-Z]+=", arguments):
        return match.group(0)
    return f"`cos {target}{arguments}`"


def _rewrite_legacy_make_commands(project: Path, commands: dict[str, str]) -> None:
    from cli._init_world import _load_config

    def to_cos(text: str) -> str:
        for legacy, current in _LEGACY_MAKE_TO_COS.items():
            text = text.replace(legacy, current)
        text = _LEGACY_TASK_COMMAND.sub(_task_command, text)
        for name in commands:
            text = re.sub(rf"\bmake {re.escape(name)}(?![\w-])", f"cos run {name}", text)
        return text

    agents_md = project / "AGENTS.md"
    if agents_md.is_file() and not agents_md.is_symlink():
        text = agents_md.read_text(encoding="utf-8")
        lines = []
        for line in text.splitlines(keepends=True):
            if "`make verify-hooks`" in line:
                continue
            if line.startswith("|"):
                line = line.replace("`make verify`", "(none)")
            lines.append(line)
        rewritten = to_cos("".join(lines))
        if rewritten != text:
            agents_md.write_text(rewritten, encoding="utf-8")
        leftover = sorted(
            {match.group(0).strip("`") for match in _LEGACY_LEFTOVER.finditer(rewritten)}
        )
        if leftover:
            import click

            click.echo(
                f"  WARN: AGENTS.md still names commands from the old Makefile: {', '.join(leftover)}."
                " Move AGENTS.md aside and run `cos update` to regenerate it.",
                err=True,
            )
    verify = _load_config(project).get("verify") or {}
    rewritten_verify = {
        domain: to_cos(f"`{cmd}`").strip("`")
        for domain, cmd in verify.items()
        if cmd != "make verify"
    }
    if rewritten_verify != verify:
        _write_config_block(project, "verify", rewritten_verify)
