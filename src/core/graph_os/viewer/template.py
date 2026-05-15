"""graph_os viewer template (I.10) — Sigma.js + Graphology + CSP nonce.

DEPENDS:  stdlib only.
"""

from __future__ import annotations

import html
import json
from typing import Iterable

from ..types import GraphEdge, GraphNode

_CDN_DEPS = [
    (
        "https://cdn.jsdelivr.net/npm/graphology@0.25.4/dist/graphology.umd.min.js",
        "graphology",
    ),
    (
        "https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/"
        "umd/graphology-layout-forceatlas2.min.js",
        "forceatlas2",
    ),
    (
        "https://cdn.jsdelivr.net/npm/sigma@3.0.0/dist/sigma.min.js",
        "sigma",
    ),
]

_STYLE = """
  html, body { margin: 0; height: 100%; font: 14px/1.4 system-ui, sans-serif; background: #0e1116; color: #e6e7eb; }
  main { display: grid; grid-template-columns: 1fr 320px; grid-template-rows: 48px 1fr; height: 100vh; }
  header { grid-column: 1 / -1; display: flex; align-items: center; gap: 12px; padding: 0 16px; background: #1b1f27; border-bottom: 1px solid #2a2f39; }
  #canvas { position: relative; background: #11151c; }
  aside { padding: 16px; background: #151a22; border-left: 1px solid #2a2f39; overflow: auto; }
  .badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #2a2f39; color: #9ea4ae; }
  ul.a11y { list-style: none; padding-left: 0; margin: 0; font-size: 12px; }
  ul.a11y li { padding: 4px 0; border-bottom: 1px solid #1f242c; }
  .edge-type { color: #7fd4a0; }
  .node-kind { color: #c68fff; }
  details > summary { cursor: pointer; padding: 4px 0; }
"""


def render(
    nodes: Iterable[GraphNode],
    edges: Iterable[GraphEdge],
    *,
    title: str,
    nonce: str,
    bundled: bool = False,
) -> str:
    """Return the final HTML document."""
    node_list = list(nodes)
    edge_list = list(edges)
    payload = {
        "nodes": [_node_to_public(n) for n in node_list],
        "edges": [_edge_to_public(e) for e in edge_list],
    }
    payload_json = json.dumps(payload, separators=(",", ":"), default=str)

    cdn_host = "'self'" if bundled else "https://cdn.jsdelivr.net"
    csp = (
        "default-src 'none'; "
        f"script-src 'nonce-{nonce}' {cdn_host}; "
        f"style-src 'nonce-{nonce}'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "base-uri 'none'; "
        "frame-ancestors 'none';"
    )
    scripts = "\n".join(
        f'  <script nonce="{nonce}" src="{url}" crossorigin="anonymous"></script>'
        for url, _ in _CDN_DEPS
    )
    a11y_html = _render_a11y(node_list, edge_list)

    return (
        "<!doctype html>\n"
        "<html lang=\"en\">\n"
        "<head>\n"
        "  <meta charset=\"utf-8\">\n"
        f"  <meta http-equiv=\"Content-Security-Policy\" content=\"{csp}\">\n"
        f"  <title>{html.escape(title)}</title>\n"
        f"  <style nonce=\"{nonce}\">{_STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        f"    <header><strong>{html.escape(title)}</strong>"
        f" <span class=\"badge\">nodes: {len(node_list)}</span>"
        f" <span class=\"badge\">edges: {len(edge_list)}</span></header>\n"
        "    <div id=\"canvas\" role=\"img\" aria-label=\"graph canvas\"></div>\n"
        "    <aside aria-label=\"accessible graph listing\">\n"
        + a11y_html
        + "    </aside>\n"
        "  </main>\n"
        + scripts
        + "\n"
        f"  <script type=\"application/json\" id=\"graph-data\">{payload_json}</script>\n"
        f"  <script nonce=\"{nonce}\">{_BOOTSTRAP_JS}</script>\n"
        "</body>\n"
        "</html>\n"
    )


_BOOTSTRAP_JS = """
  (function() {
    var el = document.getElementById('graph-data');
    if (!el) return;
    var data;
    try { data = JSON.parse(el.textContent || '{}'); } catch (e) { return; }
    if (typeof graphology === 'undefined' || typeof Sigma === 'undefined') return;
    var g = new graphology.Graph();
    (data.nodes || []).forEach(function(n) {
      try {
        g.addNode(n.uid, {
          label: n.label,
          size: 4,
          x: Math.random(),
          y: Math.random(),
          color: kindColor(n.kind)
        });
      } catch (e) { /* duplicate uid — ignore */ }
    });
    (data.edges || []).forEach(function(e) {
      try {
        g.addEdgeWithKey(
          e.source + '->' + e.target + ':' + e.edge_type,
          e.source, e.target,
          { label: e.edge_type, color: '#444a55' }
        );
      } catch (err) { /* missing endpoints — ignore */ }
    });
    new Sigma(g, document.getElementById('canvas'));
    function kindColor(kind) {
      if (!kind) return '#888';
      if (kind.indexOf('doc:') === 0) return '#5aa8ff';
      if (kind.indexOf('task:') === 0) return '#ffa64d';
      if (kind.indexOf('cos:') === 0) return '#c68fff';
      return '#7fd4a0';
    }
  })();
"""


def _node_to_public(node: GraphNode) -> dict:
    return {
        "uid": node.uid,
        "kind": node.kind,
        "label": node.label,
        "file_path": node.file_path,
        "start_line": node.start_line,
    }


def _edge_to_public(edge: GraphEdge) -> dict:
    return {
        "source": edge.source_uid,
        "target": edge.target_uid,
        "edge_type": edge.edge_type,
        "confidence": edge.confidence,
    }


def _render_a11y(nodes: list[GraphNode], edges: list[GraphEdge]) -> str:
    """Serve a list-view fallback for screen readers / no-WebGL."""
    by_uid = {n.uid: n for n in nodes}
    items: list[str] = []
    for node in nodes:
        outgoing = [e for e in edges if e.source_uid == node.uid]
        lines = [
            f"<li><details><summary><span class=\"node-kind\">{html.escape(node.kind)}</span> "
            f"— {html.escape(node.label or node.uid)}</summary>"
        ]
        if outgoing:
            lines.append("<ul>")
            for e in outgoing:
                target = by_uid.get(e.target_uid)
                target_label = target.label if target and target.label else e.target_uid
                lines.append(
                    f"<li><span class=\"edge-type\">{html.escape(e.edge_type)}</span>"
                    f" → {html.escape(target_label)}</li>"
                )
            lines.append("</ul>")
        else:
            lines.append("<div class=\"badge\">no outgoing edges</div>")
        lines.append("</details></li>")
        items.append("".join(lines))
    return "<ul class=\"a11y\">" + "".join(items) + "</ul>"


__all__ = ["render"]
