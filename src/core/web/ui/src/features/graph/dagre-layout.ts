import dagre from 'dagre';
import type Graph from 'graphology';
import type { SigmaEdgeAttrs, SigmaNodeAttrs } from './graph-adapter';

/**
 * Dagre hierarchical layout for the Containment view ( P5).
 *
 * For folder → file → class → method graphs, ForceAtlas2 produces a
 * hairball — every CONTAINS edge has confidence 1.0 so spring forces
 * pull everything together.  Dagre lays nodes out top-down with one
 * rank per containment level, which matches how engineers think about
 * a repo: roots at the top, leaves at the bottom, no diagonals
 * crossing the canvas.
 *
 * The function mutates `graph` in-place with `x`/`y` coordinates that
 * Sigma can render directly.  Coordinates are normalised to a square
 * around the origin so Sigma's camera reset frames the whole tree.
 */
export function applyDagreLayout(
  graph: Graph<SigmaNodeAttrs, SigmaEdgeAttrs>,
): void {
  if (graph.order === 0) return;

  const g = new dagre.graphlib.Graph();
  g.setGraph({
    rankdir: 'TB',
    nodesep: 30,
    ranksep: 60,
    marginx: 20,
    marginy: 20,
  });
  g.setDefaultEdgeLabel(() => ({}));

  // Default per-node bounding box. Sigma uses a circular node so dagre
  // just needs reasonable extents to space things out.
  const nodeWidth = 100;
  const nodeHeight = 30;

  graph.forEachNode((nodeId) => {
    g.setNode(nodeId, { width: nodeWidth, height: nodeHeight });
  });

  // Only feed dagre the contains backbone; semantic edges should not
  // influence the hierarchical layout (they'd add cycles).
  graph.forEachEdge((_edgeId, attrs, sourceId, targetId) => {
    if ((attrs.edgeType ?? '') === 'contains') {
      g.setEdge(sourceId, targetId);
    }
  });

  dagre.layout(g);

  // Compute bounds so we can centre + normalise.
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  graph.forEachNode((nodeId) => {
    const pos = g.node(nodeId);
    if (!pos || pos.x == null || pos.y == null) return;
    if (pos.x < minX) minX = pos.x;
    if (pos.x > maxX) maxX = pos.x;
    if (pos.y < minY) minY = pos.y;
    if (pos.y > maxY) maxY = pos.y;
  });

  // Empty layout (no contains edges fed in) — leave coordinates alone.
  if (!Number.isFinite(minX) || !Number.isFinite(minY)) return;

  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const xSpan = Math.max(maxX - minX, 1);
  const ySpan = Math.max(maxY - minY, 1);
  // Scale x and y independently so the tree fills the viewport even
  // when many siblings sit at the same rank (otherwise a uniform
  // scale collapses the vertical axis onto a single line).
  const xScale = 2 / xSpan;
  const yScale = 2 / ySpan;

  graph.forEachNode((nodeId) => {
    const pos = g.node(nodeId);
    if (!pos || pos.x == null || pos.y == null) return;
    graph.updateNodeAttributes(nodeId, (attrs) => ({
      ...attrs,
      x: (pos.x - cx) * xScale,
      // Negate y so the tree is oriented top-down on the Sigma canvas
      // (graphology / Sigma use mathematical y, dagre uses screen y).
      y: (cy - pos.y) * yScale,
    }));
  });
}
