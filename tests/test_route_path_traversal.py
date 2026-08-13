"""Traversal guards on the request-supplied identifiers that become path segments.

CodeQL reports py/path-injection on these sinks and does not model
_bounded_read.safe_segment as a barrier, so the barrier needs a test of its own —
otherwise the only thing standing behind ~23 dismissed alerts is an assertion in
a commit message. Spec: docs/engineering/ci-gates.md § Triaging a CodeQL alert.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (REPO_ROOT / "src", REPO_ROOT / "src" / "core"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from web.routes._bounded_read import safe_child, safe_segment  # noqa: E402

# Shapes that reach these routes as `agent`, `session_id`, `stack_id` or a
# skill name. The escapes are the ones that actually work on POSIX + macOS.
TRAVERSALS = [
    "..",
    "../..",
    "../../etc/passwd",
    "..%2f..",
    "a/../..",
    "/etc/passwd",
    "./..",
    "",
    ".",
    "-rf",
    "claude/../../..",
]

LEGITIMATE = [
    "claude",
    "codex",
    "ses-claude-1786-9931",
    "spring-boot",
    "go-fiber",
    "vue-nuxt",
    "clean-code",
    "python-meta-server",
]


@pytest.mark.parametrize("value", TRAVERSALS)
def test_safe_segment_rejects_traversal(value: str) -> None:
    assert safe_segment(value) is False


@pytest.mark.parametrize("value", LEGITIMATE)
def test_safe_segment_accepts_real_identifiers(value: str) -> None:
    # A guard that rejects `spring-boot` would be found by the scaffold suite,
    # not here — but a guard nobody can pass is the more common failure.
    assert safe_segment(value) is True


@pytest.mark.parametrize("value", TRAVERSALS)
def test_safe_child_refuses_to_leave_root(tmp_path: Path, value: str) -> None:
    assert safe_child(tmp_path, value) is None


def test_safe_child_returns_a_path_inside_root(tmp_path: Path) -> None:
    child = safe_child(tmp_path, "claude", "traces")
    assert child is not None
    assert child.resolve().is_relative_to(tmp_path.resolve())


def test_safe_child_blocks_a_symlink_pointing_out_of_root(tmp_path: Path) -> None:
    # The segment check alone cannot catch this one: `escape` is a perfectly
    # well-formed segment. Only the resolve-then-compare half rejects it.
    outside = tmp_path.parent / "outside-root"
    outside.mkdir(exist_ok=True)
    root = tmp_path / "root"
    root.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    assert safe_child(root, "escape") is None


@pytest.fixture
def planted_secret(tmp_path: Path) -> tuple[Path, str]:
    """A state root plus a real readable file one level ABOVE it.

    Asserting `== []` against a path that never existed passes with or without
    the guard — the traversal has to point at something real for the test to
    mean anything.
    """
    state = tmp_path / "state"
    (state / "claude" / "traces").mkdir(parents=True)
    secret_dir = tmp_path / "secret" / "traces"
    secret_dir.mkdir(parents=True)
    (secret_dir / "ses-1.jsonl").write_text('{"kind": "leaked"}\n', encoding="utf-8")
    (tmp_path / "secret" / "sessions").mkdir()
    (tmp_path / "secret" / "sessions" / "ses-1.json").write_text('{"leaked": true}', encoding="utf-8")
    return state, "../secret"


def test_roles_trace_reader_will_not_read_above_the_state_root(planted_secret) -> None:
    from web.routes.roles import _read_trace_events

    state, escape = planted_secret
    # Sanity: the traversal really does resolve onto the planted file, so a
    # green assertion below is the guard working, not the file being absent.
    assert (state / escape / "traces" / "ses-1.jsonl").exists()
    assert _read_trace_events(state, escape, "ses-1") == []


def test_cognition_trace_finder_will_not_read_above_the_state_root(planted_secret) -> None:
    from web.routes.cognition import _find_session_meta, _find_trace_file

    state, escape = planted_secret
    assert (state / escape / "sessions" / "ses-1.json").exists()
    assert _find_trace_file(state, "ses-1", escape) == (None, None)
    assert _find_session_meta(state, "ses-1", escape) == (None, None)


def test_skill_provenance_rejects_a_traversing_name() -> None:
    from cli._skill_project import _known_skill_provenance

    # `--skills` / the Hub's extra_skills field are NOT registry-validated
    # upstream, so this function is the boundary.
    assert _known_skill_provenance("../../../etc") is None
    assert _known_skill_provenance("..") is None
