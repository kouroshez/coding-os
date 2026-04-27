import { useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import SpriteText from 'three-spritetext';
import * as THREE from 'three';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
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
  degree: number;
  // Used by linkDirectionalParticles to identify highway edges.
  filePath?: string;
  startLine?: number;
  // force-graph fills these in after sim runs.
  x?: number;
  y?: number;
  z?: number;
}

interface ForceLink {
  source: string | ForceNode;
  target: string | ForceNode;
  edge_type: string;
  color: string;
  width: number;
  combinedDegree: number;
}

interface ForceGraphData {
  nodes: ForceNode[];
  links: ForceLink[];
}

// Edge palette — vivid on dark canvas. Each family has its own hue
// family so highways read at a glance:
//   structure (contains)        → warm amber
//   call/dispatch                → primary orange (Mocha)
//   inheritance / API surface    → magenta / royal orange
//   types                        → teal
//   docs / cross-refs            → cool blue
//   noise / weak ties            → muted graphite
const EDGE_PALETTE: Record<string, { color: string; width: number }> = {
  contains: { color: '#FFB37A', width: 0.5 },
  calls: { color: '#FF7A3D', width: 0.4 },
  constructs: { color: '#FF9966', width: 0.5 },
  imports: { color: '#5A9FFF', width: 0.4 },
  inherits_from: { color: '#C575FF', width: 0.6 },
  implements: { color: '#C575FF', width: 0.6 },
  extends: { color: '#C575FF', width: 0.6 },
  has_param_type: { color: '#5FE6CD', width: 0.3 },
  returns_type: { color: '#5FE6CD', width: 0.3 },
  field_of_type: { color: '#5FE6CD', width: 0.3 },
  is_decorated_by: { color: '#B19A93', width: 0.3 },
  references_doc: { color: '#7BB6FF', width: 0.4 },
  cites_heading: { color: '#7BB6FF', width: 0.4 },
  links_to: { color: '#7BB6FF', width: 0.4 },
  handles_route: { color: '#FFA73D', width: 0.5 },
  handles_tool: { color: '#FFA73D', width: 0.5 },
  handles_event: { color: '#FFA73D', width: 0.5 },
  dispatches: { color: '#FFA73D', width: 0.5 },
  defines_route: { color: '#FFA73D', width: 0.5 },
  awaits: { color: '#FFD27A', width: 0.4 },
  blocks: { color: '#FF5E5E', width: 0.7 },
  depends_on: { color: '#A89788', width: 0.4 },
  re_exports: { color: '#94a3b8', width: 0.3 },
  member_of_community: { color: '#FF8FCB', width: 0.3 },
};

// Vibrant kind palette — restated for the dark canvas so spheres pop
// against #0a0606. The 2D adapter keeps its paper-bg palette; this
// component owns its own hex map so neither view looks washed out.
const KIND_3D_COLOR: Record<string, string> = {
  folder: '#FFB37A',
  file: '#5A9FFF',
  module: '#7BB6FF',
  class: '#FF7A3D',
  method: '#FF9966',
  function: '#FFA73D',
  variable: '#5FE6CD',
  interface: '#C575FF',
  import_: '#A89788',
  route: '#FF5E5E',
  tool: '#FFD27A',
  mcp_tool: '#FFA73D',
  event: '#5FE6CD',
  task: '#FF8FCB',
  doc_file: '#7BB6FF',
  doc_heading: '#5A9FFF',
  doc_frontmatter: '#5A9FFF',
  doc_external: '#A89788',
  rule: '#FF5E5E',
  skill: '#C575FF',
  contract: '#5FE6CD',
  community: '#FF8FCB',
  hook: '#FFA73D',
  identifier: '#A89788',
  unknown: '#A89788',
};

const CANVAS_BG = '#0a0606';
const NOISE_KINDS: ReadonlySet<string> = new Set([
  'doc:frontmatter_key',
  'doc_frontmatter',
  'doc:heading',
  'doc_heading',
]);

function colorForKind(kind: string, raw: string | null | undefined): string {
  return KIND_3D_COLOR[kind] ?? kindColor(raw);
}

function adaptPayload(
  payload: ApiGraphPayload,
  visibleKinds: Set<string>,
  visibleEdgeTypes: Set<string>,
): { data: ForceGraphData; degreeMap: Map<string, number>; highwayThreshold: number } {
  const allNodes = payload.nodes ?? [];
  const filtered = allNodes.filter((n) => !NOISE_KINDS.has(n.kind ?? ''));
  const edges = payload.edges ?? [];

  const degreeMap = new Map<string, number>();
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    degreeMap.set(e.source_uid, (degreeMap.get(e.source_uid) ?? 0) + 1);
    degreeMap.set(e.target_uid, (degreeMap.get(e.target_uid) ?? 0) + 1);
  }

  // Highway edge threshold: top-quartile by combined degree. This is
  // what the screenshots call "shaharah" (شاهراه) — the major routes
  // between hubs. They get particle flow + brighter colour.
  const combinedDegrees: number[] = [];
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    combinedDegrees.push(
      (degreeMap.get(e.source_uid) ?? 0) + (degreeMap.get(e.target_uid) ?? 0),
    );
  }
  combinedDegrees.sort((a, b) => b - a);
  const highwayThreshold =
    combinedDegrees.length === 0
      ? Number.POSITIVE_INFINITY
      : combinedDegrees[Math.floor(combinedDegrees.length * 0.15)] ?? 0;

  const nodeUids = new Set<string>();
  const nodes: ForceNode[] = [];
  for (const n of filtered) {
    if (!n.uid || nodeUids.has(n.uid)) continue;
    const kind = normalizeKind(n.kind);
    if (visibleKinds.size > 0 && !visibleKinds.has(kind)) continue;
    const d = degreeMap.get(n.uid) ?? 0;
    // More aggressive scaling: tiny leaves stay tiny, big hubs really
    // dominate. Range 1.5 → 30 follows log curve so a 200-deg hub is
    // ~10× a 5-deg neighbour but never blows out the canvas.
    const base = kind === 'folder' ? 4 : kind === 'file' ? 3 : 1.5;
    const size = Math.min(30, base + Math.log2(d + 1) * 2.4);
    nodeUids.add(n.uid);
    nodes.push({
      id: n.uid,
      label: n.label || n.uid,
      kind,
      color: colorForKind(kind, n.kind),
      size,
      degree: d,
      filePath: n.file_path ?? undefined,
      startLine: n.start_line ?? undefined,
    });
  }

  const links: ForceLink[] = [];
  for (const e of edges) {
    if (!e.source_uid || !e.target_uid) continue;
    if (!nodeUids.has(e.source_uid) || !nodeUids.has(e.target_uid)) continue;
    if (visibleEdgeTypes.size > 0 && !visibleEdgeTypes.has(e.edge_type)) continue;
    const palette = EDGE_PALETTE[e.edge_type] ?? { color: '#A89788', width: 0.3 };
    const combined =
      (degreeMap.get(e.source_uid) ?? 0) + (degreeMap.get(e.target_uid) ?? 0);
    // Highway edges visibly thicker — 0.4 baseline, up to 1.4 for the
    // top-shaharah routes between major hubs.
    const widthBoost = combined >= highwayThreshold ? 1.0 : 0.0;
    links.push({
      source: e.source_uid,
      target: e.target_uid,
      edge_type: e.edge_type,
      color: palette.color,
      width: palette.width + widthBoost,
      combinedDegree: combined,
    });
  }
  return { data: { nodes, links }, degreeMap, highwayThreshold };
}

// Three.js Three3D graph host. Spheres + sprite labels + bloom post-
// processing for the enterprise look. Hubs get emissive glow; highway
// edges flow particles.
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
    max_nodes: selectedRootUid ? 1000 : 700,
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

  const { graphData, highwayThreshold } = useMemo(() => {
    if (!data) {
      return {
        graphData: { nodes: [], links: [] } as ForceGraphData,
        highwayThreshold: Number.POSITIVE_INFINITY,
      };
    }
    const adapted = adaptPayload(
      data,
      new Set(visibleKinds),
      new Set(visibleEdgeTypes),
    );
    return {
      graphData: adapted.data,
      highwayThreshold: adapted.highwayThreshold,
    };
  }, [data, visibleKinds, visibleEdgeTypes]);

  // Pre-compute neighbour adjacency so hover-highlight is O(1).
  const neighbourMap = useMemo<Map<string, Set<string>>>(() => {
    const map = new Map<string, Set<string>>();
    for (const link of graphData.links) {
      const src = typeof link.source === 'string' ? link.source : link.source.id;
      const tgt = typeof link.target === 'string' ? link.target : link.target.id;
      if (!map.has(src)) map.set(src, new Set());
      if (!map.has(tgt)) map.set(tgt, new Set());
      map.get(src)!.add(tgt);
      map.get(tgt)!.add(src);
    }
    return map;
  }, [graphData.links]);

  // Bloom post-processing — gives hubs that "glowing star" look from
  // the reference screenshots.
  useEffect(() => {
    const fg = fgRef.current as
      | {
          postProcessingComposer?: () => {
            addPass: (p: unknown) => void;
            passes?: unknown[];
          };
          scene?: () => THREE.Scene;
        }
      | null;
    if (!fg || typeof fg.postProcessingComposer !== 'function') return;
    const composer = fg.postProcessingComposer();
    if (!composer) return;
    // Idempotent — only add the bloom pass once.
    const passes = composer.passes ?? [];
    const alreadyHas = passes.some(
      (p) => (p as { name?: string }).name === 'cos-bloom',
    );
    if (alreadyHas) return;
    const bloom = new UnrealBloomPass(
      new THREE.Vector2(size.w || 800, size.h || 600),
      0.9, // strength
      0.6, // radius
      0.15, // threshold — lower = more things glow
    );
    (bloom as unknown as { name: string }).name = 'cos-bloom';
    composer.addPass(bloom);

    // Add ambient + a couple of point lights for proper sphere shading.
    if (typeof fg.scene === 'function') {
      const scene = fg.scene();
      const hasLight = scene.children.some(
        (c) => c instanceof THREE.AmbientLight,
      );
      if (!hasLight) {
        scene.add(new THREE.AmbientLight(0xffffff, 0.55));
        const key = new THREE.PointLight(0xffd2a0, 1.1, 0, 2);
        key.position.set(180, 220, 280);
        scene.add(key);
        const fill = new THREE.PointLight(0x5a9fff, 0.6, 0, 2);
        fill.position.set(-220, -100, -280);
        scene.add(fill);
      }
    }
  }, [size.w, size.h, graphData.nodes.length]);

  // Custom node renderer — Lambert sphere with emissive scaling on
  // degree, optional sprite label.
  const nodeThreeObject = (raw: object): THREE.Object3D => {
    const node = raw as ForceNode;
    const group = new THREE.Group();
    const isHovered = hovered === node.id;
    const isNeighbour =
      hovered != null && neighbourMap.get(hovered)?.has(node.id);
    const dim = hovered != null && !isHovered && !isNeighbour;

    const sphereMat = new THREE.MeshStandardMaterial({
      color: node.color,
      emissive: node.color,
      // Hubs glow more — emissiveIntensity scales with size (which is
      // log of degree). Capped so smaller nodes stay subtle.
      emissiveIntensity: Math.min(0.9, 0.15 + node.size / 36),
      roughness: 0.32,
      metalness: 0.08,
      transparent: dim,
      opacity: dim ? 0.18 : 1.0,
    });
    const sphere = new THREE.Mesh(
      new THREE.SphereGeometry(node.size, 24, 24),
      sphereMat,
    );
    group.add(sphere);

    // Halo ring for the very biggest hubs — extra emphasis on the
    // major spines like server.py / cli/main.py.
    if (node.size > 14) {
      const halo = new THREE.Mesh(
        new THREE.RingGeometry(node.size * 1.3, node.size * 1.55, 48),
        new THREE.MeshBasicMaterial({
          color: node.color,
          transparent: true,
          opacity: dim ? 0.06 : 0.35,
          side: THREE.DoubleSide,
        }),
      );
      halo.rotation.x = Math.PI / 2;
      group.add(halo);
    }

    const showLabel =
      isHovered ||
      isNeighbour ||
      node.size > 12 ||
      (!hovered && (node.kind === 'folder' || node.kind === 'file') && node.degree > 5);
    if (showLabel) {
      const sprite = new SpriteText(node.label);
      sprite.color = isHovered ? '#FFF6F0' : '#E8DFD0';
      sprite.backgroundColor = false;
      sprite.fontFace = '"Inter", system-ui, sans-serif';
      sprite.fontWeight = isHovered ? '600' : '400';
      sprite.textHeight = isHovered ? Math.max(node.size * 0.7, 4) : Math.max(node.size * 0.5, 2.5);
      sprite.position.set(0, node.size + 2, 0);
      // Cheap outline via padding-coloured stroke — keeps labels
      // legible against the dark canvas without an extra pass.
      sprite.strokeColor = CANVAS_BG;
      sprite.strokeWidth = 2;
      group.add(sprite);
    }

    return group;
  };

  // Highway / hover-aware link styling.
  const linkColor = (l: object): string => {
    const link = l as ForceLink;
    const src = typeof link.source === 'string' ? link.source : link.source.id;
    const tgt = typeof link.target === 'string' ? link.target : link.target.id;
    if (hovered) {
      if (src === hovered || tgt === hovered) return link.color;
      return '#1a1814';
    }
    return link.color;
  };

  const linkWidth = (l: object): number => {
    const link = l as ForceLink;
    return link.width;
  };

  const linkDirectionalParticles = (l: object): number => {
    const link = l as ForceLink;
    if (link.combinedDegree >= highwayThreshold) {
      // Highway: particles flow steadily — visible only when hover
      // doesn't dim the link.
      const src = typeof link.source === 'string' ? link.source : link.source.id;
      const tgt = typeof link.target === 'string' ? link.target : link.target.id;
      if (hovered && src !== hovered && tgt !== hovered) return 0;
      return 3;
    }
    return 0;
  };

  return (
    <div ref={containerRef} className="absolute inset-0 bg-[#0a0606]">
      {size.w > 0 && size.h > 0 && (
        <ForceGraph3D
          ref={fgRef as unknown as React.MutableRefObject<undefined>}
          width={size.w}
          height={size.h}
          backgroundColor={CANVAS_BG}
          graphData={graphData}
          nodeThreeObject={nodeThreeObject}
          nodeThreeObjectExtend={false}
          nodeRelSize={4}
          linkColor={linkColor}
          linkWidth={linkWidth}
          linkOpacity={hovered ? 0.95 : 0.55}
          linkDirectionalParticles={linkDirectionalParticles}
          linkDirectionalParticleWidth={0.7}
          linkDirectionalParticleSpeed={0.005}
          linkDirectionalParticleColor={(l: object) =>
            (l as ForceLink).color
          }
          enableNodeDrag={true}
          showNavInfo={false}
          warmupTicks={50}
          cooldownTicks={120}
          d3AlphaDecay={0.018}
          d3VelocityDecay={0.32}
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
          className="absolute left-3 top-3 rounded bg-black/70 px-3 py-1.5 text-xs text-white/80 backdrop-blur"
        >
          loading graph…
        </div>
      )}
      {!isLoading && graphData.nodes.length > 0 && (
        <div className="pointer-events-none absolute right-3 top-3 rounded bg-black/55 px-3 py-1.5 text-[11px] text-white/70 backdrop-blur">
          <span className="font-mono tabular-nums">
            {graphData.nodes.length} nodes · {graphData.links.length} edges
          </span>
        </div>
      )}
      {error && (
        <div
          role="alert"
          className="absolute left-3 top-3 rounded bg-rose-900/80 px-2 py-1 text-xs text-white"
        >
          {error.message}
        </div>
      )}
      {!isLoading && !error && graphData.nodes.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-white/60">
          no nodes reachable at this depth
        </div>
      )}
    </div>
  );
}
