"""Polyglot quality benchmark — measured, not judged (TASK-313).

Ground-truth corpora per language × 3 scenarios (personas):
  S1 simple    — junior-dev file: flat functions, one class, imports.
  S2 nested    — library author: methods in classes, nesting, inheritance.
  S3 realworld — enterprise service file: mixed imports, same-file +
                 cross-file + dynamic calls, inheritance, and DECOY code
                 inside comments/strings that must NOT be extracted.

Measured axes (the enterprise scorecard):
  coverage  = symbol recall (every human-visible function/class extracted)
              + edge recall (expected imports/calls/inherits found)
  accuracy  = precision in the function/class buckets (no phantoms) and
              zero decoy leakage
  trust     = confidence calibration: every calls edge at conf ≥ 0.9 must
              resolve to a real same-file uid (never an external guess)
  speed     = median extract() ms per file
  resources = peak tracemalloc bytes per extract

Thresholds (asserted — a miss is a red test, not a footnote):
  symbol recall ≥ 0.90 · precision ≥ 0.95 · edge recall ≥ 0.80
  median ≤ 25 ms/file · peak ≤ 6 MB/file

Run `python -m pytest <this file> -q` for the gate, or
`python src/core/graph_os/tests/test_polyglot_quality.py` for the
per-language stats table used in the score report.
"""

from __future__ import annotations

import statistics
import time
import tracemalloc

import pytest

pytest.importorskip("tree_sitter")

from graph_os.extractors import (
    code_generic,
)
from graph_os.tests.polyglot_corpus_config import CONFIG_CORPUS
from graph_os.tests.polyglot_corpus_scripting import CORPUS as _SCRIPTING_CORPUS
from graph_os.tests.polyglot_corpus_systems import CORPUS as _SYSTEMS_CORPUS
from graph_os.tests.polyglot_scenario import Scenario

CORPUS: dict[str, tuple[object, list[Scenario]]] = {
    **_SYSTEMS_CORPUS,
    **_SCRIPTING_CORPUS,
}

_FUNC_KINDS = {"code:function", "code:method"}
_CLASS_KINDS = {"code:class", "code:interface", "code:trait", "code:struct", "code:enum"}
_DECOY_NAMES = {"decoy", "fake_fn", "FakeClass", "phantom"}


def _last_segment(label: str) -> str:
    for sep in ("::", "."):
        if sep in label:
            label = label.rsplit(sep, 1)[-1]
    return label


def _extracted_names(result, kinds: set[str]) -> set[str]:
    return {_last_segment(n.label) for n in result.nodes if n.kind in kinds and n.label}


# ---------------------------------------------------------------------------
# Config-format corpora (yaml / json / toml) — exact-label ground truth.
# These extractors claim config KEYS and manifest DEPENDENCIES, so the metric
# is exact set equality of emitted labels (recall AND precision in one check).
# Designed scope (pinned, not a gap): arbitrary non-manifest .json files yield
# no key nodes by design — only known manifests (package.json, .mcp.json,
# tsconfig.json) are mined, to keep the graph lean (P3).
# ---------------------------------------------------------------------------

# dependency = the manifest node itself; doc:external = the dep-target stubs
# (promoted ends of `imports` edges); tool = scripts; contract = tsconfig
# paths. Exact-set equality over these kinds pins recall AND precision.
_CONFIG_KINDS = {"doc:frontmatter_key", "dependency", "tool", "doc:external", "contract"}


def _config_labels(result) -> set[str]:
    return {n.label for n in result.nodes if n.kind in _CONFIG_KINDS and n.label}


_CONFIG_CASES = [(fmt, sc) for fmt, (_, scenarios) in CONFIG_CORPUS.items() for sc in scenarios]
_CONFIG_IDS = [f"{fmt}-{sc.name}" for fmt, sc in _CONFIG_CASES]


@pytest.mark.parametrize("fmt,sc", _CONFIG_CASES, ids=_CONFIG_IDS)
def test_config_label_recall_and_precision(fmt, sc):
    """Config formats: emitted key/dependency labels must EXACTLY equal the
    ground truth — full recall (nothing missed) AND full precision (nothing
    phantom) in one assertion."""
    mod = CONFIG_CORPUS[fmt][0]
    result = mod.extract(sc.file, sc.src)
    got = _config_labels(result)
    missing = sc.funcs - got
    phantom = got - sc.funcs
    assert not missing, f"{fmt}/{sc.name}: missing labels {missing}"
    assert not phantom, f"{fmt}/{sc.name}: phantom labels {phantom}"


@pytest.mark.parametrize("fmt", list(CONFIG_CORPUS), ids=list(CONFIG_CORPUS))
def test_config_speed_and_memory(fmt):
    mod, scenarios = CONFIG_CORPUS[fmt]
    times: list[float] = []
    peaks: list[int] = []
    for sc in scenarios:
        for _ in range(5):
            tracemalloc.start()
            t0 = time.perf_counter()
            mod.extract(sc.file, sc.src)
            times.append((time.perf_counter() - t0) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
    assert statistics.median(times) <= 25
    assert max(peaks) <= 6 * 1024 * 1024


def _run_case(mod, sc: Scenario):
    return mod.extract(sc.file, sc.src)


def _symbol_metrics(result, sc: Scenario) -> tuple[float, float, set[str]]:
    extracted = _extracted_names(result, _FUNC_KINDS) | _extracted_names(result, _CLASS_KINDS)
    expected = sc.funcs | sc.classes
    found = {e for e in expected if e in extracted}
    recall = len(found) / len(expected) if expected else 1.0
    phantoms = {
        n
        for n in extracted
        if n not in expected
        # constructors legitimately share the class name (java/c#)
        and n not in sc.classes
    }
    precision = (len(extracted) - len(phantoms)) / len(extracted) if extracted else 1.0
    return recall, precision, phantoms


def _edge_recall(result, sc: Scenario) -> float:
    if not sc.edges:
        return 1.0
    hits = 0
    for etype, src_frag, tgt_frag in sc.edges:
        if any(
            e.edge_type == etype and src_frag in e.source_uid and tgt_frag in e.target_uid
            for e in result.edges
        ):
            hits += 1
    return hits / len(sc.edges)


def compute_stats() -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for lang, (mod, scenarios) in CORPUS.items():
        recalls: list[float] = []
        precisions: list[float] = []
        edge_recalls: list[float] = []
        times_ms: list[float] = []
        peaks: list[int] = []
        for sc in scenarios:
            result = _run_case(mod, sc)
            r, p, _ = _symbol_metrics(result, sc)
            recalls.append(r)
            precisions.append(p)
            edge_recalls.append(_edge_recall(result, sc))
            for _ in range(5):
                tracemalloc.start()
                t0 = time.perf_counter()
                _run_case(mod, sc)
                times_ms.append((time.perf_counter() - t0) * 1000)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peaks.append(peak)
        stats[lang] = {
            "symbol_recall": min(recalls),
            "precision": min(precisions),
            "edge_recall": min(edge_recalls),
            "median_ms": statistics.median(times_ms),
            "peak_kb": max(peaks) / 1024,
        }
    for fmt, (mod, scenarios) in CONFIG_CORPUS.items():
        recalls = []
        precisions = []
        times_ms = []
        peaks = []
        for sc in scenarios:
            result = mod.extract(sc.file, sc.src)
            got = _config_labels(result)
            recalls.append(len(got & sc.funcs) / len(sc.funcs) if sc.funcs else 1.0)
            precisions.append(len(got & sc.funcs) / len(got) if got else 1.0)
            for _ in range(5):
                tracemalloc.start()
                t0 = time.perf_counter()
                mod.extract(sc.file, sc.src)
                times_ms.append((time.perf_counter() - t0) * 1000)
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                peaks.append(peak)
        stats[fmt] = {
            "symbol_recall": min(recalls),
            "precision": min(precisions),
            "edge_recall": 1.0,  # n/a for config formats (no call/inherit edges)
            "median_ms": statistics.median(times_ms),
            "peak_kb": max(peaks) / 1024,
        }
    return stats


# ---------------------------------------------------------------------------
# Threshold gates — these are the score, asserted
# ---------------------------------------------------------------------------

_ALL_CASES = [(lang, sc) for lang, (_, scenarios) in CORPUS.items() for sc in scenarios]
_IDS = [f"{lang}-{sc.name}" for lang, sc in _ALL_CASES]


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_symbol_recall_and_precision(lang, sc):
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    recall, precision, phantoms = _symbol_metrics(result, sc)
    assert recall >= 0.9, f"{lang}/{sc.name}: symbol recall {recall:.2f} < 0.9"
    assert precision >= 0.95, f"{lang}/{sc.name}: precision {precision:.2f} (phantoms={phantoms})"


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_no_decoy_leakage(lang, sc):
    """Code inside comments / string literals must never become a symbol."""
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    extracted = _extracted_names(result, _FUNC_KINDS | _CLASS_KINDS)
    leaked = extracted & _DECOY_NAMES
    assert not leaked, f"{lang}/{sc.name}: decoys extracted from comments/strings: {leaked}"


@pytest.mark.parametrize("lang,sc", _ALL_CASES, ids=_IDS)
def test_edge_recall(lang, sc):
    mod = CORPUS[lang][0]
    result = _run_case(mod, sc)
    er = _edge_recall(result, sc)
    assert er >= 0.8, f"{lang}/{sc.name}: edge recall {er:.2f} < 0.8"


@pytest.mark.parametrize("lang", list(CORPUS), ids=list(CORPUS))
def test_call_confidence_calibration(lang):
    """Trust: every calls edge at conf ≥ 0.9 must resolve to a real same-file
    uid — a high-confidence edge pointing at an external guess is calibration
    inflation (graph-os-authoring §3)."""
    mod, scenarios = CORPUS[lang]
    for sc in scenarios:
        result = _run_case(mod, sc)
        node_uids = {n.uid for n in result.nodes}
        for e in result.edges:
            if e.edge_type == "calls" and e.confidence >= 0.9:
                assert not e.target_uid.startswith("code:external"), (
                    f"{lang}/{sc.name}: conf {e.confidence} call -> {e.target_uid}"
                )
                assert e.target_uid in node_uids


@pytest.mark.parametrize("lang", list(CORPUS), ids=list(CORPUS))
def test_speed_and_memory(lang):
    mod, scenarios = CORPUS[lang]
    times: list[float] = []
    peaks: list[int] = []
    for sc in scenarios:
        for _ in range(5):
            tracemalloc.start()
            t0 = time.perf_counter()
            _run_case(mod, sc)
            times.append((time.perf_counter() - t0) * 1000)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
    median_ms = statistics.median(times)
    peak_mb = max(peaks) / (1024 * 1024)
    assert median_ms <= 25, f"{lang}: median {median_ms:.1f} ms > 25 ms"
    assert peak_mb <= 6, f"{lang}: peak {peak_mb:.1f} MB > 6 MB"


def test_kotlin_grammar_quirk_is_surfaced():
    """Known upstream limitation, pinned (minimal repro): tree-sitter-kotlin
    1.1.0 mis-parses a SINGLE-LINE class body with members when it follows any
    other declaration — `class A { fun x() {} }` + `class B { fun y() {} }`
    on consecutive lines collapses into an ERROR node (multiline bodies are
    fine). The extractor must fail OPEN: file node + a surfaced parse error
    (TASK-293 machinery), never a raise, and salvaged symbols still emitted."""
    pytest.importorskip("tree_sitter_kotlin")
    src = "class A { fun x() {} }\nclass B { fun y() {} }\n"
    result = code_generic.extract("quirk.kt", src)
    assert any(p.kind == "tree_sitter_error" for p in result.parse_errors), (
        "expected the single-line-class-body quirk to surface as a parse "
        "error; if this fails the upstream grammar got fixed — delete this "
        "pin and tighten the kotlin corpus"
    )
    # fail-open: file node still present, salvaged symbols still extracted
    assert any(n.kind == "code:file" for n in result.nodes)
    assert "x" in _extracted_names(result, _FUNC_KINDS)


if __name__ == "__main__":
    table = compute_stats()
    print(
        f"{'lang':10} {'sym_recall':>10} {'precision':>10} {'edge_recall':>11} "
        f"{'median_ms':>10} {'peak_kb':>8}"
    )
    for lang, row in table.items():
        print(
            f"{lang:10} {row['symbol_recall']:>10.2f} {row['precision']:>10.2f} "
            f"{row['edge_recall']:>11.2f} {row['median_ms']:>10.2f} {row['peak_kb']:>8.0f}"
        )
