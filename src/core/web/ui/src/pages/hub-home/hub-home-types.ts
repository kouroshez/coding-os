// Shapes served by /api/hub/* (routes/_hub_shared.py, _hub_scan.py).

export interface HubProject {
  slug: string;
  path: string;
  created_at?: string;
  source?: 'registry' | 'runtime-cwd' | string;
}

export interface HubProjectsPayload {
  projects: HubProject[];
  count: number;
}

export interface ScanHit {
  path: string;
  slug: string;
  already_registered: boolean;
}

export interface ScanPayload {
  root: string;
  hits: ScanHit[];
  count: number;
  visited_dirs: number;
  hit_limit_reached: boolean;
  depth_limit_reached: boolean;
}

export interface GcPayload {
  kept: { slug: string; path: string }[];
  removed: { slug: string; path: string }[];
  dry_run: boolean;
  kept_count: number;
  removed_count: number;
}

export interface SuggestRootsPayload {
  suggestions: string[];
  scaffoldable: string[];
}

export type ActionError = { action: string; message: string } | null;
