"""Kernel hooks must not enforce one stack's architecture on every project.

`block-bad-patterns.sh` lives in the stack-agnostic kernel but rejected
`.objects.filter(...)` in any `views.py` and told the author to "use a selector
function from selectors.py" — a Django/DRF layering convention. A Go or Rust
project inherits that hook through the same live symlink. The safety rules
(bare `except: pass`, file size) stay unconditional; only the architectural
opinions are gated on the project having installed a stack that owns them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "block-bad-patterns.sh"

ORM_IN_VIEW = "def list_items(request):\n    return Item.objects.filter(active=True)\n"
SAVE_IN_VIEW = "def create(request):\n    obj.save()\n"
BARE_EXCEPT = "def f():\n    try:\n        g()\n    except Exception:\n        pass\n"


@pytest.fixture
def workspace() -> Path:
    """A scratch dir whose path contains no "test".

    pytest's own tmp_path is always under `.../test_<name>N/`, and the hook
    skips any FILE_PATH matching `*test*` — so every case here silently passed
    on the skip branch rather than on the behaviour under test.
    """
    root = Path(tempfile.mkdtemp(prefix="cosx-"))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _project(base: Path, templates: list[str] | None, name: str = "proj") -> Path:
    root = base / name
    (root / ".coding-os").mkdir(parents=True)
    if templates is not None:
        listed = "\n".join(f"  - {t}" for t in templates)
        (root / ".coding-os.yaml").write_text(
            textwrap.dedent(f"""\
                version: '1.0'
                agents:
                  - claude
                templates:
                {listed}
                """)
        )
    return root


def _run(root: Path, rel_path: str, content: str) -> int:
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(root / rel_path), "content": content},
    }
    bash = shutil.which("bash") or "/bin/bash"
    proc = subprocess.run(
        [bash, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(root),
            "COS_PROJECT_ROOT": str(root),
            "COS_STATE_DIR": str(root / ".coding-os"),
            "COS_AGENT_DIR": str(root / ".coding-os"),
            "COS_PANEL_DIR": str(root / ".coding-os"),
        },
        timeout=30,
    )
    return proc.returncode


@pytest.mark.parametrize("content", [ORM_IN_VIEW, SAVE_IN_VIEW])
def test_django_project_still_gets_the_layering_rules(workspace: Path, content: str) -> None:
    root = _project(workspace, ["django"])
    assert _run(root, "src/backend/apps/shop/views.py", content) == 2


@pytest.mark.parametrize("content", [ORM_IN_VIEW, SAVE_IN_VIEW])
def test_non_django_project_is_left_alone(workspace: Path, content: str) -> None:
    root = _project(workspace, ["go"])
    assert _run(root, "src/backend/views.py", content) == 0, (
        "a Go project was told to use a Django selectors.py"
    )


@pytest.mark.parametrize("content", [ORM_IN_VIEW, SAVE_IN_VIEW])
def test_project_without_config_is_left_alone(workspace: Path, content: str) -> None:
    root = _project(workspace, None)
    assert _run(root, "src/backend/views.py", content) == 0


def test_universal_safety_rules_stay_unconditional(workspace: Path) -> None:
    """The gating must not have widened into an escape hatch for real bugs."""
    for index, templates in enumerate((["go"], ["django"], None)):
        root = _project(workspace, templates, name=f"p{index}")
        assert _run(root, "src/backend/thing.py", BARE_EXCEPT) == 2, (
            f"bare except:pass slipped through for templates={templates}"
        )
