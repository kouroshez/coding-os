"""Phantom-reference contract guard (TASK-289, epic retrieval-routing-fix).

The "ask about graph -> agent goes to memory" bug had a deeper cause: the
agent-facing contract (AGENTS.md, rules, skills) documented a `cos_retrieve`
router that was never registered as an MCP tool. Every "when unsure, call
cos_retrieve" instruction pointed at a phantom, so the agent silently fell
back to memory.

This guard scans the live agent-facing contract surface for any concrete
`cos_*` token and asserts it names a REGISTERED MCP tool. The old cos_retrieve
would fail this test. Family wildcards (`cos_graph_*`) and family shorthands
(`cos_graph`) are allowed; a concrete dangling name is not.

Scope is the LIVE contract (specs + rules + skills) — NOT docs/tasks or
audits, which legitimately discuss removed/historical tools.

Run: uv run pytest tests/test_no_phantom_tool_refs.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Source surfaces where MCP tools (and the shell/python helpers that docs also
# legitimately reference) are defined.
_NAME_RE = re.compile(r'name="(cos_[a-z0-9_]+)"')  # @mcp.tool(name="cos_...")
_PYDEF_RE = re.compile(r"\bdef\s+(_?cos_[a-z0-9_]+)\s*\(")  # python defs
_SHDEF_RE = re.compile(r"^\s*(_?cos_[a-z0-9_]+)\s*\(\)", re.M)  # bash function defs
_SHASSIGN_RE = re.compile(r"\b(_?cos_[a-z0-9_]+)=", re.M)  # bash var assigns
# Word boundary on the left so we don't match INSIDE identifiers like
# `test_cos_env_panel_resolution` (which is a test name, not a `cos_*` ref).
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])cos_[a-z][a-z0-9_]*")

# Documented `cos_*` identifiers that are deliberately NOT registered MCP
# tools — auditing confirmed each is benign. A new dangling tool reference
# (the cos_retrieve class of bug) is NOT here, so it still fails the guard.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        "cos_csrf",  # a CSRF cookie name issued by the hub gate, not a tool
        "cos_doc_heading_search",  # roadmap entry (proposed future tool, doc-system-overhaul-roadmap.md)
        "cos_hook_error",  # proposed shared shell helper in the observability doc
        "cos_init_jobs_total",  # Prometheus funnel counter name (hub-architecture.md), not a tool
        "cos_root",  # example local variable in mcp-fast-path-entry.md prose
        "cos_say_json",  # real helper FILE (_helpers/cos_say_json.py) referenced by filename; not harvested as a tool symbol
    }
)

# Live agent-facing contract surface to audit. Deliberately excludes
# docs/tasks/** and docs/_meta/** (historical prose may name removed tools).
_CONTRACT_ROOTS: tuple[tuple[str, str], ...] = (
    ("AGENTS.md", ""),
    ("src/core/rules", "**/*.md"),
    ("src/core/skills", "**/*.md"),
    ("docs/engineering", "**/*.md"),
    ("docs/governance", "**/*.md"),
)


def _known_tools() -> set[str]:
    known: set[str] = set()
    for py in (*REPO.glob("src/core/**/*.py"), *REPO.glob("src/cli/**/*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        known.update(_NAME_RE.findall(text))
        known.update(_PYDEF_RE.findall(text))
    for sh in REPO.glob("src/core/**/*.sh"):
        text = sh.read_text(encoding="utf-8", errors="ignore")
        known.update(_SHDEF_RE.findall(text))
        known.update(_SHASSIGN_RE.findall(text))
    return known


def _contract_files() -> list[Path]:
    files: dict[Path, None] = {}  # dedup by resolved path (CLAUDE.md -> AGENTS.md symlink)
    for root, pattern in _CONTRACT_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        candidates = base.glob(pattern) if pattern else [base]
        for f in candidates:
            if f.is_file():
                files[f.resolve()] = None
    return sorted(files)


KNOWN_TOOLS = _known_tools()
CONTRACT_FILES = _contract_files()


def _is_phantom(token: str) -> bool:
    """A concrete cos_* token is phantom unless it is defined, allowlisted, or a family ref."""
    if token in KNOWN_TOOLS or ("_" + token) in KNOWN_TOOLS:  # tool/helper (tolerate leading _)
        return False
    if token in _ALLOWLIST:  # documented non-tool identifier
        return False
    if token.endswith("_"):  # wildcard like cos_graph_* -> token "cos_graph_"
        return False
    # family shorthand like cos_graph is fine when a real cos_graph_* tool exists
    return not any(tool.startswith(token + "_") for tool in KNOWN_TOOLS)


def _phantoms_in(path: Path) -> list[str]:
    findings: list[str] = []
    for lineno, line in enumerate(
        path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
    ):
        for token in _TOKEN_RE.findall(line):
            if _is_phantom(token):
                rel = path.relative_to(REPO)
                findings.append(f"{rel}:{lineno}  {token}")
    return findings


def test_tool_source_scan_found_tools() -> None:
    """Sanity: the known-tool harvest must work, else every ref looks phantom."""
    assert len(KNOWN_TOOLS) >= 50, f"harvested only {len(KNOWN_TOOLS)} tools — extraction broken"
    assert "cos_search" in KNOWN_TOOLS and "cos_graph_query" in KNOWN_TOOLS
    assert "cos_retrieve" not in KNOWN_TOOLS  # the phantom must NOT be a real tool


@pytest.mark.parametrize(
    "contract_file",
    CONTRACT_FILES,
    ids=[str(p.relative_to(REPO)) for p in CONTRACT_FILES],
)
def test_no_phantom_tool_refs(contract_file: Path) -> None:
    phantoms = _phantoms_in(contract_file)
    assert not phantoms, (
        "phantom cos_* reference(s) — name a tool that is not registered:\n"
        + "\n".join("  " + p for p in phantoms)
    )


def test_contract_surface_summary() -> None:
    """Structured summary: files scanned + total phantoms (the regression number)."""
    total = sum(len(_phantoms_in(f)) for f in CONTRACT_FILES)
    print(
        f"\n[phantom-ref] scanned {len(CONTRACT_FILES)} contract files against "
        f"{len(KNOWN_TOOLS)} registered tools; {total} phantom reference(s)."
    )
    assert total == 0
