"""Helpers for `cos init` — target resolution, git bootstrap, materialization.

Separated from main.py to keep init logic testable and linear. The three
concerns live in leaves — `_init_target` (flags → prepared directory),
`_init_git` (repo, ignore file, baseline commit, hook bodies), and
`_init_materialize` (write-once artifacts rendered from the world) — and are
re-exported here so every existing import keeps resolving.
"""

from __future__ import annotations

from cli._init_git import (
    CONSUMER_GITIGNORE as CONSUMER_GITIGNORE,
    GitHooksResult as GitHooksResult,
    GitInitResult as GitInitResult,
    InitialCommitResult as InitialCommitResult,
    ensure_gitignore as ensure_gitignore,
    install_consumer_git_hooks as install_consumer_git_hooks,
    maybe_git_init as maybe_git_init,
    maybe_initial_commit as maybe_initial_commit,
)
from cli._init_materialize import (
    _ensure_stacks_include as _ensure_stacks_include,
    ensure_agents_md as ensure_agents_md,
    ensure_entrypoint_symlink as ensure_entrypoint_symlink,
    materialize_ci_workflow as materialize_ci_workflow,
    materialize_dockerfiles as materialize_dockerfiles,
    materialize_makefile_targets as materialize_makefile_targets,
)
from cli._init_target import (
    CODING_OS_ROOT as CODING_OS_ROOT,
    DEBUG_DIR as DEBUG_DIR,
    DEFAULT_DEBUG_NAME as DEFAULT_DEBUG_NAME,
    NAME_REGEX as NAME_REGEX,
    InitError as InitError,
    InitExit as InitExit,
    InitTarget as InitTarget,
    _cwd_inside_coding_os as _cwd_inside_coding_os,
    _is_dir_empty as _is_dir_empty,
    _is_nested_in_git as _is_nested_in_git,
    _safe_remove_tree as _safe_remove_tree,
    is_coding_os_source_tree as is_coding_os_source_tree,
    resolve_init_target as resolve_init_target,
    validate_name as validate_name,
)
