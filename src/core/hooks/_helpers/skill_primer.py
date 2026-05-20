"""Build SessionStart skill-primer card from active stack manifests.

Reads installed-manifest.json::templates → resolves each stack's
stack.yaml → emits a compact card listing primary skills + per-glob
skill bindings so the agent enters the session knowing which Skill
invocations are required before code edits.

Source of truth:
  - active stacks: $COS_STATE_DIR/installed-manifest.json::templates
  - per-stack skills: src/templates/<stack>/stack.yaml::{primary_skill, skills, skill_enforcement}

Fail-open: prints nothing on any parse error (hook always exits 0).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("skill_primer")

try:
    import yaml
except ImportError as exc:
    logger.debug("yaml import failed: %s", exc)
    sys.exit(0)


def _resolve_cos_root(state_dir: Path) -> Path | None:
    manifest = state_dir / "installed-manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("manifest read failed: %s", exc)
            data = {}
        root = data.get("coding_os_root")
        if root and Path(root).is_dir():
            return Path(root)

    env_root = os.environ.get("COS_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if (parent / "src" / "templates").is_dir() and (parent / "src" / "core" / "hooks").is_dir():
            return parent
    return None


def _resolve_active_stacks(state_dir: Path, cos_root: Path) -> list[str]:
    manifest = state_dir / "installed-manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.debug("manifest read failed: %s", exc)
            data = {}
        stacks = data.get("templates") or []
        valid = [s for s in stacks if (cos_root / "src" / "templates" / s / "stack.yaml").exists()]
        if valid:
            return valid

    if (cos_root / "src" / "templates" / "meta" / "stack.yaml").exists():
        return ["meta"]
    return []


def _load_stack(cos_root: Path, stack_id: str) -> dict | None:
    path = cos_root / "src" / "templates" / stack_id / "stack.yaml"
    try:
        return yaml.safe_load(path.read_text()) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.debug("stack.yaml load failed for %s: %s", stack_id, exc)
        return None


def _format_card(stacks: list[tuple[str, dict]]) -> str:
    lines: list[str] = []
    lines.append(
        "[Skill Primer] PreToolUse Write/Edit BLOCKS without a matching domain skill loaded this session."
    )
    lines.append("")
    lines.append("Invoke required skills NOW via the Skill tool — do not wait for the block.")
    lines.append("")

    all_skills: set[str] = set()
    for stack_id, stack in stacks:
        label = stack.get("label") or stack_id
        primary = stack.get("primary_skill")
        skills_list = stack.get("skills") or []
        all_skills.update(skills_list)
        if primary:
            all_skills.add(primary)

        lines.append(f"Stack: {stack_id} ({label})")
        if primary:
            lines.append(f"  Primary: {primary}")

        enforcement = stack.get("skill_enforcement") or []
        if enforcement:
            lines.append("  Per-glob enforcement (PreToolUse Write/Edit BLOCKS):")
            seen_primary: set[str] = set()
            for row in enforcement:
                row_primary = row.get("primary")
                globs = row.get("globs") or []
                if not row_primary or not globs:
                    continue
                if row_primary in seen_primary:
                    continue
                seen_primary.add(row_primary)
                glob_preview = ", ".join(globs[:2])
                if len(globs) > 2:
                    glob_preview += f", +{len(globs) - 2}"
                lines.append(f'    {glob_preview} → Skill skill: "{row_primary}"')
        lines.append("")

    if all_skills:
        lines.append("Universally available this session:")
        lines.append("  " + " · ".join(sorted(all_skills)))
        lines.append("")

    lines.append(
        'Minimal load before any code edit: Skill skill: "clean-code" (universal) + the primary matching the file you intend to edit.'
    )
    return "\n".join(lines).rstrip()


def main() -> int:
    state_dir = Path(os.environ.get("COS_STATE_DIR") or ".coding-os")
    cos_root = _resolve_cos_root(state_dir)
    if cos_root is None:
        return 0

    stack_ids = _resolve_active_stacks(state_dir, cos_root)
    if not stack_ids:
        return 0

    stacks: list[tuple[str, dict]] = []
    for stack_id in stack_ids:
        stack = _load_stack(cos_root, stack_id)
        if stack:
            stacks.append((stack_id, stack))

    if not stacks:
        return 0

    sys.stdout.write(_format_card(stacks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
