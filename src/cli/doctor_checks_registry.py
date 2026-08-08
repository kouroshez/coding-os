"""Private sibling of cli.doctor — checks are re-exported by the kernel; import cli.doctor."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

from cli._resources import adapters_dir, templates_dir

from ._doctor_shared import (  # noqa: F401
    _DOCTOR_CFG,
    CODING_OS_ROOT,
    CONFIG_FILE,
    IGNORED_PREFIXES,
    MANIFEST_PATH_DEFAULT,
    MCP_SERVER_PATH,
    PLACEHOLDER_RE,
    RUNTIME_PATHS,
    SEV_FAIL,
    SEV_PASS,
    SEV_WARN,
    STATE_DIR_DEFAULT,
    CheckResult,
    DoctorReport,
    _derive_expected_schema_version,
    _load_doctor_config,
    _load_runtime_paths,
    _scan_project_files,
    _tick,
)

logger = logging.getLogger(__name__)


def _check_stack_registry_consistency(report: DoctorReport) -> None:
    """stack.registry_valid — every stack declared in .coding-os.yaml::templates exists in the registry.

    If a stack was installed and later removed from the coding-os distribution,
    the project config still lists it — FAIL so the user knows to either add
    the stack back or remove it from their config.
    """
    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_WARN,
                f"could not load stack registry: {exc}",
            )
        )
        return

    missing = [t for t in report.templates if t not in registry]
    if missing:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_FAIL,
                f"stacks in config not found in templates/: {', '.join(missing)}",
                {"missing": missing},
            )
        )
    elif not report.templates:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                "no stacks installed (base-only project)",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.registry_valid",
                SEV_PASS,
                f"all {len(report.templates)} installed stack(s) present in registry",
                {"installed": report.templates},
            )
        )


def _check_category_balance(report: DoctorReport) -> None:
    """stack.category_balance — informational WARN when two or more stacks of the same category
    are installed (e.g. two backend stacks). The project will work, but the
    later stack wins on conflicting substitution keys — the user should know."""
    if len(report.templates) < 2:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "single-stack or base-only project",
            )
        )
        return

    try:
        from cli.stack_registry import load_stack_registry

        registry = load_stack_registry(templates_dir())
    except Exception:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                "registry unavailable, skipping",
            )
        )
        return

    categories: dict[str, list[str]] = {}
    for stack_id in report.templates:
        if stack_id in registry:
            cat = registry[stack_id].category
            categories.setdefault(cat, []).append(stack_id)

    duplicates = {c: ids for c, ids in categories.items() if len(ids) >= 2}
    if duplicates:
        details = ", ".join(f"{cat}: {', '.join(ids)}" for cat, ids in duplicates.items())
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_WARN,
                f"multiple stacks in same category ({details}) — last stack wins on conflicts",
                {"duplicates": duplicates},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.category_balance",
                SEV_PASS,
                f"{len(report.templates)} stacks in {len(categories)} distinct categories",
            )
        )


def _check_stack_skills_linked(project: Path, report: DoctorReport) -> None:
    """stack.skills_linked — every installed stack's skills are symlinked into the agent's skills dir.

    Detects the B1 regression where `.claude/skills/python-django/SKILL.md`
    was missing even though `--template django` was declared. We consult the
    adapter registry to find `skills_dir` (null for Codex → skip check) and
    the src/templates/<stack>/skills/ source of truth.
    """
    if not report.templates:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no stacks installed"))
        return
    if not report.agent:
        report.checks.append(CheckResult("stack.skills_linked", SEV_PASS, "no agent configured"))
        return
    try:
        from cli.adapter_registry import load_adapter_registry

        adapters = load_adapter_registry(adapters_dir())
    except Exception as exc:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_WARN,
                f"could not load adapter registry: {exc}",
            )
        )
        return
    profile = adapters.get(report.agent)
    if profile is None or not profile.skills_dir:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"adapter '{report.agent}' has no skills_dir — skipped",
            )
        )
        return

    skills_dir = project / profile.skills_dir
    expected: list[tuple[str, str]] = []  # (stack, skill_name)
    for stack in report.templates:
        stack_skills = templates_dir(stack, "skills")
        if not stack_skills.exists():
            continue
        for entry in stack_skills.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                expected.append((stack, entry.name))

    if not expected:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                "no stack skills to link",
            )
        )
        return

    missing = []
    for stack, name in expected:
        link = skills_dir / name / "SKILL.md"
        if not link.exists():
            missing.append(f"{stack}:{name}")

    if missing:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_FAIL,
                f"missing stack skill links: {', '.join(missing)} — run `cos update` to repair",
                {"missing": missing},
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "stack.skills_linked",
                SEV_PASS,
                f"all {len(expected)} stack skill(s) linked",
            )
        )


def _check_mcp_portable(project: Path, report: DoctorReport) -> None:
    """mcp.portable — .mcp.json coding-os entry uses the `cos server-start` wrapper.

    The wrapper form lets the project survive coding-os relocations and
    upgrades: the `cos` binary on PATH resolves the server location, no
    absolute dev path is hardcoded. A plain `uv run --directory <abs>`
    entry is tolerated as a bootstrap fallback but flagged WARN.
    """
    mcp_path = project / ".mcp.json"
    if not mcp_path.exists():
        report.checks.append(CheckResult("mcp.portable", SEV_PASS, "no .mcp.json (skip)"))
        return
    try:
        import json as _json

        data = _json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        report.checks.append(CheckResult("mcp.portable", SEV_FAIL, f"invalid JSON: {exc}"))
        return
    entry = (data.get("mcpServers") or {}).get("coding-os")
    if entry is None:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                "no coding-os MCP entry (skip)",
            )
        )
        return
    command = entry.get("command")
    if command == "cos":
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                "uses `cos server-start` wrapper (portable)",
            )
        )
        return
    args = entry.get("args") or []
    has_abs_cos_path = any(isinstance(a, str) and "/core/thinking_os" in a for a in args)
    if has_abs_cos_path:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_WARN,
                "hardcoded absolute path — runs fine locally but won't "
                "survive coding-os relocation. Install `cos` on PATH and "
                "re-run the adapter install to switch to the wrapper.",
            )
        )
    else:
        report.checks.append(
            CheckResult(
                "mcp.portable",
                SEV_PASS,
                f"unknown command form '{command}' — assumed portable",
            )
        )


def _load_coding_os_mcp_launch(
    project: Path,
    agent: str | None,
) -> tuple[str | None, list[str], dict[str, str], str | None, str | None]:
    """Return the coding-os MCP launch config from any adapter (Claude/Codex/Cursor)."""

    def _load_claude_json(
        path: Path,
    ) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        if not path.exists():
            return None
        try:
            import json as _json

            data = _json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return None, [], {}, str(path), f"invalid JSON: {exc}"
        entry = (data.get("mcpServers") or {}).get("coding-os")
        if entry is None:
            return None, [], {}, str(path), None
        env = {str(k): str(v) for k, v in (entry.get("env") or {}).items()}
        return entry.get("command"), list(entry.get("args") or []), env, str(path), None

    def _load_codex_toml(path: Path) -> tuple[str | None, list[str], dict[str, str]] | None:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        match = re.search(r"(?ms)^\[mcp_servers\.coding-os\]\s*\n(?P<body>.*?)(?=^\[|\Z)", text)
        if not match:
            return None
        body = match.group("body")
        cmd_match = re.search(r'(?m)^[ \t]*command[ \t]*=[ \t]*"([^"]+)"[ \t]*$', body)
        if not cmd_match:
            return "", [], {}
        args_match = re.search(r"(?ms)^[ \t]*args[ \t]*=[ \t]*\[(.*?)\][ \t]*$", body)
        args = []
        if args_match:
            args = re.findall(r'"((?:[^"\\]|\\.)*)"', args_match.group(1))
            args = [bytes(item, "utf-8").decode("unicode_escape") for item in args]
        env: dict[str, str] = {}
        env_match = re.search(r"(?ms)^[ \t]*env[ \t]*=[ \t]*\{(.*?)\}[ \t]*$", body)
        if env_match:
            for key, value in re.findall(
                r'"((?:[^"\\]|\\.)*)"[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"', env_match.group(1)
            ):
                env[bytes(key, "utf-8").decode("unicode_escape")] = bytes(value, "utf-8").decode(
                    "unicode_escape"
                )
        return cmd_match.group(1), args, env

    def _load_codex(
        path: Path,
    ) -> tuple[str | None, list[str], dict[str, str], str | None, str | None] | None:
        loaded = _load_codex_toml(path)
        if loaded is None:
            return None
        command, args, env = loaded
        return command, args, env, str(path), None

    # Registry-driven loader selection — each adapter declares its
    # mcp_launch.loader and config_paths in adapter.yaml so no agent id
    # is hardcoded here (Rule 12 / tests/test_no_hardcoded_stacks).
    from cli.adapter_registry import load_adapter_registry

    adapters = load_adapter_registry(adapters_dir())

    loader_fns = {
        "claude_json": _load_claude_json,
        "codex_toml": _load_codex,
        # Cursor's .cursor/mcp.json uses the same mcpServers.coding-os JSON
        # shape as Claude (see src/adapters/cursor/install.sh), so it reuses
        # the Claude JSON loader. Without this entry the Cursor MCP launch
        # diagnostic was silently skipped (spec.loader not in loader_fns).
        "cursor_mcp_json": _load_claude_json,
    }

    loaders: list[tuple[str, Path]] = []
    for aid, profile in adapters.items():
        if agent and agent != aid:
            continue
        spec = profile.mcp_launch
        if spec is None:
            continue
        if spec.loader not in loader_fns:
            continue
        for cp in spec.config_paths:
            root = project if cp.scope == "project" else Path.home()
            loaders.append((spec.loader, root / cp.path))

    for loader_name, path in loaders:
        fn = loader_fns.get(loader_name)
        if fn is None:
            continue
        loaded = fn(path)
        if loaded is not None:
            return loaded

    return None, [], {}, None, None


def _check_mcp_actually_launches(project: Path, report: DoctorReport) -> None:
    """mcp.actually_launches — simulate the exact MCP launch path the active agent config uses.

    mcp.self_test_passes runs `server.py --test` with an explicit COS_DB_PATH env — that
    verifies the server code works but bypasses the agent launch config
    entirely. mcp.actually_launches closes that gap: it reads coding-os MCP launch config
    from Claude or Codex, runs the declared command with the project
    root as cwd, feeds a real `initialize` handshake, and expects a
    valid JSON-RPC response.
    """
    command, args, entry_env, source_path, load_error = _load_coding_os_mcp_launch(
        project, report.agent
    )
    if load_error:
        report.checks.append(CheckResult("mcp.actually_launches", SEV_FAIL, load_error))
        return
    if source_path is None:
        # Data-driven (Rule 11): list every adapter that ships an
        # install.sh under src/adapters/<id>/. New adapters appear here
        # automatically — no edit to this diagnostic when one is added.
        meta_root = Path(__file__).resolve().parent.parent.parent / "src" / "adapters"
        adapter_lines: list[str] = []
        if meta_root.is_dir():
            for adapter_yaml in sorted(meta_root.glob("*/adapter.yaml")):
                install_sh = adapter_yaml.parent / "install.sh"
                if install_sh.exists():
                    adapter_lines.append(
                        f"`bash <coding-os>/adapters/{adapter_yaml.parent.name}/install.sh`"
                    )
        if adapter_lines:
            repair = "Run " + " or ".join(adapter_lines) + " from the project root."
        else:
            repair = (
                "Run `bash <coding-os>/adapters/<adapter>/install.sh` for the "
                "adapter you use, from the project root."
            )
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                "coding-os MCP config missing — neither .mcp.json nor "
                ".codex/config.toml defines coding-os. " + repair,
            )
        )
        return
    if command is None:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                f"no coding-os MCP entry in {source_path} (skip)",
            )
        )
        return

    env = os.environ.copy()
    env.update(entry_env)

    handshake = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":'
        '{"protocolVersion":"2025-03-26","capabilities":{},'
        '"clientInfo":{"name":"cos-doctor","version":"1.0"}}}\n'
    )

    if not command:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"no command specified in {source_path}",
            )
        )
        return

    try:
        proc = subprocess.run(
            [command, *args],
            input=handshake,
            cwd=str(project),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"command not found on PATH: {command!r}. "
                f"Install via `uv tool install --editable <coding-os>`.",
            )
        )
        return
    except subprocess.TimeoutExpired:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                "launched (exceeded 20s → server is running, no crash)",
            )
        )
        return
    except OSError as exc:
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_FAIL,
                f"OS error launching: {exc}",
            )
        )
        return

    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if '"jsonrpc"' in (proc.stdout or "") and '"result"' in (proc.stdout or ""):
        report.checks.append(
            CheckResult(
                "mcp.actually_launches",
                SEV_PASS,
                "initialize handshake succeeded (server ready)",
            )
        )
        return

    if "unable to open database file" in combined or "OperationalError" in combined:
        msg = (
            "server crashed: cannot open DB. This usually means the "
            "MCP launch config uses `uv run --directory ...` which "
            "chdir's into the server tree, so `.coding-os/coding-os.db` "
            "stops resolving. Switch to the wrapper form: "
            '`command = "cos"` and `args = ["server-start"]`.'
        )
    elif "No module named" in combined or "ModuleNotFoundError" in combined:
        msg = "server crashed: missing Python dependency — rerun `uv sync`."
    else:
        tail = combined.strip().splitlines()[-3:]
        msg = f"launch failed (exit {proc.returncode}). Last output: " + " | ".join(tail)[-200:]

    report.checks.append(
        CheckResult(
            "mcp.actually_launches",
            SEV_FAIL,
            msg,
            {"stderr_tail": (proc.stderr or "")[-500:]},
        )
    )


def _check_agents_md_present(project: Path, report: DoctorReport) -> None:
    """docs.agents_md_present — AGENTS.md at the project root is the canonical instruction file.

    Read by both Claude (via AGENTS.md convention) and Codex. `cos init`
    generates it; pre-v0.2.0 projects or partial installs may be missing it.
    `cos add-adapter` and `cos update` now backfill automatically — this
    check catches projects that never ran either command since.
    """
    agents_md = project / "AGENTS.md"
    if agents_md.exists():
        report.checks.append(
            CheckResult(
                "docs.agents_md_present",
                SEV_PASS,
                "present",
                {"path": str(agents_md.relative_to(project))},
            )
        )
        return
    report.checks.append(
        CheckResult(
            "docs.agents_md_present",
            SEV_FAIL,
            "missing — run 'cos update' or 'cos add-adapter <agent>' to backfill",
            {"expected": "AGENTS.md"},
        )
    )
