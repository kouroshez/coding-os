"""graph_os — score-and-rank entry-point candidates (TASK-081)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .backend import GraphBackend
from .types import GraphNode

logger = logging.getLogger("graph_os.entry_points")


_KINDS: tuple[str, ...] = ("main", "cli", "http", "cron", "test")

_CANDIDATE_NODE_KINDS: frozenset[str] = frozenset(
    {
        "function",
        "code:function",
        "method",
        "code:method",
        "route",
        "cos:route",
        "mcp_tool",
        "cos:mcp_tool",
    }
)

_SCAN_LIMIT: int = 10_000


@dataclass(frozen=True)
class EntryPoint:
    """One scored entry-point candidate."""

    uid: str
    kind: str
    score: float
    label: str
    file_path: str | None
    start_line: int | None
    components: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "kind": self.kind,
            "score": round(self.score, 4),
            "label": self.label,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "components": list(self.components),
        }


def discover(
    backend: GraphBackend,
    *,
    min_score: float = 0.05,
    kind_filter: str | None = None,
) -> list[EntryPoint]:
    """Discover and score entry-point candidates."""
    if kind_filter is not None and kind_filter not in _KINDS:
        raise ValueError(f"kind_filter must be one of {_KINDS} (got {kind_filter!r})")

    candidates = _collect_candidates(backend)
    out: list[EntryPoint] = []
    for node in candidates:
        for ep in _score_node(node):
            if kind_filter is not None and ep.kind != kind_filter:
                continue
            # Test functions are not real entry points — they otherwise
            # dominate the default ranking (round-5 audit: ~76% of results,
            # scored 0.85 ABOVE the real CLI root at 0.6). Surface them only
            # when the caller explicitly asks for kind="test".
            if ep.kind == "test" and kind_filter != "test":
                continue
            if ep.score < min_score:
                continue
            out.append(ep)

    out.sort(key=lambda e: (-e.score, e.uid))
    return out


def _collect_candidates(backend: GraphBackend) -> list[GraphNode]:
    seen: dict[str, GraphNode] = {}
    for kind in _CANDIDATE_NODE_KINDS:
        try:
            for n in backend.sample_nodes(kind=kind, limit=_SCAN_LIMIT):
                seen.setdefault(n.uid, n)
        except Exception as exc:
            logger.debug("sample_nodes(%s) suppressed: %s", kind, exc)
            continue
    return list(seen.values())


def _score_node(node: GraphNode) -> Iterable[EntryPoint]:
    label = (node.label or "").strip()
    fp = node.file_path or ""
    lower_label = label.lower()
    lower_path = fp.lower()
    kind_str = node.kind or ""

    for ep_kind, score, components in _kind_signals(
        node,
        label=label,
        lower_label=lower_label,
        file_path=fp,
        lower_path=lower_path,
        node_kind=kind_str,
    ):
        if score <= 0.0:
            continue
        yield EntryPoint(
            uid=node.uid,
            kind=ep_kind,
            score=min(score, 1.0),
            label=label or node.uid.split("::")[-1] or node.uid,
            file_path=node.file_path,
            start_line=node.start_line,
            components=tuple(components),
        )


def _kind_signals(
    node: GraphNode,
    *,
    label: str,
    lower_label: str,
    file_path: str,
    lower_path: str,
    node_kind: str,
) -> Iterable[tuple[str, float, list[str]]]:
    sig = (node.signature or "").lower()

    main_score = 0.0
    main_comp: list[str] = []
    if lower_label == "main":
        main_score += 0.45
        main_comp.append("label_exact")
    if lower_label in {"__main__", "run", "start"}:
        main_score += 0.30
        main_comp.append("label_alias")
    if file_path.endswith("__main__.py") or file_path.endswith("/main.py"):
        main_score += 0.20
        main_comp.append("path_main")
    if main_score > 0:
        yield "main", main_score, main_comp

    cli_score = 0.0
    cli_comp: list[str] = []
    if "/cli/" in lower_path or lower_path.startswith("cli/"):
        cli_score += 0.20
        cli_comp.append("path_cli")
    if any(tok in lower_label for tok in ("command", "cli_", "_cli", "cmd_")):
        cli_score += 0.30
        cli_comp.append("label_command")
    if lower_label in {"app", "cli", "main_cli"}:
        cli_score += 0.45
        cli_comp.append("label_exact_cli")
    if "click" in sig or "argparse" in sig:
        cli_score += 0.10
        cli_comp.append("sig_argparse_click")
    if cli_score > 0:
        yield "cli", cli_score, cli_comp

    http_score = 0.0
    http_comp: list[str] = []
    if node_kind in {"route", "cos:route"}:
        http_score += 0.55
        http_comp.append("kind_route")
    if node_kind in {"mcp_tool", "cos:mcp_tool"}:
        http_score += 0.45
        http_comp.append("kind_mcp_tool")
    if any(verb in lower_label for verb in ("get_", "post_", "put_", "delete_", "patch_")):
        http_score += 0.20
        http_comp.append("label_verb")
    if "/routes/" in lower_path or "/api/" in lower_path or "/handlers/" in lower_path:
        http_score += 0.10
        http_comp.append("path_routes")
    if http_score > 0:
        yield "http", http_score, http_comp

    cron_score = 0.0
    cron_comp: list[str] = []
    if any(tok in lower_label for tok in ("cron", "schedule", "periodic", "tick")):
        cron_score += 0.45
        cron_comp.append("label_cron")
    if "/cron/" in lower_path or "/jobs/" in lower_path or "/scheduler" in lower_path:
        cron_score += 0.30
        cron_comp.append("path_cron")
    if "celery" in sig or "@scheduled" in sig:
        cron_score += 0.20
        cron_comp.append("sig_scheduler")
    if cron_score > 0:
        yield "cron", cron_score, cron_comp

    test_score = 0.0
    test_comp: list[str] = []
    if lower_path.startswith("tests/") or "/tests/" in lower_path:
        test_score += 0.45
        test_comp.append("path_tests")
    if lower_label.startswith("test_"):
        test_score += 0.30
        test_comp.append("label_test_prefix")
    if "test_" in (node.uid or "").lower():
        test_score += 0.10
        test_comp.append("uid_test")
    if test_score > 0:
        yield "test", test_score, test_comp


def best_start_for_query(backend: GraphBackend, query: str) -> EntryPoint | None:
    """Return the highest-scoring entry point whose label/uid contains ``query``."""
    lower = query.lower()
    candidates = discover(backend, min_score=0.05)
    matches = [
        ep for ep in candidates if lower in (ep.label or "").lower() or lower in ep.uid.lower()
    ]
    return matches[0] if matches else None


__all__ = ["EntryPoint", "best_start_for_query", "discover"]
