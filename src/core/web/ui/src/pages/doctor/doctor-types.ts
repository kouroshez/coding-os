// Shapes served by /api/health, /api/health/db and cos_graph_doctor.

import type { MetricSample } from '@/lib/prometheus-parse';

export type Tab = 'overview' | 'health' | 'maintenance' | 'backend' | 'sqlite';

export interface HealthPayload {
  status: 'ok' | 'degraded' | string;
  backend_id: string;
  edge_sample?: number;
  node_count_sample?: number;
  edge_count_sample?: number;
  file_index_state_rows?: number | null;
  file_index_state_last_indexed_at?: number | null;
  file_index_state_error?: string;
  reason?: string;
}

export interface DbHealthPayload {
  db_path: string;
  exists: boolean;
  size_bytes: number;
  tables: Record<string, number | null | { error: string }>;
  diagnostics?: string[];
  error?: string;
}

export interface GraphDoctorPayload {
  ok?: boolean;
  data?: Record<string, unknown>;
  [k: string]: unknown;
}


export interface GraphIssue {
  category: string;
  count: number;
  sample?: Array<Record<string, unknown>>;
}
export interface GraphStats {
  node_count?: number;
  edge_count?: number;
  orphaned_nodes?: number;
  // W7.6: split orphan stats — orphaned_inrepo are real bugs;
  // orphaned_external_unresolved are stdlib/3rd-party stub surface.
  orphaned_inrepo?: number;
  orphaned_external_unresolved?: number;
  issue_count?: number;
  fixed_edge_count?: number;
}
export interface GraphDoctorData {
  healthy?: boolean;
  issues?: GraphIssue[];
  stats?: GraphStats;
  meta?: Record<string, unknown>;
}

export interface MetricsState {
  samples: MetricSample[];
  totalsHistory: number[]; // rolling total requests
  errorsHistory: number[]; // rolling 4xx+5xx counter (if available)
  lastTotal: number | null;
  lastFetched: number;
  err: string | null;
}

