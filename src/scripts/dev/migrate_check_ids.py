from __future__ import annotations

import re
import sys
from pathlib import Path

ID_MAP: dict[str, str] = {
    "C1": "config.file_present",
    "C2": "state.directory_present",
    "C3": "database.openable",
    "C4": "database.schema_current",
    "C5": "database.tables_present",
    "C6": "scaffold.roots_present",
    "C7": "adapter.configured",
    "C8": "scaffold.manifest_fresh",
    "C9": "scaffold.placeholders_resolved",
    "C10": "mcp.self_test_passes",
    "C11": "stack.registry_valid",
    "C12": "stack.category_balance",
    "C13": "stack.skills_linked",
    "C14": "mcp.portable",
    "C15": "mcp.actually_launches",
    "C16": "docs.agents_md_present",
    "C17": "graph.freshness",
    "C18": "graph.parse_error_rate",
    "C19": "graph.backend_responsive",
    "C20": "graph.groups_configured",
    "C21": "graph.embedding_migration",
    "C22": "graph.embedding_dimensions",
    "C23": "graph.cascade_overflow",
    "C24": "graph.kuzu_state",
    "C25": "graph.evidence_table",
    "C26": "graph.orphan_symbols",
    "C27": "graph.legacy_kinds",
    "C28": "cognition.registries_present",
    "C29": "hook.coverage",
    "C30": "scheduled.cron_configured",
    "C31": "presence.no_zombies",
    "C32": "runtime.optional_extras_installed",
    "C33": "adapter.all_installed_healthy",
    "C34": "hub.http_responsive",
    "C35": "docs.markdown_link_integrity",
    "C36": "graph.uid_consistency",
    "C37": "scaffold.regen_artifacts_fresh",
    "C38": "board.config_yamls_valid",
    "C39": "hub.project_paths_exist",
    "C40": "state.size_within_budget",
    "C41": "mcp.dispatcher_modules_importable",
    "C42": "mcp.envelope_contract_sample",
    "C43": "runtime.cli_binary_health",
    "C44": "scaffold.boundary_yamls_valid",
    "C45": "adapter.identity_file_present",
    "C46": "adapter.symlinks_healthy",
    "C47": "hub.consumer_hook_symlinks_healthy",
    "C48": "hook.cos_env_sourced",
    "C50": "board.wip_within_caps",
    "C51": "board.no_stale_tasks",
    "C52": "board.frontmatter_valid",
    "C53": "board.index_synced",
}

CHECK_CALL = re.compile(
    r'((?:CheckResult|_CR)\(\s*)"(C\d+)"\s*,\s*"([a-z_]+)"',
    flags=re.DOTALL,
)

# Standalone "C\d+" literal in tests + comments — only rewritten in test files.
ID_LITERAL = re.compile(r'"(C\d+)"')


def rewrite(text: str, path: Path) -> tuple[str, int]:
    replacements = 0

    def sub(match: re.Match) -> str:
        nonlocal replacements
        prefix, old_id, _slug = match.group(1), match.group(2), match.group(3)
        new_id = ID_MAP.get(old_id)
        if new_id is None:
            print(f"  WARN: unmapped id {old_id} in {path}", file=sys.stderr)
            return match.group(0)
        replacements += 1
        return f'{prefix}"{new_id}"'

    return CHECK_CALL.sub(sub, text), replacements


def rewrite_literals(text: str, path: Path) -> tuple[str, int]:
    replacements = 0

    def sub(match: re.Match) -> str:
        nonlocal replacements
        old_id = match.group(1)
        new_id = ID_MAP.get(old_id)
        if new_id is None:
            return match.group(0)
        replacements += 1
        return f'"{new_id}"'

    return ID_LITERAL.sub(sub, text), replacements


def main() -> int:
    targets = [
        Path("src/cli/doctor.py"),
        Path("src/cli/doctor_graph.py"),
        Path("src/cli/doctor_extras.py"),
        Path("src/cli/doctor_board.py"),
    ]
    test_targets = [
        Path("tests/test_doctor.py"),
        Path("tests/test_hooks_phase_f.py"),
        Path("tests/test_persona_integration.py"),
    ]
    total = 0
    for path in targets:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        rewritten, count = rewrite(original, path)
        if count == 0:
            print(f"  {path}: no matches")
            continue
        path.write_text(rewritten, encoding="utf-8")
        print(f"  {path}: {count} rewritten")
        total += count
    for path in test_targets:
        if not path.exists():
            print(f"missing: {path}", file=sys.stderr)
            continue
        original = path.read_text(encoding="utf-8")
        rewritten, count = rewrite_literals(original, path)
        if count == 0:
            print(f"  {path}: no test literals matched")
            continue
        path.write_text(rewritten, encoding="utf-8")
        print(f"  {path}: {count} literals rewritten")
        total += count
    print(f"total replacements: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
