// Shapes served by /api/patterns/* and the learning tools.
// Field names mirror the producers exactly (api-contract-discipline):
//   patterns  → src/core/web/routes/patterns.py::_COLUMNS + the computed `tier`
//   roi       → src/core/web/routes/patterns.py::learning_roi

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

export interface RoiData {
  sessions: { session_id: string; friction: number; total: number; rate: number; started: string }[];
  count: number;
  trend: string;
  delta_pct: number;
  validations_30d: number;
  helpful_rate_30d: number | null;
}
