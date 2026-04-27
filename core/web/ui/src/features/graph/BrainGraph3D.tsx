import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import * as THREE from 'three';
import { useGraphStore } from '@/store/graph-store';
import { useApiGet } from '@/lib/hooks';
import { kindColor, normalizeKind } from '@/lib/node-colors';
import type { ApiGraphPayload } from './graph-adapter';

interface ForceNode {
  id: string;
  label: string;
  kind: string;
  color: string;
  size: number;
  filePath?: string;
  startLine?: number;
}

interface ForceLink {
  source: string;
  target: string;
  edge_type: string;
  color: string;
  width: number;
}

interface ForceGraphData {
  nodes: ForceNode[];
  links: ForceLink[];
}

// Edge palette — mirrors graph-adapter.ts so 2D and 3D views agree on
// what each edge type means visually.
const EDGE_PALETTE: Record<string, { color: string; width: number }> = {
  contains: { color: '#8B5A2B', width: 0.6 },
  calls: { color: '#FF7A3D', width: 0.5 },
  constructs: { color: '#C84B16', width: 0.55 },
  imports: { color: '#2C5AA0', width: 0.45 },
  inherits_from: { color: '#7A3A7A', width: 0.6 },
  implements: { color: '#7A3A7A', width: 0.6 },
  extends: { color: '#7A3A7A', width: 0.6 },
  has_param_type: { color: '#3A7A7A', width: 0.35 },
  returns_type: { color: '#3A7A7A', width: 0.35 },
  field_of_type: { color: '#3A7A7A', width: 0.35 },
  is_decorated_by: { color: '#B19A93', width: 0.35 },
  references_doc: { color: '#5A7CA8', width: 0.4 },
  cites_heading: { color: '#5A7CA8', width: 0.4 },
  links_to: { color: '#5A7CA8', width: 0.4 },
  handles_route: { color: '#D96C2C', width: 0.55 },
  handles_tool: { color: '#D96C2C', width: 0.55 },
  handles_event: { color: '#D96C2C', width: 0.55 },
  dispatches: { color: '#D96C2C', width: 0.55 },
  defines_route: { color: '#D96C2C', width: 0.55 },
  awaits: { color: '#FFA468', width: 0.45 },
  blocks: { color: '#8B2318', width: 0.6 },
  depends_on: { color: '#6B504A', width: 0.45 },
  re_exports: { color: '#94a3b8', width: 0.35 },
  member_of_community: { color: '#C0719B', width: 0.3 },
};

const NOISE_KINDS: ReadonlySet<string> = new Set([
  'doc:frontmatter_key',
  'doc_frontmatter',
  'doc:heading',
  'doc_heading',
]);

function adaptPayload(
  payload: ApiGraphPayload,
  visibleKinds: Set<string>,
  visibleEdgeTypes: Set<string>,
): ForceGraphData {
  const allNodes = payload.nodes ?? [];
  const filtered = allNodes.filter((n) => !NOISE_KINDS.has(n.kind ?? ''));
  const edges = payload.edges ?? [];

  // Degree map for size scaling — hubs visibly larger.
  const degree = new Map<string, number>();
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    degree.set(e.source_uid, (degree.get(e.source_uid) ?? 0) + 1);
    degree.set(e.target_uid, (degree.get(e.target_uid) ?? 0) + 1);
  }
  const nodeUids = new Set<string>();
  const nodes: ForceNode[] = [];
  for (const n of filtered) {
    if (!n.uid || nodeUids.has(n.uid)) continue;
    const kind = normalizeKind(n.kind);
    if (visibleKinds.size > 0 && !visibleKinds.has(kind)) continue;
    const base = kind === 'folder' ? 5 : kind === 'file' ? 4 : 2.5;
    const d = degree.get(n.uid) ?? 0;
    const size = Math.min(18, base + Math.log2(d + 1) * 1.4);
    nodeUids.add(n.uid);
    nodes.push({
      id: n.uid,
      label: n.label || n.uid,
      kind,
      color: kindColor(n.kind),
      size,
      filePath: n.file_path ?? undefined,
      startLine: n.start_line ?? undefined,
    });
  }

  const links: ForceLink[] = [];
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    if (!nodeUids.has(e.source_uid) || !nodeUids.has(e.target_uid)) continue;
    if (visibleEdgeTypes.size > 0 && !visibleEdgeTypes.has(e.edge_type)) continue;
    const palette = EDGE_PALETTE[e.edge_type] ?? { color: '#8a8378', width: 0.4 };
    links.push({
      source: e.source_uid,
      target: e.target_uid,
      edge_type: e.edge_type,
      color: palette.color,
      width: palette.width,
    });
  }
  return { nodes, links };
}

// Three.js Three3D graph host. Replaces the legacy Sigma.js 2D canvas
// with a depth-aware force-directed view: spheres sized by degree,
// labels rendered as billboarded sprite-text, edges coloured by type.
export default function BrainGraph3D() {
  const fgRef = useRef<unknown>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [hovered, setHovered] = useState<string | null>(null);

  const selectedRootUid = useGraphStore((s) => s.selectedRootUid);
  const viewMode = useGraphStore((s) => s.viewMode);
  const visibleKinds = useGraphStore((s) => s.visibleKinds);
  const visibleEdgeTypes = useGraphStore((s) => s.visibleEdgeTypes);
  const setSelectedNode = useGraphStore((s) => s.setSelectedNode);

  // Read brand tokens for canvas BG and label colour so the 3D scene
  // matches the rest of the SPA in either light or dark theme.
  const [bgColor, setBgColor] = useState('#f4efe1');
  const [labelColor, setLabelColor] = useState('#1a1814');
  useEffect(() => {
    if (!containerRef.current) return;
    const cs = getComputedStyle(containerRef.current);
    setBgColor(cs.getPropertyValue('--cos-bg').trim() || '#f4efe1');
    setLabelColor(cs.getPropertyValue('--cos-text').trim() || '#1a1814');
  }, []);

  // Resize observer: 3d-force-graph wants explicit width/height props.
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const update = () => {
      const rect = el.getBoundingClientRect();
      setSize({ w: rect.width, h: rect.height });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const exportParams: Record<string, unknown> = {
    format: 'json',
    max_nodes: selectedRootUid ? 800 : 600,
    mode: viewMode,
  };
  if (selectedRootUid) {
    exportParams.root_uid = selectedRootUid;
    exportParams.include_spine = true;
  }
  const { data, isLoading, error } = useApiGet<ApiGraphPayload>(
    ['graph-export-3d', selectedRootUid ?? '__overview__', viewMode],
    '/api/graph/export',
    exportParams,
  );

  const graphData = useMemo<ForceGraphData>(() => {
    if (!data) return { nodes: [], links: [] };
    return adaptPayload(
      data,
      new Set(visibleKinds),
      new Set(visibleEdgeTypes),
    );
  }, [data, visibleKinds, visibleEdgeTypes]);

  // Pre-compute neighbour adjacency so hover-highlight is O(1).
  const neighbourMap = useMemo<Map<string, Set<string>>>(() => {
    const map = new Map<string, Set<string>>();
    for (const link of graphData.links) {
      const src =
        typeof link.source === 'string'
          ? link.source
          : (link.source as ForceNode).id;
      const tgt =
        typeof link.target === 'string'
          ? link.target
          : (link.target as ForceNode).id;
      if (!map.has(src)) map.set(src, new Set());
      if (!map.has(tgt)) map.set(tgt, new Set());
      map.get(src)!.add(tgt);
      map.get(tgt)!.add(src);
    }
    return map;
  }, [graphData.links]);

  // Custom node renderer: sphere mesh with optional label sprite.
  // Labels are gated on `hovered` to keep the scene legible — showing
  // every label on a 600-node scene is illegible.
  const nodeThreeObject = (raw: object): THREE.Object3D => {
    const node = raw as ForceNode;
    const group = new THREE.Group();
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(node.size, 16, 16),
      new THREE.MeshLambertMaterial({
        color: node.color,
        transparent: true,
        opacity:
          hovered && node.id !== hovered && !neighbourMap.get(hovered)?.has(node.id)
            ? 0.18
            : 1.0,
      }),
    );
    group.add(sphere);
    const showLabel =
      node.id === hovered ||
      (!hovered && (node.kind === 'folder' || node.kind === 'file')) ||
      (hovered && neighbourMap.get(hovered)?.has(node.id));
    if (showLabel) {
      const sprite = new SpriteText(node.label);
      sprite.color = labelColor;
      sprite.backgroundColor = false;
      sprite.fontFace = '"Inter", system-ui, sans-serif';
      sprite.textHeight = node.id === hovered ? node.size * 0.9 : node.size * 0.6;
      sprite.position.set(0, node.size + 1.5, 0);
      group.add(sprite);
    }
    return group;
  };

  return (
    <div ref={containerRef} className="absolute inset-0">
      {size.w > 0 && size.h > 0 && (
        <ForceGraph3D
          ref={fgRef as unknown as React.MutableRefObject<undefined>}
          width={size.w}
          height={size.h}
          backgroundColor={bgColor}
          graphData={graphData}
          nodeThreeObject={nodeThreeObject}
          nodeThreeObjectExtend={false}
          linkColor={(l: object) =>
            hovered &&
            (l as ForceLink).source !== hovered &&
            (l as ForceLink).target !== hovered &&
            !(
              typeof (l as ForceLink).source === 'object' &&
              ((l as ForceLink).source as unknown as ForceNode).id === hovered
            ) &&
            !(
              typeof (l as ForceLink).target === 'object' &&
              ((l as ForceLink).target as unknown as ForceNode).id === hovered
            )
              ? '#e7dfd0'
              : (l as ForceLink).color
          }
          linkWidth={(l: object) => (l as ForceLink).width}
          linkOpacity={0.7}
          linkDirectionalParticles={0}
          enableNodeDrag={true}
          showNavInfo={false}
          onNodeHover={(n: object | null) =>
            setHovered(n ? (n as ForceNode).id : null)
          }
          onNodeClick={(n: object) => setSelectedNode((n as ForceNode).id)}
          onBackgroundClick={() => setSelectedNode(null)}
        />
      )}
      {isLoading && (
        <div
          role="status"
          className="absolute left-3 top-3 rounded bg-[var(--cos-panel)] px-2 py-1 text-xs"
        >
          loading…
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="absolute left-3 top-3 rounded bg-rose-900/80 px-2 py-1 text-xs"
        >
          {error.message}
        </div>
      )}
      {!isLoading && !error && graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[var(--cos-muted)]">
          no nodes reachable at this depth
        </div>
      )}
    </div>
  );
}
