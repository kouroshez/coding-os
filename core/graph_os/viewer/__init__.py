# DEPRECATED for human use (S5, 2026-04-21): superseded by core/web/ui/ React SPA. Kept for `cos graph-viz` CLI compat through S6.
"""graph-os HTML viewer (I.10).

Builds a self-contained HTML page backed by Sigma.js + Graphology for
WebGL rendering. The exporter lives in `exporter.py`; the HTML
template in `template.py`. A pure-Python accessibility list-view is
rendered server-side so screen readers have a meaningful fallback.
"""

from .exporter import ViewerExporter, build_view

__all__ = ["ViewerExporter", "build_view"]
