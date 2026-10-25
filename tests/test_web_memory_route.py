"""GET /api/memory — the Hub's read-only view of `.agents/memory/`."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (_REPO_ROOT, _REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from core.web.routes.memory import memory_payload
from core.web.server import create_app


def _memory(directory: Path, slug: str, kind: str, body: str, verified: str = "") -> None:
    extra = f"  verified: {verified}\n" if verified else ""
    (directory / f"{slug}.md").write_text(
        f"---\nname: {slug}\ndescription: about {slug}\nmetadata:\n  type: {kind}\n{extra}---\n\n{body}\n",
        encoding="utf-8",
    )


def _project(tmp_path: Path) -> Path:
    directory = tmp_path / ".agents" / "memory"
    directory.mkdir(parents=True)
    (directory / "MEMORY.md").write_text(
        "# Memory Index\n\n"
        "- [Keep tests light](keep-tests-light.md) — one heavy process at a time\n"
        "- [Browser work](index-browser.md) — open before driving a browser\n",
        encoding="utf-8",
    )
    (directory / "index-browser.md").write_text(
        "# Browser work\n\n- [Use the extension](use-the-extension.md) — attach, never launch\n",
        encoding="utf-8",
    )
    _memory(
        directory, "keep-tests-light", "feedback", "Why: it crashed.\nSee [[use-the-extension]]."
    )
    _memory(directory, "use-the-extension", "reference", "Attach to Brave.", verified="2026-10-01")
    return tmp_path


def test_payload_groups_entries_by_index(tmp_path):
    payload = memory_payload(_project(tmp_path))

    assert payload["present"] is True
    root, sub = payload["indexes"]
    assert [e["slug"] for e in root["entries"]] == ["keep-tests-light", "index-browser"]
    assert root["entries"][0] == {
        "line": 3,
        "slug": "keep-tests-light",
        "title": "Keep tests light",
        "rule": "one heavy process at a time",
    }
    assert sub["name"] == "index-browser"
    assert sub["title"] == "Browser work"
    assert sub["pointer"] == {"title": "Browser work", "rule": "open before driving a browser"}
    assert [e["slug"] for e in sub["entries"]] == ["use-the-extension"]


def test_payload_reads_frontmatter_and_strips_it_from_the_body(tmp_path):
    memories = {m["slug"]: m for m in memory_payload(_project(tmp_path))["memories"]}

    assert set(memories) == {"keep-tests-light", "use-the-extension"}
    light = memories["keep-tests-light"]
    assert (light["type"], light["description"], light["verified"]) == (
        "feedback",
        "about keep-tests-light",
        None,
    )
    assert light["links"] == ["use-the-extension"]
    assert light["body"].startswith("Why: it crashed.")
    assert memories["use-the-extension"]["verified"] == "2026-10-01"


def test_payload_carries_budget_and_lint(tmp_path):
    payload = memory_payload(_project(tmp_path))

    assert payload["budget"] == {
        "lines": 4,
        "bytes": payload["budget"]["bytes"],
        "max_lines": 200,
        "max_bytes": 25_000,
    }
    assert payload["lint"]["errors"] == []
    assert "2 memories, 1 sub-indexes" in payload["lint"]["summary"]


def test_lint_errors_reach_the_payload(tmp_path):
    root = _project(tmp_path)
    _memory(root / ".agents" / "memory", "orphan-note", "user", "Indexed nowhere.")

    errors = memory_payload(root)["lint"]["errors"]

    assert any("orphan-note" in error for error in errors)


def test_missing_memory_dir_is_not_an_error(tmp_path):
    assert memory_payload(tmp_path) == {"present": False, "dir": ".agents/memory"}


def test_endpoint_is_served():
    response = TestClient(create_app()).get("/api/memory")

    assert response.status_code == 200
    assert "present" in response.json()
