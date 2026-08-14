"""File-size ratchet: no tracked Python file may grow past its recorded size.

Two shrink-only gates, because a single global cap only ever watches the
one largest file — every other file could triple silently, which is exactly
how server.py reached 3,159 lines one accepted commit at a time:

* `SOFT_LIMIT` — a file absent from `BASELINE` must stay under it, so no
  NEW god-file can form.
* `BASELINE` — the files already over `SOFT_LIMIT` when this landed. Each
  may only shrink; splitting one means lowering its entry, and deleting the
  entry once the file drops under `SOFT_LIMIT`.

Raising a number (or adding a `BASELINE` key) is a review-rejected change by
policy: docs/engineering/ci-gates.md § File-size ratchet. Failures print the
exact replacement line so tightening is mechanical.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SOFT_LIMIT = 500

BASELINE: dict[str, int] = {
    # Append-only schema ledger — recorded exception, see ci-gates.md.
    "src/core/thinking_os/_db_migrations.py": 2316,
    "src/cli/pr_commands.py": 2024,
    "src/core/thinking_os/embeddings.py": 943,
}

EXCLUDED_PREFIXES = (
    "src/templates/",  # consumer-shipped scaffold; downstream owns style
    "tests/golden/",  # generated snapshots
    "archive/",
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_line_counts() -> dict[str, int]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    counts: dict[str, int] = {}
    for rel in out.stdout.splitlines():
        if not rel or rel.startswith(EXCLUDED_PREFIXES):
            continue
        try:
            counts[rel] = sum(1 for _ in (REPO_ROOT / rel).open("rb"))
        except OSError:
            continue  # deleted-but-still-tracked mid-rebase; git owns it
    return counts


def test_no_python_file_exceeds_its_size_ratchet() -> None:
    grown: list[str] = []
    new_offenders: list[str] = []
    for rel, count in sorted(_tracked_line_counts().items()):
        recorded = BASELINE.get(rel)
        if recorded is None:
            if count > SOFT_LIMIT:
                new_offenders.append(f"  {rel}: {count} lines (> {SOFT_LIMIT})")
        elif count > recorded:
            grown.append(f'  "{rel}": {recorded} -> {count} (+{count - recorded})')

    message = ""
    if grown:
        message += (
            "These files grew past their recorded ratchet. Move the added code "
            "into a sibling module instead of raising the number:\n" + "\n".join(grown) + "\n"
        )
    if new_offenders:
        message += (
            f"These files crossed {SOFT_LIMIT} lines. Split them — do NOT add a "
            "BASELINE entry, which is reserved for debt that predates the gate:\n"
            + "\n".join(new_offenders)
            + "\n"
        )
    assert not message, message


def test_baseline_has_no_stale_entries() -> None:
    counts = _tracked_line_counts()
    stale: list[str] = []
    for rel, recorded in sorted(BASELINE.items()):
        count = counts.get(rel)
        if count is None:
            stale.append(f'  "{rel}": {recorded}  # file no longer tracked')
        elif count <= SOFT_LIMIT:
            stale.append(f'  "{rel}": {recorded}  # now {count} lines, under the limit')
    assert not stale, (
        "Delete these BASELINE entries — the ratchet only tightens when paid-off "
        "debt leaves the list:\n" + "\n".join(stale)
    )


def test_hook_registry_quotes_the_real_ceiling() -> None:
    """The registry description is what an agent reads; it must not invent a number.

    It advertised an "800-line ceiling" while the hook enforced 500 and this
    file's SOFT_LIMIT was 500 — so the one place designed to explain the rule
    was the one place stating it wrongly.
    """
    import re

    registry = (
        Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "registry.yaml"
    ).read_text()
    hook = (
        Path(__file__).resolve().parent.parent / "src" / "core" / "hooks" / "block-bad-patterns.sh"
    ).read_text()

    enforced = re.search(r'MAX_FILE_LINES="\$\{COS_MAX_FILE_LINES:-(\d+)\}"', hook)
    assert enforced, "could not read MAX_FILE_LINES from block-bad-patterns.sh"
    assert int(enforced.group(1)) == SOFT_LIMIT, (
        f"hook enforces {enforced.group(1)} but this suite gates on {SOFT_LIMIT}"
    )

    quoted = re.findall(r"(\d+)-line (?:ceiling|backstop)", registry)
    assert quoted, "registry no longer describes a line ceiling — update this test with it"
    wrong = [n for n in quoted if int(n) != SOFT_LIMIT]
    assert not wrong, f"registry.yaml advertises {wrong} but the hook enforces {SOFT_LIMIT}"


# --- Rule 12: no provenance in comments -------------------------------------

_TASK_REF = re.compile(r"TASK-\d+")
_COMMENT = re.compile(r"^(\s*)(#|//|\*)")

# The first two document the ID FORMAT they parse or fuzz, so the ids are the
# subject of the comment rather than provenance about who wrote the line; the
# third is generated from the OpenAPI snapshot and is not hand-edited.
_PROVENANCE_EXEMPT = {
    "src/core/thinking_os/task_parser.py",
    "src/core/web/ui/src/features/cos-board/renderTaskMarkdown.fuzz.test.ts",
    "src/core/web/ui/src/lib/api-types.ts",
}


def test_no_task_ids_in_source_comments() -> None:
    """Rule 12: `git blame` already records who and what; a comment states why.

    The repo carried 346 of these while enforcing the rule on consumers — and
    because the runtime is told to match surrounding comment density, that
    legacy taught every agent the opposite of the rule.
    """
    root = Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    for rel_root in ("src/core", "src/cli", "src/adapters"):
        for path in (root / rel_root).rglob("*"):
            if path.suffix not in {".py", ".sh", ".ts", ".tsx"} or not path.is_file():
                continue
            rel = str(path.relative_to(root))
            if rel in _PROVENANCE_EXEMPT or "/tests/" in rel:
                continue
            for num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _COMMENT.match(line) and _TASK_REF.search(line):
                    offenders.append(f"{rel}:{num}: {line.strip()[:80]}")
    assert not offenders, (
        f"Rule 12 — {len(offenders)} comment(s) carry a task id:\n  " + "\n  ".join(offenders[:20])
    )
