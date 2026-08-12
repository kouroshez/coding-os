// Shapes served by /api/patterns/*, /api/scheduled/* and the learning tools.
// Field names mirror the producers exactly (api-contract-discipline):
//   patterns  → src/core/web/routes/patterns.py::_COLUMNS + the computed `tier`
//   roi       → src/core/web/routes/patterns.py::learning_roi
//   scheduled → src/core/web/routes/scheduled.py (FLAT — no {data, meta} envelope)

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
  summary?: ScheduledState | null;
}

// GET /api/scheduled/project/<slug> returns the verbatim last_run.json plus the
// slug — no envelope, no response_model. An unknown slug still answers HTTP 200
// but with `error` instead of state, which is why `error` is modelled here: the
// page must show a failure, not a silent "never ran".
export interface ScheduledTask {
  status?: string;
  reason?: string;
}

export interface ScheduledState {
  slug?: string;
  run_at?: string | null;
  consecutive_failures?: number;
  last_error?: string | null;
  tasks?: Record<string, ScheduledTask>;
  error?: string;
}

export interface RoiData {
  sessions: { session_id: string; friction: number; total: number; rate: number; started: string }[];
  count: number;
  trend: string;
  delta_pct: number;
  validations_30d: number;
  helpful_rate_30d: number | null;
}
