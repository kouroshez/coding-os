#!/usr/bin/env python3
"""Generate core/scaffold_manifest.json by initializing fresh sandboxes.

For each (agent, template) combination we care about, runs `cos init`
into a temp directory with a fixed placeholder name, then records the
set of relative paths produced. Doctor compares this set against a
live project to detect missing files.

Path-only (no hashes) — placeholder substitution produces different
content per project name, so hash diffs would be noisy. Hash drift is
a follow-up feature.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "src" / "core" / "scaffold_manifest.json"
FIXTURE_NAME = "cos-manifest-fixture"


def _discover_sections() -> list[tuple[str, str, list[str]]]:
    """Compute (section_id, agent, templates) tuples from live registries.

    Produces (for each adapter):
      - <agent>_base                — base scaffold only
      - <agent>_<stack>             — base + that stack

    Adding a new stack (templates/<id>/stack.yaml) or adapter
    (adapters/<id>/adapter.yaml) automatically shows up here — no edits
    to this script are needed.
    """
    # Late imports so the script stays usable if cli imports break.
    sys.path.insert(0, str(REPO_ROOT))
    from cli.adapter_registry import load_adapter_registry  # noqa: E402
    from cli.stack_registry import load_stack_registry  # noqa: E402

    adapters = load_adapter_registry(REPO_ROOT / "src" / "adapters")
    stacks = load_stack_registry(REPO_ROOT / "src" / "templates")

    sections: list[tuple[str, str, list[str]]] = []
    for agent_id in sorted(adapters):
        sections.append((f"{agent_id}_base", agent_id, []))
        for stack_id in sorted(stacks.keys()):
            sections.append((f"{agent_id}_{stack_id}", agent_id, [stack_id]))
    return sections


# Legacy constant retained for back-compat with any external caller.
# Computed lazily because the registries may change between invocations.
SECTIONS: list[tuple[str, str, list[str]]] = _discover_sections()

# Runtime state files — single source of truth lives in cli/doctor.py.
sys.path.insert(0, str(REPO_ROOT))
from cli.doctor import IGNORED_PREFIXES, RUNTIME_PATHS  # noqa: E402


def _scaffold(agent: str, templates: list[str], target: Path) -> None:
    cmd = [
        sys.executable, "-m", "cli.main", "init",
        "--agent", agent,
        "--project-dir", str(target.parent),
        "--name", target.name,
        "--no-git",
        "--force",
        "--no-register",
    ]
    for t in templates:
        cmd.extend(["--template", t])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )


def _collect_paths(root: Path) -> list[str]:
    """Return sorted relative paths, excluding runtime state and VCS/build dirs."""
    paths = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in RUNTIME_PATHS:
            continue
        if any(rel.startswith(prefix) for prefix in IGNORED_PREFIXES):
            continue
        paths.append(rel)
    return sorted(paths)


def build_manifest() -> dict:
    manifest: dict = {
        "version": 1,
        "fixture_name": FIXTURE_NAME,
        "sections": {},
    }
    with tempfile.TemporaryDirectory(prefix="cos-manifest-") as tmp:
        tmp_dir = Path(tmp)
        for section_id, agent, templates in SECTIONS:
            target = tmp_dir / section_id / FIXTURE_NAME
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                _scaffold(agent, templates, target)
            except subprocess.CalledProcessError as exc:
                print(
                    f"[manifest] ABORTING — {section_id} init failed; "
                    f"manifest NOT written.\n"
                    f"  stderr: {exc.stderr}\n",
                    file=sys.stderr,
                )
                raise
            paths = _collect_paths(target)
            manifest["sections"][section_id] = {
                "agent": agent,
                "templates": templates,
                "paths": paths,
                "count": len(paths),
            }
            print(f"[manifest] {section_id}: {len(paths)} files")
            shutil.rmtree(target.parent)
    return manifest


def main() -> int:
    manifest = build_manifest()
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(s["count"] for s in manifest["sections"].values())
    print(f"[manifest] wrote {MANIFEST_PATH.relative_to(REPO_ROOT)} "
          f"({len(manifest['sections'])} sections, {total} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
