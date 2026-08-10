#!/usr/bin/env python3
"""
Coding OS — CLI tool for installing and managing the cognitive operating system.

Usage:
    coding-os init --agent claude,codex [--template django]
    coding-os add-adapter codex
    coding-os health
    coding-os adopt          # overlay onto an existing repo
    coding-os eject          # remove coding-os, keep your code/docs
"""

from __future__ import annotations

from pathlib import Path

import click

from cli._init_boundaries import _aggregate_scaffold_boundaries  # noqa: F401
from cli._init_phase import (  # noqa: F401 — re-exported for tests + siblings
    _initial_doc_index,
    _initial_graph_index,
    _run_scaffold_phase,
)
from cli._init_preview import (  # noqa: F401 — re-exported for tests + siblings
    _dry_config_preview,
    _dry_run_preview,
    _scaffold_tree_preview,
)
from cli._init_registries import (  # noqa: F401 — re-exported for tests + siblings
    ADAPTERS_DIR,
    CONFIG_FILE,
    CORE_DIR,
    STATE_DIR,
    TEMPLATES_DIR,
    VALID_AGENTS,
    _apply_enable_modules,
    _discover_valid_agents,
    _discover_valid_templates,
    _enable_flag_help,
    _example_swimlane,
    _get_adapter_registry,
    _get_base_profile,
    _get_stack_registry,
    _module_flag_help,
    _profile_flag_help,
    _registered_slug,
    _reset_registries_for_tests,
    _subsystem_help_lists,
    _validated_disabled_modules,
)
from cli._init_scaffold import (  # noqa: F401 — re-exported for tests + siblings
    _apply_doc_conditions,
    _apply_template,
    _copy_workflow_docs,
    _link_stack_skills,
    _overlay_scaffold,
    _resolve_placeholders,
    _run_adapter_install,
    _service_relocations,
    module_scaffold_doc_rels,
)
from cli._init_world import (  # noqa: F401 — re-exported for tests + siblings
    _build_world,
    _derive_verify_from_world,
    _detect_existing_install,
    _load_config,
    _parse_agents,
    _prompt_agents,
    _prompt_name_and_location,
    _prompt_templates,
    _save_config,
    _sync_missing,
)
from cli.add_stack import add_stack as add_stack_cmd
from cli.brain_commands import (
    brain_decay as brain_decay_cmd,
    brain_gc as brain_gc_cmd,
    brain_sweep_changelog as brain_sweep_changelog_cmd,
    docs_index as docs_index_cmd,
    reindex as reindex_cmd,
    task_sync as task_sync_cmd,
)
from cli.doctor import doctor as doctor_cmd
from cli.list_adapters import list_adapters as list_adapters_cmd
from cli.list_stacks import list_stacks as list_stacks_cmd
from cli.materialize_file import materialize_file as materialize_file_cmd
from cli.remove_stack import remove_stack as remove_stack_cmd
from cli.setup import setup as setup_cmd
from cli.skills_list import skills_list as skills_list_cmd
from cli.tail_command import tail_cmd
from cli.update import update as update_cmd

VALID_TEMPLATES: list[str] = _discover_valid_templates()

# Stack and adapter metadata live in templates/*/stack.yaml and
# adapters/*/adapter.yaml. Adding a new stack or adapter is a pure data-file
# change — never touch this module.
#
# The caches below memoize registry loads within a single CLI invocation so
# cos init/doctor/add-stack don't re-parse YAML repeatedly. Tests can reset
# them via _reset_registries_for_tests().


# _merge_profiles, _build_substitutions, _list_installed_skills have all
# been replaced by the aggregator pipeline. See _build_world() above and
# src/cli/aggregator.py::aggregate() for the data-driven replacement.


# Tag-driven docs composition (TASK-360):
#  - file-level: a `module:<id>` token in the first-line header comment skips
#    the whole doc when that module is disabled;
#  - block-level: `<!-- if-stack:a,b -->` / `<!-- if-module:docs -->` ...
#    `<!-- end-if -->` keep the block only when ANY listed stack is installed /
#    the module is enabled. Markers and tags are stripped from the copy, so a
#    fully-default project's output is byte-identical to untagged sources.


def _bootstrap_hub_dir_if_first_run() -> None:
    """Seed ~/.coding-os/ the very first time the CLI is invoked."""
    import os as _os

    override = _os.environ.get("COS_REGISTRY_PATH")
    hub_dir = Path(override).parent if override else Path.home() / ".coding-os"
    try:
        if not hub_dir.exists():
            hub_dir.mkdir(parents=True, exist_ok=True)
        registry_file = hub_dir / "registry.json"
        if not registry_file.exists():
            # Same shape save_registry() writes — keep in sync with
            # cli.registry.Registry.to_dict().
            registry_file.write_text(
                '{\n  "version": 1,\n  "projects": []\n}\n',
                encoding="utf-8",
            )
    except OSError as exc:
        import logging as _logging

        _logging.getLogger("cli.main").debug("hub-dir bootstrap skipped: %s", exc)


from importlib.metadata import (
    PackageNotFoundError as _PackageNotFoundError,
    version as _pkg_version,
)


def _resolve_cli_version() -> str:
    try:
        return _pkg_version("coding-os")
    except _PackageNotFoundError:
        return "unknown"


def _warn_dangling_agent_links() -> None:
    """One stderr nudge when the cwd project's agent symlinks dangle (moved meta-repo).

    Fail-open by contract: the probe must never break or slow a command —
    hub-architecture.md § Symlink health is the spec for this passive layer.
    """
    try:
        project = Path.cwd()
        if not (project / CONFIG_FILE).exists():
            return
        from cli.sync_all import _dangling, _iter_symlinks

        for link in _iter_symlinks(project):
            if _dangling(link):
                click.echo(
                    "WARN: dangling coding-os symlinks detected (meta-repo moved or removed?) "
                    "— run: cos sync-doctor --repair",
                    err=True,
                )
                return
    except Exception as exc:
        import logging

        logging.getLogger(__name__).debug("dangling-link probe skipped: %s", exc)


@click.group()
@click.version_option(version=_resolve_cli_version(), prog_name="coding-os")
def cli() -> None:
    """Coding OS — the cognitive operating system that gives AI agents memory, structure, and discipline."""
    _warn_dangling_agent_links()
    # Route every stdlib logger.error from doctor /
    # health / any cos command into logging_os so the CLI process is no longer
    # blind to its own failures. Idempotent — install_bridge() removes a prior
    # bridge handler before adding. See docs/engineering/observability-eye.md §1.
    try:
        from core.logging_os import setup as _logging_os_setup

        _logging_os_setup(level="info")
    except Exception as _bridge_exc:  # pragma: no cover — never block the CLI on logging setup
        import logging as _logging

        _logging.getLogger("coding_os.cli").debug("logging_os bridge unavailable: %s", _bridge_exc)

    _bootstrap_hub_dir_if_first_run()


cli.add_command(doctor_cmd)
cli.add_command(list_stacks_cmd)
cli.add_command(list_adapters_cmd)
cli.add_command(add_stack_cmd)
cli.add_command(remove_stack_cmd)
cli.add_command(docs_index_cmd)
cli.add_command(task_sync_cmd)
cli.add_command(reindex_cmd)
cli.add_command(brain_decay_cmd)
cli.add_command(brain_gc_cmd)
cli.add_command(brain_sweep_changelog_cmd)
cli.add_command(update_cmd)
cli.add_command(setup_cmd)
cli.add_command(materialize_file_cmd)
cli.add_command(tail_cmd)
cli.add_command(skills_list_cmd)

from cli.module_commands import module_group as module_group_cmd
from cli.preset_commands import preset_group as preset_group_cmd
from cli.skill_commands import skill_group as skill_group_cmd
from cli.stack_lint import stack_lint as stack_lint_cmd
from cli.supervision_commands import supervision_group as supervision_group_cmd

cli.add_command(module_group_cmd)
cli.add_command(preset_group_cmd)
cli.add_command(skill_group_cmd)
cli.add_command(stack_lint_cmd)
cli.add_command(supervision_group_cmd)

from cli._cli_paths import (  # noqa: F401  — pre-split re-export
    CODING_OS_ROOT,
    _refuse_coding_os_self_init,
    _resolve_project_dir,
)
from cli.adopt_command import _detect_stacks_from_markers  # noqa: F401  — pre-split re-export

# Durable error/log query CLI (cos errors / cos logs).
try:
    from cli.logs_commands import errors_cmd as _errors_cmd, logs_cmd as _logs_cmd

    cli.add_command(_logs_cmd)
    cli.add_command(_errors_cmd)
except ImportError as _logs_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("logs CLI unavailable: %s", _logs_cli_exc)

# Doc lifecycle CLI (cos doc-new / doc-history / doc-lint).
try:
    from cli.doc_commands import (
        doc_history_cmd as _doc_history_cmd,
        doc_lint_cmd as _doc_lint_cmd,
        doc_new_cmd as _doc_new_cmd,
    )

    cli.add_command(_doc_new_cmd)
    cli.add_command(_doc_history_cmd)
    cli.add_command(_doc_lint_cmd)
except ImportError as _doc_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("doc CLI unavailable: %s", _doc_cli_exc)

# Fast scope-aware verification: `cos verify --since-edit`.
try:
    from cli.verify_since_edit import verify_since_edit_cmd as _verify_cmd

    cli.add_command(_verify_cmd)
except ImportError as _verify_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("verify CLI unavailable: %s", _verify_exc)

# Hub propagation: push meta-repo edits to every registered
# project via symlink re-link + DB migration.  Lives in src/cli/sync_all.py
# so registry.py stays focused on the JSON CRUD.
try:
    from cli.sync_all import sync_all_cmd, sync_doctor_cmd

    cli.add_command(sync_all_cmd)
    cli.add_command(sync_doctor_cmd)
except ImportError as _e:
    import logging as _logging

    _logging.getLogger("cli.main").debug("sync_all unavailable: %s", _e)

# board_os CLI surface (16 commands).
try:
    from cli.board_commands import BOARD_COMMANDS

    for _bc in BOARD_COMMANDS:
        cli.add_command(_bc)
except ImportError:
    pass  # board_os optional — don't break `cos` if deps missing.

# pr-mode multi-agent git executor (cos pr open/submit/status/cleanup/preflight).
try:
    from cli.pr_commands import pr_group as _pr_group

    cli.add_command(_pr_group)
except ImportError as _pr_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("pr CLI unavailable: %s", _pr_cli_exc)

# Scheduled jobs (CRON A/B).
try:
    from cli.cron_commands import cron_cmd

    cli.add_command(cron_cmd)
except ImportError as _e:
    import logging as _logging

    _logging.getLogger("cli.main").debug("cron CLI unavailable: %s", _e)

# cognition CLI (formula dispatches, persona selections, backtracks).
try:
    from cli.cognition import COGNITION_COMMANDS

    for _cc in COGNITION_COMMANDS:
        cli.add_command(_cc)
except ImportError:
    pass  # cognition optional — don't break `cos` if click missing.


# ---------------------------------------------------------------------------
# graph_os subcommand family (`cos graph-*`).
# Registration lives in src/cli/graph_commands.py so the main file stays lean.
# ---------------------------------------------------------------------------
try:
    from cli import graph_commands as _graph_commands

    _graph_commands.register(cli)
except ImportError as _graph_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("graph_os CLI unavailable: %s", _graph_cli_exc)


# ---------------------------------------------------------------------------
# DB lifecycle — `cos db-stats`, `cos db-reset`. Spec: docs/playbooks/db-reset.md.
# ---------------------------------------------------------------------------
try:
    from cli import db_reset as _db_reset

    _db_reset.register(cli)
except ImportError as _db_reset_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("db_reset CLI unavailable: %s", _db_reset_exc)


# ---------------------------------------------------------------------------
# S4/S5 — registry + hub CLI. (`cos web` removed: it duplicated
# `cos hub start --foreground` — both just call web.server.run_server. Dev
# auto-reload lives in `make ui-dev`.)
# ---------------------------------------------------------------------------
try:
    from cli.registry import registry_cli as _registry_cli

    cli.add_command(_registry_cli)

    from cli.hub_commands import hub_cli as _hub_cli, service_cli as _service_cli

    cli.add_command(_hub_cli)
    cli.add_command(_service_cli)
except ImportError as _web_cli_exc:  # pragma: no cover — defensive
    import logging as _logging

    _logging.getLogger("coding_os.cli").debug("web CLI unavailable: %s", _web_cli_exc)


from cli.adopt_command import adopt
from cli.init_command import init
from cli.install_commands import add_adapter, codex_mcp_install, eject, health, materialize
from cli.runtime_commands import hooks_dir, hooks_list, hooks_log, server_start, session_state

cli.add_command(init)
cli.add_command(adopt)
cli.add_command(add_adapter)
cli.add_command(codex_mcp_install)
cli.add_command(health)
cli.add_command(materialize)
cli.add_command(eject)
cli.add_command(hooks_dir)
cli.add_command(hooks_log)
cli.add_command(hooks_list)
cli.add_command(server_start)
cli.add_command(session_state)


# Must stay last: `python -m cli.main` executes the module top-to-bottom, so an
# earlier guard would invoke the CLI before the commands above are registered.
if __name__ == "__main__":
    cli()
