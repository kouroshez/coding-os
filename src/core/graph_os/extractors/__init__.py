"""graph_os extractors.

Each module under this package turns a single source type (markdown
doc, task file, Python module, TS file, shell script, contracts ...)
into a stream of GraphNode + GraphEdge values that flows into the
shared GraphBackend. Extractors MUST be pure: no DB writes, no
sys.path tweaks, no network. The orchestrator owns the write path.
"""
