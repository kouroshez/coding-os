// Shapes served by /api/memory/* and the learning tools.

import type { paths } from '@/lib/api-client';

export interface PatternRow {
  id: number;
  pattern: string;
  memory_type: string;
  domain: string | null;
  source: string | null;
  confidence: number;
  decay_rate: number;
  impact_score: number;
  times_validated: number;
  times_violated: number;
  access_count: number;
  trust_tier: string;
  tier: string; // Forming | Trusted | Fading — computed by pattern_tier()
  provenance: string;
  promoted_to: string | null;
  evidence_json: string | null;
  last_validated: string | null;
  last_accessed_at: string | null;
  created_at: string;
}

export interface PatternsData {
  patterns: PatternRow[];
  count: number;
  total_count: number;
}

// Envelope derived from the OpenAPI schema so a producer rename fails typecheck.
// `summary` is declared as an opaque dict there (the nightly task map), so the
// slice this panel reads stays narrowed by hand — verified against
// routes/scheduled.py::_run_project.
export type RunResult =
  paths['/api/scheduled/run/{slug}']['post']['responses']['200']['content']['application/json'];

export interface RunResp extends Omit<RunResult, 'summary'> {
  summary?: {
    tasks?: {
      learn_extract?: { status?: string; extracted?: unknown[]; total_outcomes_analyzed?: number };
    };
  } | null;
}

// Field names mirror src/core/web/routes/patterns.py::learning_roi exactly.
export interface RoiSession {
  session_id: string;
  friction: number;
  total: number;
  rate: number;
  started: string;
}
export interface RoiData {
  sessions: RoiSession[];
  count: number;
  trend: string;
  delta_pct: number;
  validations_30d: number;
  helpful_rate_30d: number | null;
}
