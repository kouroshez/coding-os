"""The `cos init` scaffold phase driver plus the first doc + graph index runs.

One responsibility: sequence the materialisation steps in the order a working
project needs them. The steps themselves live in _init_scaffold / _init_world;
this module owns only the ordering, the progress output, and the failure paths.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from cli._init_boundaries import _aggregate_scaffold_boundaries
from cli._init_helpers import (
    ensure_agents_md,
    ensure_entrypoint_symlink,
    materialize_ci_workflow,
    materialize_dockerfiles,
    materialize_makefile_targets,
)
from cli._init_registries import (
    CONFIG_FILE,
    CORE_DIR,
    STATE_DIR,
    TEMPLATES_DIR,
    _get_adapter_registry,
    _get_stack_registry,
)
from cli._init_scaffold import (
    _apply_template,
    _copy_workflow_docs,
    _link_stack_skills,
    _overlay_scaffold,
    _run_adapter_install,
)
from cli._init_world import (
    _build_world,
    _derive_verify_from_world,
    _load_config,
    _save_config,
)
from cli.config_composer import compose_coding_os_configs
from cli.core_version import stamp_core_version


def _run_scaffold_phase(
    agents: list[str],
    template: tuple[str, ...],
    project: Path,
    *,
    today: str | None = None,
    no_register: bool = False,
    do_index: bool = True,
    graph_index: bool = False,
    active_preset=None,
    extra_skills: list[str] | None = None,
    project_summary: str | None = None,
    disabled_modules: list[str] | None = None,
) -> None:
    """Original scaffolding body — extracted so it can be redirected in JSON mode.

    `today` is an optional ISO-8601 override for {{DATE}} substitution
    in scaffolded files (used by golden parity tests for determinism).

    `no_register` skips the global registry write (step 12). Sandbox
    fixtures (manifest-regen, golden parity tests) pass it so disposable
    temp dirs don't pollute ~/.coding-os/registry.json.
    """

    # 1. Create state directory
    state = project / STATE_DIR
    state.mkdir(parents=True, exist_ok=True)
    click.echo(f"  Created {STATE_DIR}/")
    stamp_core_version(state)
    # First-edit grace marker (TASK-372): lets the agent's first legitimate code
    # edit in a brand-new project skip the doc-anchor BLOCK. enforce-doc-anchor.sh
    # consumes it on that first edit, so the grace is exactly one edit, bounded.
    (state / ".fresh-init").touch()

    # 2. Initialize DB directory
    db_path = state / "coding-os.db"
    if not db_path.exists():
        # Initialize the database
        brain_dir = str(CORE_DIR / "thinking_os")
        init_code = (
            "import sys; "
            f"sys.path.insert(0, {brain_dir!r}); "
            "from database import init_db; "
            f"init_db({str(db_path)!r})"
        )
        env = os.environ.copy()
        env["COS_DB_PATH"] = str(db_path)
        proc = subprocess.run(
            [sys.executable, "-c", init_code],
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            click.echo("  ERROR: failed to initialize thinking_os database", err=True)
            if proc.stderr:
                click.echo(proc.stderr.strip(), err=True)
            click.echo(
                "  HINT: missing Python deps are the usual cause — run "
                "`uv sync --extra rag` in the coding-os checkout, then re-run `cos init` "
                "(machine prerequisites: `cos doctor --bootstrap`)",
                err=True,
            )
            raise SystemExit(1)
        click.echo("  Initialized thinking_os database")

    # 3. Generate config
    config = {
        "version": "1.0",
        "agents": agents,
        "templates": list(template),
        "state_dir": STATE_DIR,
        "code_extensions": ["py", "ts", "tsx", "js", "jsx"],
        "verify": {},
        "protected_files": [],
    }
    if active_preset is not None:
        # Provenance + pass-through for later layers: extra-skill linking is
        # TASK-370, module toggle behavior is TASK-349.
        config["preset"] = active_preset.id
        if active_preset.skills:
            config["extra_skills"] = list(active_preset.skills)
        if active_preset.modules:
            config["modules"] = dict(active_preset.modules)
    # CLI / wizard --disable-module entries merge on top of preset-declared
    # module state; the module_toggles pass below disables them in dependency
    # order (set_module_enabled refuses invalid chains, e.g. docs while tasks on).
    if disabled_modules:
        merged_modules = dict(config.get("modules") or {})
        for module_id in disabled_modules:
            merged_modules[module_id] = False
        config["modules"] = merged_modules
    if extra_skills:
        # --skills / wizard extras merge on top of preset-declared ones.
        config["extra_skills"] = list(
            dict.fromkeys([*(config.get("extra_skills") or []), *extra_skills])
        )
    _save_config(project, config)
    # Preset/wizard module toggles land in project state BEFORE the scaffold
    # copy so tag-driven docs composition sees them (TASK-360). Disable order:
    # dependents first (the registry refuses chains, e.g. docs before tasks).
    module_toggles = {k: v for k, v in (config.get("modules") or {}).items() if v is False}
    if module_toggles:
        from cli.subsystems import load_subsystems, set_module_enabled

        registry_modules = load_subsystems()

        def _dependents_being_disabled(module_id: str) -> int:
            # Dependents disable BEFORE their dependencies (the registry
            # refuses e.g. docs-off while tasks is still enabled).
            return sum(
                1
                for other in module_toggles
                if other in registry_modules and module_id in registry_modules[other].depends_on
            )

        ordered = sorted(module_toggles, key=_dependents_being_disabled)
        for module_id in ordered:
            toggle = set_module_enabled(project, module_id, False)
            if not toggle.ok:
                click.echo(f"  WARN: module '{module_id}': {toggle.reason}", err=True)
            else:
                click.echo(f"  Module disabled per preset: {module_id}")
        # SI-1 (TASK-439): route init through the SAME runtime-allowlist path
        # as `cos module disable`. set_module_enabled alone only flips state;
        # without this, .coding-os/disabled-hook-scripts is never written at
        # init time and the disabled modules' hooks keep firing. AGENTS.md is
        # written fresh by the scaffold copy below, so only the allowlist needs
        # regenerating here (not the full toggle_and_regen).
        from cli.project_overrides import write_runtime_allowlist

        allowlist = write_runtime_allowlist(project)
        click.echo(f"  Runtime hook allowlist → {allowlist.relative_to(project)}")
    if project_summary and project_summary.strip():
        # Onboarding intake — consumed by the description→PRD pipeline (TASK-364).
        meta_dir = project / "docs" / "_meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "project-description.md").write_text(
            "# Project Description (onboarding intake)\n\n" + project_summary.strip() + "\n",
            encoding="utf-8",
        )
        click.echo("  Seeded docs/_meta/project-description.md")
        # Docs-module gate: preset/wizard module toggles are stored in config
        # (behavior SSOT lands with TASK-349); docs defaults ON.
        if (config.get("modules") or {}).get("docs", True):
            from cli.setup import seed_prd_from_text

            seeded = seed_prd_from_text(project, project_summary, date=today)
            if seeded:
                click.echo(f"  Seeded {len(seeded)} PRD doc(s): {', '.join(seeded)}")
    click.echo(f"  Generated {CONFIG_FILE}")

    # 4. Run adapter install for each agent
    for agent in agents:
        click.echo(f"\nInstalling {agent} adapter...")
        _run_adapter_install(agent, project)

    # 5. Apply templates (agent-agnostic content first)
    for t in template:
        click.echo(f"\nApplying template: {t}")
        # Pass first agent for path-scoped rules; additional agents get
        # rules via their own adapter install or add-adapter.
        _apply_template(t, project, agent=agents[0])

    # 5b. Link stack-scoped skills into each agent's skills_dir.
    if template:
        for agent in agents:
            _link_stack_skills(agent, template, project)

    # 5c. A module disabled above must shed its owned skills too (audit D2-1):
    # the adapter install (step 4) links every core skill, so init reaches the
    # same skill-parity `cos module disable` has at runtime by running the same
    # ref-counted cascade (a skill another enabled module owns is kept).
    if module_toggles:
        from cli.module_commands import cascade_module_commands
        from cli.skill_commands import cascade_module_skills

        for module_id in module_toggles:
            try:
                cascade = cascade_module_skills(project, module_id, enabled=False)
            except Exception as exc:
                click.echo(f"  WARN: skill cascade for '{module_id}' skipped ({exc})", err=True)
            else:
                if cascade["unlinked"]:
                    click.echo(
                        f"  Skills unlinked ({module_id} off): {', '.join(cascade['unlinked'])}"
                    )
            try:
                cmd_cascade = cascade_module_commands(project, module_id, enabled=False)
            except Exception as exc:
                click.echo(f"  WARN: command cascade for '{module_id}' skipped ({exc})", err=True)
            else:
                if cmd_cascade["unlinked"]:
                    click.echo(
                        f"  Commands unlinked ({module_id} off): "
                        f"{', '.join(cmd_cascade['unlinked'])}"
                    )

    # 6. Aggregate base + stacks + adapter into a world.
    # Use the first agent for world building (substitutions, AGENTS.md).
    # All adapters share the same core content; adapter-specific setup
    # was handled in step 4.
    for w in _get_stack_registry().warnings:
        click.echo(f"  WARN: {w}", err=True)
    world = _build_world(agents[0], template, project, today=today)
    for msg in world.conflicts:
        click.echo(f"  WARN: {msg}", err=True)
    substitutions = world.substitutions
    if project_summary and project_summary.strip():
        # The user's own words replace the generic default everywhere the
        # {{PROJECT_DESCRIPTION}} placeholder appears (TASK-364).
        substitutions = {
            **substitutions,
            "PROJECT_DESCRIPTION": " ".join(project_summary.split()),
        }

    # 6b. Patch .coding-os.yaml.verify with derived commands.
    # step 3 wrote an empty dict because the world is only available here.
    # enforce-verify.sh reads this map to know which suite to require per
    # changed-file glob, so we must populate it before any hook runs.
    verify_map = _derive_verify_from_world(world)
    if verify_map:
        existing = _load_config(project) or {}
        existing["verify"] = verify_map
        _save_config(project, existing)
        click.echo(f"  Populated verify config: {', '.join(sorted(verify_map))}")

    # 7. Overlay scaffold files (_base + each template overlay) with placeholder resolution
    copied = _overlay_scaffold(project, template, substitutions)
    if copied:
        click.echo(f"  Copied {copied} scaffold file(s) (docs/, governance/, playbooks/, ...)")

    # 7b. Compose .coding-os/ configs (rag/scrumban/domain) from base + every
    # installed stack — deep-merged, multi-stack-correct. The overlay (step 7)
    # deliberately skips these. SSOT: docs/engineering/config-composition.md.
    config_conflicts: list[str] = []
    composed = compose_coding_os_configs(
        project, state, list(template), templates_dir=TEMPLATES_DIR, conflicts=config_conflicts
    )
    if composed:
        click.echo(f"  Composed {len(composed)} .coding-os config(s): {', '.join(composed)}")
    for line in config_conflicts:
        click.echo(f"  WARN: config conflict (later wins) — {line}", err=True)

    # 8. Copy thinking_os reference doc from src/core/docs/
    _copy_workflow_docs(project)

    # 9. Copy Makefile.base verbatim. The `cos` CLI binary (installed
    # via `uv tool install`) owns path discovery — Makefile.base calls
    # `cos docs-index`, `cos task-sync`, etc. and stays fully portable.
    makefile_src = TEMPLATES_DIR / "_base" / "Makefile.base"
    if makefile_src.exists():
        makefile_dest = state / "Makefile.base"
        shutil.copy2(makefile_src, makefile_dest)
        click.echo(f"  Copied Makefile.base to {STATE_DIR}/")

        # Materialize stack-contributed targets (lint-backend, test-backend-<id>,
        # …) into a generated include so the suites named in AGENTS.md are
        # runnable. Writes .coding-os/Makefile.stacks; the project Makefile (if
        # it already exists) gets the `-include` wired in idempotently.
        materialize_makefile_targets(project, state, world)

        # Create a project Makefile if none exists
        project_makefile = project / "Makefile"
        if not project_makefile.exists():
            project_makefile.write_text(
                f"# Project Makefile\n"
                f"# coding-os universal targets\n"
                f"include {STATE_DIR}/Makefile.base\n"
                f"-include {STATE_DIR}/Makefile.stacks\n\n"
                f"# Add your project-specific targets below:\n\n"
            )
            click.echo("  Generated Makefile")

    # CI workflow + backend Dockerfiles — gated behind the `cicd` module (off in
    # lean profiles), independent of the Makefile.base copy so init mirrors the
    # update.py materialize step. Both delegate to generated artifacts.
    from cli.subsystems import module_state

    if module_state(project).get("cicd", True):
        if materialize_ci_workflow(project, world):
            click.echo("  Generated .github/workflows/ci.yml")
        if materialize_dockerfiles(project, world):
            click.echo("  Generated backend Dockerfile(s)")

    # 9b. Aggregate scaffold-boundary.yaml from every installed stack so the
    # consumer-side enforce-scaffold-boundary.sh hook can enforce subtree
    # isolation at runtime. SSOT spec: docs/governance/scaffold-boundary-contract.md.
    _aggregate_scaffold_boundaries(project, state, template)

    # 10. Generate AGENTS.md by composing fragments from base + stacks.
    # No template file is read; the content is assembled by render_agents_md()
    # from the fragments registered in base.yaml::agents_md_sections (and any
    # fragments stacks contribute via their own stack.yaml::agents_md_sections).
    if ensure_agents_md(project, world):
        click.echo("  Generated AGENTS.md")

    # 10b. Link each agent's own root entrypoint (Claude reads CLAUDE.md, not
    # AGENTS.md) at that one SSOT. Filename comes from the adapter's own yaml,
    # never a literal here (Rule 11).
    for agent in agents:
        entrypoint = _get_adapter_registry()[agent].entrypoint_file
        if ensure_entrypoint_symlink(project, entrypoint):
            click.echo(f"  Linked {entrypoint} → AGENTS.md")

    # 11. Initial RAG indexing of the scaffolded docs so `cos_doc_search`
    # returns hits from the very first session. Without this, the
    # consumer's document_chunks table is empty until the user runs
    # `make docs-index` manually — Rule 19 (doc-sync) enforcement is
    # also effectively off until something hits the FTS index.
    # Skipped under --no-index: the index lives in the gitignored runtime DB,
    # so fast/CI/fixture scaffolds (e.g. golden capture) don't pay the
    # ~15s embedding-model load for output they discard.
    if do_index:
        _initial_doc_index(project, state)
    else:
        click.echo("  Skipped initial doc index (--no-index)")

    # 11b. Seed the knowledge graph so the Hub Graph tab + cos_graph_* tools work
    # from the first session with NO manual `cos graph-reindex` (TASK-423). Built
    # when --index (the default) OR --graph-index is set — the latter lets a fast
    # --no-index create (the Hub Composer) still get a populated graph (AST walk,
    # no embedding model), while CI/fixture scaffolds that pass only --no-index
    # stay graph-free. Inside, it is also gated on the graph module being enabled
    # — a disabled graph module owns no tools, so building its graph is wasted.
    if do_index or graph_index:
        _initial_graph_index(project, state)
    else:
        click.echo("  Skipped initial graph index (--no-index)")

    # 12. Register project in the global ~/.coding-os/registry.json so the
    # Hub web UI (`cos hub`) can enumerate it and serve its sqlite DB.
    # Skipped when --no-register passed (sandbox fixtures use disposable
    # temp dirs — registering them creates stale entries doctor then warns
    # about in hub.project_paths_exist).
    if no_register:
        click.echo("  Skipped hub registry write (--no-register)")
    else:
        try:
            from cli.registry import add_project as _registry_add_project

            entry = _registry_add_project(project)
            click.echo(f"  Registered in hub registry: {entry.slug}")
        except Exception as exc:
            # Registry is non-fatal — a failed write should not break init.
            click.echo(f"  WARN: could not register project in hub registry: {exc}", err=True)
            click.echo(
                "  HINT: register later with `cos registry add <project-path>` "
                "so the hub web UI can see this project",
                err=True,
            )


def _initial_doc_index(project: Path, state: Path) -> None:
    """Seed document_chunks + FTS for a freshly-scaffolded project."""
    rag_config = state / "rag-config.yaml"
    if not rag_config.exists():
        return
    db_path = state / "coding-os.db"
    brain_dir = str(CORE_DIR / "thinking_os")
    code = (
        "import sys; "
        f"sys.path.insert(0, {brain_dir!r}); "
        "from database import init_db; "
        "from doc_indexer import index_docs; "
        "from pathlib import Path; "
        f"conn = init_db({str(db_path)!r}); "
        f"stats = index_docs(conn, Path({str(rag_config)!r}), Path({str(project)!r})); "
        "conn.close(); "
        "print(f\"  Indexed {stats['updated_files']} doc(s), {stats['new_chunks']} chunk(s)\")"
    )
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        click.echo(result.stdout.rstrip())
    elif result.returncode != 0:
        # Non-fatal: missing yaml / embeddings extras shouldn't break init.
        click.echo(
            f"  WARN: initial doc index skipped: {result.stderr.strip().splitlines()[-1] if result.stderr else 'unknown'}",
            err=True,
        )
        click.echo(
            "  HINT: doc search stays empty until indexed — install extras with "
            "`uv sync --extra rag` in the coding-os checkout, then run `make docs-index` here",
            err=True,
        )


def _initial_graph_index(project: Path, state: Path) -> None:
    """Build the knowledge graph for a fresh project when the graph module is on (TASK-423)."""
    try:
        from cli.subsystems import module_state

        if not module_state(project).get("graph", True):
            click.echo("  Skipped graph index (graph module disabled)")
            return
    except Exception:
        # State unreadable → graph is on by default; fall through and build.
        pass
    db_path = state / "coding-os.db"
    core_path = str(CORE_DIR)
    brain_dir = str(CORE_DIR / "thinking_os")
    # include_docs=False: the docs RAG layer was just seeded by
    # _initial_doc_index; here we want only the graph (AST + doc structure),
    # which needs no embedding model. Runs in-process python (sys.executable),
    # NOT the global `cos`, so an env without the graph deps fails fast instead
    # of doing heavy work (mirrors _initial_doc_index).
    code = (
        "import sys; "
        f"sys.path.insert(0, {core_path!r}); "
        f"sys.path.insert(0, {brain_dir!r}); "
        "from graph_os.ingest.base import walk_local; "
        "from graph_os.tools.reindex_dispatch import dispatch; "
        f"plan = walk_local({str(project)!r}); "
        "reports = [dispatch(str(f), project_root="
        f"{str(project)!r}, db_path={str(db_path)!r}, "
        "include_docs=False, link_stubs=True) for f in plan.files]; "
        "ok = sum(1 for r in reports if r.get('status') == 'ok'); "
        "print(f'  Built knowledge graph: {ok}/{len(reports)} file(s) indexed')"
    )
    env = os.environ.copy()
    env["COS_DB_PATH"] = str(db_path)
    # Bounded so a very large repo never blows the init budget (the Hub Composer
    # wraps `cos init` in its own timeout). On timeout the graph is left empty —
    # valid, since cos_graph_export returns ok([]) for an empty graph — with a
    # clear repair HINT, far better than hard-failing a half-created project.
    timeout_s = int(os.environ.get("COS_INIT_GRAPH_TIMEOUT", "180"))
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        click.echo(
            f"  WARN: initial graph index exceeded {timeout_s}s — graph left empty", err=True
        )
        click.echo("  HINT: graph stays empty until built — run `cos graph-reindex` here", err=True)
        return
    if result.returncode == 0 and result.stdout.strip():
        click.echo(result.stdout.rstrip())
    elif result.returncode != 0:
        # Non-fatal: missing graph deps shouldn't break init.
        detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown"
        click.echo(f"  WARN: initial graph index skipped: {detail}", err=True)
        click.echo(
            "  HINT: graph stays empty until built — run `cos graph-reindex` here",
            err=True,
        )
