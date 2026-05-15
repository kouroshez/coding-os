"""Contract test for `templates/<stack>/skills/<skill>/references/anatomy.md`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "src" / "templates"

REQUIRED_H2_ORDER = [
    "## 1. Boundary",
    "## 2. Layout map",
    "## 3. Entity recipes",
    "## 4. Conventions",
]

REQUIRED_H3_UNDER_CONVENTIONS = [
    "#### Naming",
    "#### Test colocation",
    "#### Dependency rules",
]

# Cap matches anatomy-contract.md § Token budget.
TOKEN_CAP = 2000

FRONTMATTER_RE = re.compile(
    r"^<!--\s*domain:[A-Z0-9_]+\s*\|\s*layer:reference\s*\|\s*ssot:(true|ref)\s*\|\s*updated:\d{4}-\d{2}-\d{2}\s*-->",
)

OPENING_BLOCK_LINES = ("> P:", "> R:", "> S:", "> N:")


def _stack_anatomy_files() -> list[Path]:
    """Return every anatomy.md the repo ships under templates/<stack>/."""
    return sorted(TEMPLATES.glob("*/skills/*/references/anatomy.md"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _approx_tokens(text: str) -> int:
    """Heuristic: 1 token ≈ 4 chars (Claude tokenizer ballpark)."""
    return len(text) // 4


def test_at_least_one_stack_ships_anatomy() -> None:
    files = _stack_anatomy_files()
    assert files, "No stack anatomy files found — POC has not landed yet."


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_frontmatter(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    first_line = body.splitlines()[0] if body else ""
    assert FRONTMATTER_RE.match(first_line), (
        f"{anatomy_path.relative_to(REPO_ROOT)}: frontmatter does not match "
        f"`<!-- domain:STACK | layer:reference | ssot:true|ref | updated:YYYY-MM-DD -->`. "
        f"Got: {first_line!r}"
    )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_short_form_opening_block(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    for prefix in OPENING_BLOCK_LINES:
        assert any(line.startswith(prefix) for line in body.splitlines()), (
            f"{anatomy_path.relative_to(REPO_ROOT)}: missing opening-block "
            f"line starting with {prefix!r} (short form mandatory per "
            f"anatomy-contract.md)."
        )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_required_h2_order(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    found = [ln for ln in body.splitlines() if ln.startswith("## ")]
    contract_present = [ln for ln in found if ln in REQUIRED_H2_ORDER]
    assert contract_present == REQUIRED_H2_ORDER, (
        f"{anatomy_path.relative_to(REPO_ROOT)}: required H2 sections must "
        f"appear in this order: {REQUIRED_H2_ORDER!r}. Found: {contract_present!r}."
    )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_conventions_subsections(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    h3s = [ln for ln in body.splitlines() if ln.startswith("#### ")]
    h3_present = [ln for ln in h3s if ln in REQUIRED_H3_UNDER_CONVENTIONS]
    assert h3_present == REQUIRED_H3_UNDER_CONVENTIONS, (
        f"{anatomy_path.relative_to(REPO_ROOT)}: § 4 Conventions MUST contain "
        f"these H3 subsections in order: {REQUIRED_H3_UNDER_CONVENTIONS!r}. "
        f"Found: {h3_present!r}."
    )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_boundary_section_links_yaml(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    # § 1 Boundary must contain a link to scaffold-boundary.yaml (SSOT) — no
    # duplicated field tables (over-fix per audit).
    boundary_idx = body.find("## 1. Boundary")
    next_h2_idx = body.find("\n## 2. ", boundary_idx)
    section = body[boundary_idx:next_h2_idx if next_h2_idx > 0 else len(body)]
    assert "scaffold-boundary.yaml" in section, (
        f"{anatomy_path.relative_to(REPO_ROOT)}: § 1 Boundary MUST link to "
        f"the stack's scaffold-boundary.yaml (SSOT, no duplicated tables)."
    )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_token_budget(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    tokens = _approx_tokens(body)
    assert tokens <= TOKEN_CAP, (
        f"{anatomy_path.relative_to(REPO_ROOT)}: ~{tokens} tokens exceeds "
        f"hard cap {TOKEN_CAP}. Split entity recipes into anatomy-*.md siblings."
    )


@pytest.mark.parametrize("anatomy_path", _stack_anatomy_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_anatomy_test_recipe_present(anatomy_path: Path) -> None:
    body = _read(anatomy_path)
    assert "### Add a new test" in body, (
        f"{anatomy_path.relative_to(REPO_ROOT)}: § 3 Entity recipes MUST "
        f"include `### Add a new test` (universal recipe per contract)."
    )


# ---------------------------------------------------------------------------
# scaffold-boundary.yaml contract
# ---------------------------------------------------------------------------

REQUIRED_BOUNDARY_KEYS = {
    "version",
    "stack",
    "roots",
    "file_patterns",
    "imports_from",
    "forbids_writing_in",
}


def _stack_boundary_files() -> list[Path]:
    return sorted(TEMPLATES.glob("*/scaffold-boundary.yaml"))


def test_at_least_one_stack_ships_boundary() -> None:
    files = _stack_boundary_files()
    assert files, "No stack scaffold-boundary.yaml files found — POC has not landed yet."


@pytest.mark.parametrize("boundary_path", _stack_boundary_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_boundary_required_keys(boundary_path: Path) -> None:
    data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{boundary_path.name}: not a YAML mapping."
    missing = REQUIRED_BOUNDARY_KEYS - set(data.keys())
    assert not missing, (
        f"{boundary_path.relative_to(REPO_ROOT)}: missing required keys: {sorted(missing)}"
    )


@pytest.mark.parametrize("boundary_path", _stack_boundary_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_boundary_stack_field_matches_dir(boundary_path: Path) -> None:
    data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
    expected_stack = boundary_path.parent.name
    assert data.get("stack") == expected_stack, (
        f"{boundary_path.relative_to(REPO_ROOT)}: stack='{data.get('stack')}' "
        f"does not match enclosing dir '{expected_stack}'."
    )


@pytest.mark.parametrize("boundary_path", _stack_boundary_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_boundary_roots_have_trailing_slash(boundary_path: Path) -> None:
    data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
    for root in data.get("roots") or []:
        assert root.endswith("/"), (
            f"{boundary_path.relative_to(REPO_ROOT)}: root '{root}' must end with '/'."
        )


@pytest.mark.parametrize("boundary_path", _stack_boundary_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_boundary_version_is_one(boundary_path: Path) -> None:
    data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
    assert data.get("version") == 1, (
        f"{boundary_path.relative_to(REPO_ROOT)}: version must be 1 (got {data.get('version')!r})."
    )


def test_root_collisions_only_within_same_category() -> None:
    """Two stacks may share a root iff they are mutually exclusive (same
    `category` in stack.yaml). E.g. django + fastapi both own `backend/`,
    but a single project picks ONE; aggregator at `cos init` enforces the
    real per-project invariant."""
    by_root: dict[str, list[tuple[str, str]]] = {}
    for boundary_path in _stack_boundary_files():
        data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
        stack_id = data.get("stack")
        stack_yaml_path = boundary_path.parent / "stack.yaml"
        category = "unknown"
        if stack_yaml_path.exists():
            stack_meta = yaml.safe_load(stack_yaml_path.read_text(encoding="utf-8"))
            category = stack_meta.get("category", "unknown")
        for root in data.get("roots") or []:
            by_root.setdefault(root, []).append((stack_id, category))

    issues: list[str] = []
    for root, claimants in by_root.items():
        categories = {c for _, c in claimants}
        if len(claimants) > 1 and len(categories) > 1:
            issues.append(
                f"Root '{root}' claimed by stacks across categories {sorted(categories)}: "
                f"{[s for s, _ in claimants]} — only same-category stacks may collide."
            )
    assert not issues, " ; ".join(issues)


def test_forbids_writing_in_references_real_subtrees() -> None:
    # Collect all roots installed in the meta-repo's stack set.
    all_roots: set[str] = set()
    for boundary_path in _stack_boundary_files():
        data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
        for root in data.get("roots") or []:
            all_roots.add(root.rstrip("/"))

    issues: list[str] = []
    for boundary_path in _stack_boundary_files():
        data = yaml.safe_load(boundary_path.read_text(encoding="utf-8"))
        for forbidden in data.get("forbids_writing_in") or []:
            stripped = forbidden.rstrip("/")
            if stripped not in all_roots:
                issues.append(
                    f"{boundary_path.relative_to(REPO_ROOT)} forbids writes "
                    f"in '{forbidden}' but no installed stack owns that root."
                )
    # Soft assertion: a forbidden subtree may legitimately reference a future
    # stack. Surface as a single combined message; do not block.
    if issues:
        pytest.skip("forbids_writing_in references unowned subtrees: " + " ; ".join(issues))


# ---------------------------------------------------------------------------
# Anatomy ↔ boundary cross-check
# ---------------------------------------------------------------------------


def test_every_stack_with_anatomy_ships_boundary() -> None:
    anatomies = {a.parents[3].name for a in _stack_anatomy_files()}
    boundaries = {b.parent.name for b in _stack_boundary_files()}
    missing = anatomies - boundaries
    assert not missing, (
        f"Stacks ship anatomy.md but no scaffold-boundary.yaml: {sorted(missing)}"
    )
