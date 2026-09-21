---
name: splitting-a-facade-needs-a-runtime-surface-diff
description: "After splitting a module, diff dir() against the pre-split version at runtime — an AST scan cannot see names imported inside try/except."
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 5ac9fe2e-f9a3-4490-bb81-1ab2bb139298
  modified: 2026-09-21T02:36:31.367Z
---

When a module is split into private siblings with the original kept as a facade, prove the public surface survived by **importing both versions and diffing `dir()`**, not by parsing the source:

```python
old = {n for n in dir(module_from_git_show_HEAD) if not n.startswith("__")}
new = {n for n in dir(module_now) if not n.startswith("__")}
assert not (old - new)
```

**Why:** `ast.parse(src).body` only sees *top-level* statements. Re-exports written as `try: from ._x import a, b / except ImportError: ...` are nested inside the `Try`, so a source scan reports them missing and a hand-written re-export list reports them present — both lie. The runtime diff on `embeddings.py` found six names (`MODEL_DIMS`, `_MODEL_OVERRIDES`, `_PERSISTED_FLOORS`, …) that the facade had silently stopped exposing; the AST scan had flagged 35 names, almost all false.

**How to apply:** after any facade split, run the runtime diff before running the suite — a missing constant surfaces as a `conftest` `AttributeError` across hundreds of unrelated tests, which reads like a much bigger breakage than it is. Also check *how* the package is imported: `thinking_os` is loaded both flat (`import embeddings`, package dir on `sys.path`) and as `thinking_os.embeddings`, so sibling imports need a `try:` relative / `except ImportError:` flat pair, and mypy only honors `# type: ignore` when it is the **first** comment on the line — `# noqa: F401  # type: ignore[...]` silences nothing. Related: [[verification-matrix-must-match-ci]], [[fix-the-twin-of-every-guard-you-fix]].
